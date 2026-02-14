# -*- coding: utf-8 -*-
"""
Step3: 多次调用 LLM API 生成 5 个评审专家 Agent：
- 专家1：事实与逻辑；专家2：结构与深度；专家3：可行性与合规；
- 专家4：事实核查（调用 Perplexity API 检索核实），输出幻觉清单及有事实依据的修改意见；
- 专家5：文笔风格，去除 AI 味，使输出更有真人感。
"""
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _log(msg: str):
    ts = time.strftime("%H:%M:%S", time.localtime())
    print(f"[{ts}] {msg}", flush=True)
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config import REPORT_DIR, EXPERT_DIR
from src.kimi_client import chat
from src.llm_client import perplexity_chat_with_citations


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


def run_experts(report_v1_path: Path, output_basename: str = None) -> dict:
    """
    对报告 1.0 分别调用五位专家，生成意见并合并保存。
    专家4 另输出幻觉清单文件。返回各专家意见路径及合并文档路径。
    """
    report_v1_path = Path(report_v1_path)
    if not report_v1_path.is_file():
        raise FileNotFoundError(f"报告 1.0 不存在: {report_v1_path}")
    report_text = report_v1_path.read_text(encoding="utf-8", errors="replace")
    base = output_basename or report_v1_path.stem.replace("_report_v1", "")

    user_template = """请对以下《深度调查报告 1.0》进行评审，仅输出**可直接执行的修改意见**（分点列出），不要复述报告内容。

要求：修改意见应有助于提升严谨性与可读性，但**不要建议过度学术化、泛化或编造数据**，应保留原文的论述逻辑与案例丰富度。

---
{}
"""
    content_preview = report_text[:60000] if len(report_text) > 60000 else report_text
    user_msg = user_template.format(content_preview)

    _log("=" * 60)
    _log("Step3 专家评审：开始")
    _log(f"报告 1.0: {report_v1_path.name}, 约 {len(report_text)} 字")
    _log("=" * 60)

    results = {}
    for i, (name, system) in enumerate([
        ("专家1_事实与逻辑", EXPERT_1_SYSTEM),
        ("专家2_结构与深度", EXPERT_2_SYSTEM),
        ("专家3_可行性与合规", EXPERT_3_SYSTEM),
        ("专家4_事实核查", EXPERT_4_SYSTEM),
        ("专家5_文笔风格", EXPERT_5_SYSTEM),
    ], 1):
        _log(f"API 调用 #{i}: {name} 评审中...")
        t0 = time.time()
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
        _log(f"API#{i} 完成，耗时 {time.time()-t0:.1f}s，意见约 {len(opinion)} 字")
        out_path = EXPERT_DIR / f"{base}_{name}.md"
        out_path.write_text(f"# {name} 评审意见\n\n{opinion}", encoding="utf-8")
        results[name] = {"path": str(out_path), "content": opinion}
        _log(f"已保存: {out_path.name}")

        # 专家4：单独保存幻觉清单（始终保存，便于 Step4 加载）
        if name == "专家4_事实核查":
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

    # 合并为一份「专家意见汇总」
    combined = f"# 深度调查报告 1.0 — 专家评审意见汇总\n\n"
    for name, data in results.items():
        if name.startswith("_"):
            continue
        content = data.get("content") if isinstance(data, dict) else ""
        if content:
            combined += f"## {name}\n\n{content}\n\n---\n\n"
    combined_path = EXPERT_DIR / f"{base}_专家意见汇总.md"
    combined_path.write_text(combined, encoding="utf-8")
    results["_combined_path"] = str(combined_path)
    _log(f"Step3 完成：专家意见汇总已保存 {combined_path.name}")
    return results


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="对报告1.0生成五位专家评审意见（含幻觉清单）")
    parser.add_argument("report_v1", type=Path, help="报告 1.0 路径，如 output/reports/xxx_report_v1.md")
    parser.add_argument("-o", "--output-base", default=None, help="输出文件名前缀")
    args = parser.parse_args()
    run_experts(args.report_v1, args.output_base)
