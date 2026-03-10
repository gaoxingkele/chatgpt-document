# -*- coding: utf-8 -*-
"""
Step7（可选）：根据原始语料与最新版报告，采用 Skill.md 与 summary.md 进行风格化处理，
输出学术风格分析报告。支持并行章节处理，provider 由环境变量或参数指定。
"""
import time
from pathlib import Path

import src  # noqa: F401  — 确保 PROJECT_ROOT 加入 sys.path

from config import (
    REPORT_DIR,
    POLICY_CHAPTER_BODY_LIMIT, POLICY_RAW_PREVIEW_LIMIT,
    SKILL_TEXT_LIMIT, SUMMARY_TEXT_LIMIT, POLICY_RAW_TOTAL_LIMIT,
)
from src.llm_client import chat
from src.report_type_profiles import load_report_type_profile
from src.utils.markdown_utils import parse_report_chapters as _parse_report_v1_chapters, read_report_text as _read_report_text, extract_chapter_context as _extract_chapter_context
from src.utils.docx_utils import save_docx_safe
from src.utils.parallel import parallel_map


from src.utils.log import log as _log
from src.utils.file_utils import load_skill_and_summary as _load_skill_and_summary


def _process_single_chapter(
    idx: int,
    total: int,
    ch_title: str,
    ch_body: str,
    style_guide: str,
    raw_preview: str,
    context: dict = None,
) -> tuple[int, str, str]:
    """处理单个章节的风格化改写，返回 (idx, ch_title, revised_text)。"""
    _log(f"[并行] 风格化第 {idx + 1}/{total} 章: {ch_title[:40]}...")
    t0 = time.time()
    body_limit = POLICY_CHAPTER_BODY_LIMIT
    prompt = f"""你是一位学术分析报告写作专家。请将以下章节按照上方【写作规范】改写为学术风格分析报告。

要求：
1. 严格遵循 Skill.md 与 summary.md 中的结构规范、论证范式、语言与修辞、元认知框架；
2. 采用学术写作规范，章节结构清晰、论证可追溯、概念界定明确；
3. 使用中性、客观、可证据支撑的表述，避免政治动员语气；
4. 基于下方【原始语料摘要】补充或修正事实，确保内容有据可查；
5. **完整保留原文中的事实、数据、案例、论证链、数学公式，不要压缩或省略**。公式标记（`$...$` / `$$...$$`）须原样保留。

【原始语料摘要】（供参考）
{raw_preview[:POLICY_RAW_PREVIEW_LIMIT]}

【本章标题】{ch_title}

【本章正文】
{ch_body[:body_limit]}

"""
    # 章节上下文注入（仅较长章节）
    if context and len(ch_body) >= 1500:
        ctx_section = "\n【章节上下文（供衔接参考）】\n"
        if context.get("toc"):
            ctx_section += f"全文目录：\n{context['toc']}\n"
        if context.get("prev_summary"):
            ctx_section += f"上一章末尾：{context['prev_summary']}\n"
        if context.get("next_summary"):
            ctx_section += f"下一章开头：{context['next_summary']}\n"
        prompt += ctx_section

    prompt += f"""
请直接输出改写后的完整章节，以 `## {ch_title}` 开头，使用 Markdown。不要 JSON 或多余说明。"""

    resp = chat(
        [
            {"role": "system", "content": style_guide + "\n\n你是学术分析报告写作专家，严格按规范输出。"},
            {"role": "user", "content": prompt},
        ],
        max_tokens=8192,
        temperature=0.4,
    )
    _log(f"[并行] 第 {idx + 1} 章完成，耗时 {time.time()-t0:.1f}s，约 {len(resp)} 字")
    return idx, ch_title, resp.strip()


def _process_by_chapters(
    header: str,
    chapters: list[tuple[str, str]],
    skill_text: str,
    summary_text: str,
    raw_preview: str,
    policy_name: str,
) -> str:
    """
    并行按章节调用 LLM 进行风格化改写（学术风格），最后按原序拼接。
    """
    style_guide = f"""
【写作规范 - Skill.md】
{skill_text[:SKILL_TEXT_LIMIT]}

【写作规范 - summary.md 要点】
{summary_text[:SUMMARY_TEXT_LIMIT]}
"""
    total = len(chapters)
    contexts = _extract_chapter_context(chapters)

    def _do_chapter(idx, chapter):
        ch_title, ch_body = chapter
        _, _, revised = _process_single_chapter(idx, total, ch_title, ch_body, style_guide, raw_preview, context=contexts[idx])
        return revised

    revised_parts = parallel_map(_do_chapter, chapters)
    return "\n\n".join(revised_parts)


def run_report_policy(
    raw_path: Path,
    report_path: Path,
    output_basename: str = None,
    policy_name: str = "policy1",
    report_type: str | None = None,
) -> dict:
    """
    根据原始语料与最新版报告，采用 policy 目录下的 Skill.md 与 summary.md 进行风格化处理，
    输出学术风格分析报告。使用 Gemini API。

    参数:
        raw_path: 原始语料路径，如 output/raw/gaojinsumei.txt
        report_path: 最新版报告路径，如 output/reports/gaojinsumei_report_v4.docx
        output_basename: 输出文件名前缀
        policy_name: policy 子目录名，默认 policy1
        report_type: 报告类型（对应 output/skill/report_types/*.md）；传入后将自动映射 policy

    返回:
        report_path, docx_path, report_text
    """
    raw_path = Path(raw_path)
    report_path = Path(report_path)
    if not raw_path.is_file():
        raise FileNotFoundError(f"原始语料不存在: {raw_path}")
    if not report_path.is_file():
        raise FileNotFoundError(f"报告不存在: {report_path}")

    base = output_basename or raw_path.stem
    raw_text = raw_path.read_text(encoding="utf-8", errors="replace")
    report_text = _read_report_text(report_path)

    profile = load_report_type_profile(report_type)
    resolved_policy = policy_name or profile.get("policy_name", "policy1")
    if policy_name == "policy1" and report_type:
        # 当显式指定报告类型但未指定自定义 policy 时，自动使用类型映射 policy
        resolved_policy = profile.get("policy_name", "policy1")
    title_suffix = profile.get("step7_title_suffix", "学术风格分析报告")

    skill_text, summary_text = _load_skill_and_summary(resolved_policy)

    _log("=" * 60)
    _log("Step7 学术风格分析报告：风格化处理")
    _log(
        f"原始语料: {raw_path.name} | 报告: {report_path.name} | "
        f"类型: {profile.get('display_name')} | Policy: {resolved_policy}"
    )
    _log("=" * 60)

    header, chapters = _parse_report_v1_chapters(report_text)
    if not chapters:
        _log("[警告] 未能解析章节，将整篇处理")
        chapters = [("正文", report_text)]

    raw_preview = raw_text[:POLICY_RAW_TOTAL_LIMIT] + ("\n\n[已截断]" if len(raw_text) > POLICY_RAW_TOTAL_LIMIT else "")

    t0 = time.time()
    body = _process_by_chapters(
        header,
        chapters,
        skill_text,
        summary_text,
        raw_preview,
        resolved_policy,
    )

    # 构建完整报告：更新标题为学术风格分析报告
    report_title = f"{base} {title_suffix}"
    first_line = header.split("\n")[0].strip() if header else ""
    if first_line.startswith("# "):
        header_new = header.replace(first_line, f"# {report_title}", 1)
    else:
        header_new = (f"# {report_title}\n\n" + header) if header else f"# {report_title}\n\n"
    report_out = f"{header_new}\n\n{body}".strip()

    _log(f"风格化完成，总耗时 {time.time()-t0:.1f}s")

    out_name = f"{base}_{title_suffix}"
    md_path = REPORT_DIR / f"{out_name}.md"
    md_path.write_text(report_out, encoding="utf-8")
    _log(f"已保存: {md_path.name}")

    docx_path = save_docx_safe(report_out, REPORT_DIR / f"{out_name}.docx")
    _log(f"Step7 完成：学术风格分析报告 (Word) 已保存 {docx_path.name}")

    return {
        "report_path": str(md_path),
        "docx_path": str(docx_path),
        "report_text": report_out,
    }


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Step7: 根据原始语料与报告，采用 Skill/summary 风格化，输出学术风格分析报告")
    parser.add_argument("raw", type=Path, help="原始语料路径，如 output/raw/gaojinsumei.txt")
    parser.add_argument("report", type=Path, help="最新版报告路径，如 output/reports/gaojinsumei_report_v4.docx")
    parser.add_argument("-o", "--output-base", default=None, help="输出文件名前缀")
    parser.add_argument("-p", "--policy", default="policy1", help="policy 子目录名，默认 policy1")
    parser.add_argument("-t", "--report-type", default=None, help="报告类型（对应 output/skill/report_types/*.md）")
    args = parser.parse_args()
    run_report_policy(args.raw, args.report, args.output_base, args.policy, args.report_type)
