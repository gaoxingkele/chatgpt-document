# -*- coding: utf-8 -*-
"""
Step8：基于 Prompt RL 的分章迭代压缩，生成报告 5.0。
在保留重要信息（事实、分析逻辑）不减少的前提下，每轮每章压缩 10%~20%。
收敛条件：迭代达 MAX_ITERATIONS 次，或文档尺寸低于原始 MIN_FINAL_RATIO，任一满足即停止。
每步遵循 Skill 规范，输出 5.0 版本。
"""
import time
from pathlib import Path

import src  # noqa: F401  — 确保 PROJECT_ROOT 加入 sys.path

from config import REPORT_DIR, COMPRESS_SKILL_TEXT_LIMIT, COMPRESS_SUMMARY_TEXT_LIMIT, STEP8_ITERATION_DELAY
from src.llm_client import chat
from src.report_type_profiles import load_report_type_profile
from src.utils.markdown_utils import read_report_text as _read_report_text, parse_report_chapters as _parse_chapters
from src.utils.docx_utils import save_docx_safe
from src.utils.file_utils import load_skill_and_summary as _load_skill_and_summary
from src.utils.parallel import parallel_map


from src.utils.log import log as _log


# Prompt RL 参数
MAX_ITERATIONS = 3
MIN_COMPRESSION_RATIO = 0.10   # 每轮至少压缩 10%
MAX_COMPRESSION_RATIO = 0.20   # 每轮最多压缩 20%
MIN_FINAL_RATIO = 0.65         # 最终尺寸不低于原始 65%


def _compress_chapter(
    ch_title: str,
    ch_body: str,
    target_chars: int,
    style_guide: str,
    role_label: str,
) -> str:
    """对单个章节进行温和压缩。"""
    floor_chars = int(len(ch_body) * (1 - MAX_COMPRESSION_RATIO))
    prompt = f"""你是一位{role_label}精炼专家。请对以下章节进行**温和的无损信息压缩**。

【核心约束】
1. **必须保留**：所有事实、数据、案例、人物、机构名称、数学公式；分析逻辑与论证链；核心论点与结论。
2. **可删减**：冗余表述、重复解释、过渡性套话、过度铺陈。
3. **目标字数**：压缩后约 {target_chars}~{floor_chars} 字（当前约 {len(ch_body)} 字）。
   - **严禁过度压缩**：输出不得少于 {floor_chars} 字。
   - 仅压缩 10%~20%，保持文章完整可读。
4. **规范**：输出仍须遵循上方写作规范。

【章节标题】{ch_title}

【章节正文】
{ch_body}

请直接输出压缩后的完整章节，以 `## {ch_title}` 开头，使用 Markdown。不要 JSON 或说明。"""

    needed_tokens = min(16384, max(4096, int(target_chars * 1.5)))
    resp = chat(
        [
            {"role": "system", "content": style_guide + "\n\n你是精炼专家。温和压缩，零信息损失，仅删冗余。"},
            {"role": "user", "content": prompt},
        ],
        max_tokens=needed_tokens,
        temperature=0.2,
    )
    return resp.strip()


def _compress_one_iteration(
    header: str,
    chapters: list,
    skill_text: str,
    summary_text: str,
    role_label: str,
    iteration: int,
) -> str:
    """单轮分章并行压缩，返回拼接后的完整报告文本。"""
    style_guide = f"""
【写作规范 - Skill.md】（压缩时须继续遵循）
{skill_text[:COMPRESS_SKILL_TEXT_LIMIT]}

【summary.md 要点】
{summary_text[:COMPRESS_SUMMARY_TEXT_LIMIT]}
"""
    total = len(chapters)

    def _do_compress(idx, chapter):
        ch_title, ch_body = chapter
        target = int(len(ch_body) * (1 - MIN_COMPRESSION_RATIO))
        _log(f"  [迭代{iteration}] 压缩第 {idx+1}/{total} 章: {ch_title[:40]}... ({len(ch_body)}→≈{target}字)")
        result = _compress_chapter(ch_title, ch_body, target, style_guide, role_label)
        # 保护：若压缩结果为空或过短（<原文30%），回退到原文
        if len(result) < len(ch_body) * 0.3:
            _log(f"  [迭代{iteration}] 第 {idx+1} 章过度压缩，回退原文")
            result = f"## {ch_title}\n\n{ch_body}" if not ch_body.startswith("##") else ch_body
        else:
            _log(f"  [迭代{iteration}] 第 {idx+1} 章完成: {len(ch_body)}→{len(result)} 字")
        return result

    compressed_parts = parallel_map(_do_compress, chapters)
    return f"{header}\n\n" + "\n\n".join(compressed_parts)


def run_report_v5(
    report_input_path: Path,
    output_basename: str = None,
    policy_name: str = "policy1",
    report_type: str | None = None,
) -> dict:
    """
    基于 Step7 输出，采用分章 Prompt RL 迭代压缩，输出 5.0 版本。

    收敛条件：
    - 迭代次数达到 MAX_ITERATIONS 次；或
    - 文档尺寸低于原始 MIN_FINAL_RATIO
    任一条件满足即停止。
    """
    report_input_path = Path(report_input_path)
    if not report_input_path.is_file():
        raise FileNotFoundError(f"报告不存在: {report_input_path}")

    base = output_basename or report_input_path.stem.replace("_政治情报学分析报告", "")
    doc_text = _read_report_text(report_input_path)
    original_size = len(doc_text)

    profile = load_report_type_profile(report_type)
    resolved_policy = policy_name or profile.get("policy_name", "policy1")
    if policy_name == "policy1" and report_type:
        resolved_policy = profile.get("policy_name", "policy1")
    role_label = f"{profile.get('display_name', '学术分析报告')}文档"
    output_suffix = profile.get("step8_output_suffix", "报告_v5")

    skill_text, summary_text = _load_skill_and_summary(resolved_policy)

    _log("=" * 60)
    _log("Step8 报告 5.0：分章 Prompt RL 迭代压缩")
    _log(
        f"输入: {report_input_path.name} | 原始约 {original_size} 字 | "
        f"类型: {profile.get('display_name')} | Policy: {resolved_policy}"
    )
    _log(f"约束: 每轮每章压缩10%~20%, 最多{MAX_ITERATIONS}轮, 尺寸≥{int(MIN_FINAL_RATIO*100)}%")
    _log("=" * 60)

    min_final_size = int(original_size * MIN_FINAL_RATIO)
    current_doc = doc_text
    iteration = 0
    t0 = time.time()

    while iteration < MAX_ITERATIONS:
        prev_size = len(current_doc)
        if prev_size < min_final_size:
            _log(f"已达尺寸下限（{min_final_size} 字），停止")
            break

        header, chapters = _parse_chapters(current_doc)
        if not chapters:
            _log("[警告] 无法拆分章节，停止压缩")
            break

        _log(f"--- 迭代 {iteration + 1}/{MAX_ITERATIONS}: {len(chapters)} 章并行压缩（目标每章减 10%~20%）...")

        current_doc = _compress_one_iteration(
            header, chapters, skill_text, summary_text, role_label, iteration + 1,
        )

        new_size = len(current_doc)
        ratio = new_size / prev_size if prev_size else 0
        _log(f"    迭代 {iteration+1} 完成: {prev_size} → {new_size} 字，压缩率 {100*(1-ratio):.1f}%")

        if new_size >= prev_size * 0.95:
            _log("    [提示] 压缩未达 5%，提前停止迭代")
            break

        iteration += 1
        if len(current_doc) < min_final_size:
            _log(f"    已达尺寸下限（{min_final_size} 字），停止")
            break
        time.sleep(STEP8_ITERATION_DELAY)

    final_size = len(current_doc)
    _log(f"收敛完成，共 {iteration} 轮，最终约 {final_size} 字（原始 {int(100*final_size/original_size):.0f}%）")

    # 更新标题为 5.0 版
    first_line = current_doc.split("\n")[0] if current_doc else ""
    if first_line.startswith("# ") and "5.0" not in first_line:
        report_out = current_doc.replace(first_line, first_line.rstrip() + " 5.0版", 1)
    else:
        report_out = current_doc

    out_name = f"{base}_{output_suffix}"
    md_path = REPORT_DIR / f"{out_name}.md"
    md_path.write_text(report_out, encoding="utf-8")
    _log(f"已保存: {md_path.name}")

    docx_path = save_docx_safe(report_out, REPORT_DIR / f"{out_name}.docx")
    _log(f"Step8 完成：报告 5.0 已保存 {docx_path.name}，总耗时 {time.time()-t0:.1f}s")

    return {
        "report_path": str(md_path),
        "docx_path": str(docx_path),
        "report_text": report_out,
    }


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Step8: Prompt RL 迭代压缩，输出报告 5.0")
    parser.add_argument("report", type=Path, help="Step7 输出路径，如 xxx_政治情报学分析报告.docx")
    parser.add_argument("-o", "--output-base", default=None, help="输出文件名前缀")
    parser.add_argument("-p", "--policy", default="policy1", help="policy 子目录名")
    parser.add_argument("-t", "--report-type", default=None, help="报告类型（对应 output/skill/report_types/*.md）")
    args = parser.parse_args()
    run_report_v5(args.report, args.output_base, args.policy, args.report_type)
