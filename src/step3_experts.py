# -*- coding: utf-8 -*-
"""
Step3: 并行调用 LLM API 生成 5 个评审专家 Agent：
- 专家1：事实与逻辑；专家2：结构与深度；专家3：可行性与合规；
- 专家4：事实核查（调用 Perplexity API 检索核实），输出幻觉清单及有事实依据的修改意见；
- 专家5：文笔风格，去除 AI 味，使输出更有真人感。

所有 5 位专家并行调用，大幅缩短 Step3 总耗时。
"""
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import src  # noqa: F401  — 确保 PROJECT_ROOT 加入 sys.path

from config import EXPERT_DIR, EXPERT_PREVIEW_LIMIT, ARBITRATE_EXPERT_LIMIT
from src.llm_client import chat
from src.llm_client import perplexity_chat_with_citations
from src.report_type_profiles import load_report_type_profile
from src.utils.log import log as _log


EXPERT_1_SYSTEM = """你是一位严谨的「事实与逻辑」评审专家。你的评审重点：
- 内容事实与论据的细节是否可靠、是否有据可查；
- 局部观点与论证逻辑是否自洽、是否合理；
- 表述是否符合该专业领域的常识与惯例。

约束：修改意见应具体、可执行，但**不要建议过度学术化或泛化**，应保留原文的论述逻辑与案例丰富度。请用分点、可直接执行的方式输出修改意见。"""

EXPERT_2_SYSTEM = """你是一位「结构与深度」评审专家。你的评审重点：
- 整体文档架构是否完整、层次是否清晰，**章节是否控制在 7 章以内**；
- 重点观点的递进顺序是否合理，论述逻辑是否连贯；
- 表达的观点和主题是否鲜明，能否让读者快速把握核心结论。

**积极采用更系统的文档表达模式**，在结构与逻辑方面给出修改建议，包括但不限于：
- **三段论**：大前提 → 小前提 → 结论，使论证更严谨；
- **递进推理**：由浅入深、层层推进，增强说服力；
- **多角度分析与对比**：横向比较、纵向梳理，多维度展开论述；
- **动机理论**：从动机、需求、行为逻辑切入，使论证更有解释力。

约束：**不要建议将丰富论述压缩成空洞要点**，应保留论证的完整性与说服力。请用分点方式写出修改意见，注明建议采用的表达模式及理由，并标注优先级（高/中/低）。"""

EXPERT_3_SYSTEM = """你是一位「可行性与合规」评审专家。你的评审重点：
- 内容在现实中的可行性、合规性、安全性、合理性；
- 对文档内出现的不同观点、事实进行必要的横向/纵向比较分析；
- 指出可能存在的风险、矛盾或需要补充证据的地方。

约束：修改意见应务实，**不要建议过度规范化或虚构数据**。请用分点方式写出修改意见，注明类别（可行性/合规性/安全性/比较分析等）。"""

EXPERT_4_SYSTEM = """你是一位「事实核查」评审专家，具备实时检索能力。你的评审重点：

1. **利用检索核实事实**：对报告中的关键事实、数据、案例、人物、机构名称进行检索核实；
2. **有事实依据的修改意见**：对错误或过时的数据，基于检索结果给出正确数值及来源；对表述不准确之处，给出符合事实的改写建议，并注明依据；
3. **幻觉判定**：若无法找到任何可靠来源证实某事实、人物或实体存在，视为幻觉，须列入【幻觉清单】；
4. **修改意见须可执行**：每条修改建议应具体到「原文表述 → 建议改为 → 依据/来源」。

输出格式（必须严格遵循）：
1. 【修改意见】部分：分点列出可直接执行的事实修正建议，每条格式为「原文/位置 → 建议修改 → 事实依据（来源或检索结论）」；
2. 【幻觉清单】部分：列出需删除的虚构事实、人物、实体，每条注明：所在位置/原文表述/判定理由（检索无可靠来源）。若无幻觉则写「未发现虚构内容」。

幻觉清单中的内容将**不得出现在报告 2.0 中**。"""

EXPERT_5_SYSTEM = """你是一位「文笔与风格」评审专家。你的评审重点：
- 语法、用词、句式的规范性与准确性；
- 文风的统一性、专业性与可读性；
- **去除 AI 味道**：如过于工整的排比、空洞的套话、机械的过渡句、过度书面化的表达；
- **增强真人感**：使文本更像真人撰写，自然、有温度、有个人判断痕迹，避免千篇一律的模板化表述。

请用分点方式写出修改意见，标注建议修改的句式或表述类型，并给出改写示例（可选）。"""

DEFAULT_USER_TEMPLATE = """请对以下《深度调查报告 1.0》进行评审，仅输出**可直接执行的修改意见**（分点列出），不要复述报告内容。

要求：修改意见应有助于提升严谨性与可读性，但**不要建议过度学术化、泛化或编造数据**，应保留原文的论述逻辑与案例丰富度。

---
{}
"""


def _extract_hallucination_list(text: str) -> str:
    """从专家4输出中提取【幻觉清单】部分。"""
    for sep in ["【幻觉清单】", "## 幻觉清单", "### 幻觉清单", "幻觉清单：", "幻觉清单：\n"]:
        sep_clean = sep.replace("\n", "").strip()
        if sep in text or sep_clean in text:
            idx = text.find(sep) if sep in text else text.find(sep_clean)
            start = idx + (len(sep) if sep in text else len(sep_clean))
            part = text[start:].strip()
            next_section = len(part)
            for s in ["【修改意见】", "【专家5】", "\n## 专家", "\n## 修改", "### 事实核查引用来源", "---\n\n### 事实核查引用来源"]:
                if s in part:
                    pos = part.find(s)
                    if pos >= 0:
                        next_section = min(next_section, pos)
            return part[:next_section].strip()
    if "未发现虚构内容" in text or "未发现虚构" in text:
        return "未发现虚构内容。"
    return ""


def _build_profile_prompts(report_type: str | None = None) -> tuple[dict[str, str], str, dict]:
    """按报告类型加载 Step3 提示词（外部 markdown），缺失时回退默认提示。"""
    profile = load_report_type_profile(report_type)
    sections = profile.get("sections", {})
    user_template = sections.get("Step3 用户提示模板", DEFAULT_USER_TEMPLATE)
    prompts = {
        "专家1_事实与逻辑": sections.get("Step3 专家1_事实与逻辑", EXPERT_1_SYSTEM),
        "专家2_结构与深度": sections.get("Step3 专家2_结构与深度", EXPERT_2_SYSTEM),
        "专家3_可行性与合规": sections.get("Step3 专家3_可行性与合规", EXPERT_3_SYSTEM),
        "专家4_事实核查": sections.get("Step3 专家4_事实核查", EXPERT_4_SYSTEM),
        "专家5_文笔风格": sections.get("Step3 专家5_文笔风格", EXPERT_5_SYSTEM),
    }
    return prompts, user_template, profile


def _call_expert(name: str, system: str, user_msg: str, expert_idx: int) -> tuple[str, str, str]:
    """调用单个专家，返回 (name, opinion, error_msg)。"""
    _log(f"[并行] API 调用 #{expert_idx}: {name} 评审中...")
    t0 = time.time()
    opinion = ""
    try:
        if name == "专家4_事实核查":
            try:
                opinion, citations = perplexity_chat_with_citations(
                    [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user_msg},
                    ],
                    max_tokens=6144,
                    temperature=0.3,
                )
                if citations:
                    ref_block = "\n\n---\n\n### 事实核查引用来源\n\n" + "\n".join(
                        f"- [{r.get('title', '')}]({r.get('url', '')})" for r in citations[:20]
                    )
                    opinion = opinion + ref_block
            except Exception as e:
                _log(f"    Perplexity 调用失败，回退至主 LLM: {e}")
                opinion = chat(
                    [{"role": "system", "content": system}, {"role": "user", "content": user_msg}],
                    max_tokens=6144, temperature=0.4,
                )
        else:
            opinion = chat(
                [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user_msg},
                ],
                max_tokens=6144,
                temperature=0.4,
            )
        _log(f"[并行] API#{expert_idx} {name} 完成，耗时 {time.time()-t0:.1f}s，意见约 {len(opinion)} 字")
        return name, opinion, ""
    except Exception as e:
        _log(f"[并行] API#{expert_idx} {name} 失败: {e}")
        return name, "", str(e)


def _arbitrate_experts(combined_text: str, base: str) -> str:
    """对 5 位专家的汇总意见进行冲突仲裁，按优先级排序并裁定采纳/搁置/折中。"""
    prompt = f"""请对以下 5 位专家的评审意见进行**冲突仲裁**。

【优先级规则】
- 事实类意见（专家1 事实与逻辑、专家4 事实核查）优先级最高
- 结构类意见（专家2 结构与深度、专家3 可行性与合规）优先级次之
- 风格类意见（专家5 文笔风格）优先级最低
- 当不同专家意见冲突时，高优先级意见优先采纳

【任务】
1. 识别各专家意见中的**冲突点**（同一处内容收到相互矛盾的修改建议）
2. 对每个冲突点，按优先级给出裁定：**采纳**（接受某方）/ **搁置**（暂不修改）/ **折中**（综合处理）
3. 对无冲突的高价值意见，标记为**采纳**
4. 输出结构化的仲裁结果

【专家意见汇总】
---
{combined_text[:ARBITRATE_EXPERT_LIMIT]}
---

请输出仲裁结果，格式如下：

# 专家意见仲裁报告

## 冲突裁定
（列出冲突点及裁定）

## 采纳清单
（按优先级列出应采纳的修改意见）

## 搁置清单
（列出暂不采纳的意见及理由）

直接输出 Markdown，不要 JSON。"""

    _log("调用 API：专家意见冲突仲裁...", "arbitrate")
    t0 = time.time()
    resp = chat(
        [
            {"role": "system", "content": "你是中立的学术仲裁专家，擅长调和多方评审意见冲突，输出结构化裁定。"},
            {"role": "user", "content": prompt},
        ],
        max_tokens=8192,
        temperature=0.3,
    )
    _log(f"仲裁完成，耗时 {time.time()-t0:.1f}s", "arbitrate")

    # 保存仲裁结果
    arbitrate_path = EXPERT_DIR / f"{base}_专家意见仲裁.md"
    arbitrate_path.write_text(resp.strip(), encoding="utf-8")
    _log(f"已保存: {arbitrate_path.name}")

    return resp.strip()


def run_experts(
    report_v1_path: Path,
    output_basename: str = None,
    report_type: str | None = None,
) -> dict:
    """
    对报告 1.0 并行调用五位专家，生成意见并合并保存。
    专家4 另输出幻觉清单文件。返回各专家意见路径及合并文档路径。
    """
    report_v1_path = Path(report_v1_path)
    if not report_v1_path.is_file():
        raise FileNotFoundError(f"报告 1.0 不存在: {report_v1_path}")
    report_text = report_v1_path.read_text(encoding="utf-8", errors="replace")
    base = output_basename or report_v1_path.stem.replace("_report_v1", "")

    prompts, user_template, profile = _build_profile_prompts(report_type)
    content_preview = report_text[:EXPERT_PREVIEW_LIMIT] if len(report_text) > EXPERT_PREVIEW_LIMIT else report_text
    user_msg = user_template.format(content_preview)

    _log("=" * 60)
    _log("Step3 专家评审：开始（5 位专家并行）")
    _log(f"报告 1.0: {report_v1_path.name}, 约 {len(report_text)} 字 | 类型: {profile.get('display_name')}")
    _log("=" * 60)

    t_start = time.time()
    results = {}

    # 并行调用所有专家
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {}
        for i, (name, system) in enumerate(prompts.items(), 1):
            future = executor.submit(_call_expert, name, system, user_msg, i)
            futures[future] = (i, name)

        for future in as_completed(futures):
            i, name = futures[future]
            expert_name, opinion, error = future.result()
            if error:
                _log(f"专家 {expert_name} 出错: {error}")
                continue

            out_path = EXPERT_DIR / f"{base}_{expert_name}.md"
            out_path.write_text(f"# {expert_name} 评审意见\n\n{opinion}", encoding="utf-8")
            results[expert_name] = {"path": str(out_path), "content": opinion}
            _log(f"已保存: {out_path.name}")

            # 专家4：单独保存幻觉清单（始终保存，便于 Step4 加载）
            if expert_name == "专家4_事实核查":
                hallucination = _extract_hallucination_list(opinion)
                if not hallucination:
                    hallucination = "未发现虚构内容。"
                halluc_path = EXPERT_DIR / f"{base}_专家4_幻觉清单.md"
                halluc_path.write_text(
                    f"# 幻觉清单（虚构事实/人物/实体，不得出现在报告 2.0 中）\n\n{hallucination}",
                    encoding="utf-8",
                )
                results["_hallucination_path"] = str(halluc_path)
                _log(f"已保存幻觉清单: {halluc_path.name}")

    _log(f"Step3 全部专家评审完成，总耗时 {time.time()-t_start:.1f}s")

    # 合并为一份「专家意见汇总」（按固定顺序）
    combined = f"# 深度调查报告 1.0 — 专家评审意见汇总\n\n"
    for name in prompts.keys():
        data = results.get(name)
        if data:
            content = data.get("content") if isinstance(data, dict) else ""
            if content:
                combined += f"## {name}\n\n{content}\n\n---\n\n"
    combined_path = EXPERT_DIR / f"{base}_专家意见汇总.md"
    combined_path.write_text(combined, encoding="utf-8")
    results["_combined_path"] = str(combined_path)
    _log(f"专家意见汇总已保存 {combined_path.name}")

    # 专家意见冲突仲裁
    _log("Step3 进入专家意见冲突仲裁...")
    _arbitrate_experts(combined, base)
    results["_arbitrate_path"] = str(EXPERT_DIR / f"{base}_专家意见仲裁.md")

    _log(f"Step3 完成：专家意见汇总与仲裁已保存")
    return results


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="对报告1.0生成五位专家评审意见（含幻觉清单）")
    parser.add_argument("report_v1", type=Path, help="报告 1.0 路径，如 output/reports/xxx_report_v1.md")
    parser.add_argument("-o", "--output-base", default=None, help="输出文件名前缀")
    parser.add_argument(
        "-t",
        "--report-type",
        default=None,
        help="报告类型（对应 output/skill/report_types/*.md），如 academic_research",
    )
    args = parser.parse_args()
    run_experts(args.report_v1, args.output_base, args.report_type)
