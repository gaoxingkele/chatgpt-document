# -*- coding: utf-8 -*-
"""
Step4: 根据专家意见与原始语料，对报告 1.0 整改生成报告 2.0；
要求：保留 ChatGPT 论述逻辑、5~7 章、去重简练、专业严谨；输出 Markdown 与 Word。
"""
import time
from pathlib import Path

import src  # noqa: F401  — 确保 PROJECT_ROOT 加入 sys.path

from config import (
    REPORT_DIR, EXPERT_DIR, RAW_DIR,
    HALLUCINATION_TEXT_LIMIT,
    REVISE_RAW_CHUNK_LIMIT, REVISE_EXPERT_LIMIT, REVISE_CHAPTER_BODY_LIMIT,
)
from src.llm_client import chat
from src.utils.log import log as _log
from src.utils.markdown_utils import parse_report_chapters as _parse_report_v1_chapters
from src.utils.docx_utils import md_to_docx
from src.utils.parallel import parallel_map


def _load_expert_combined(base: str) -> str:
    p = EXPERT_DIR / f"{base}_专家意见汇总.md"
    if not p.is_file():
        raise FileNotFoundError(f"专家意见汇总不存在: {p}，请先运行 Step3")
    return p.read_text(encoding="utf-8", errors="replace")


def _load_hallucination_list(base: str) -> str:
    """加载幻觉清单（若存在）。"""
    p = EXPERT_DIR / f"{base}_专家4_幻觉清单.md"
    if p.is_file():
        return p.read_text(encoding="utf-8", errors="replace")
    return ""


from src.utils.file_utils import load_raw_content as _load_raw_content


def _api_revise_chapter(
    chapter_title: str,
    chapter_body: str,
    expert_text: str,
    hallucination_text: str,
    raw_chunk: str,
    target_chars: int,
    chapter_idx: int,
    total_chapters: int,
) -> str:
    """对单章进行整改，返回该章完整正文（含章标题）。强调篇幅必须达标。"""
    hall_section = ""
    if hallucination_text:
        hall_section = f"""
【幻觉清单】必须删除以下内容，不得出现在本章：
{hallucination_text[:HALLUCINATION_TEXT_LIMIT]}
"""
    raw_section = ""
    if raw_chunk:
        raw_section = f"""
【原始语料】（供参考，优先保留论证、案例、数据）
---
{raw_chunk[:REVISE_RAW_CHUNK_LIMIT]}
---
"""
    prompt = f"""请对《深度调查报告 1.0》的**第 {chapter_idx}/{total_chapters} 章**进行整改，输出该章的完整正文。

【本章标题】{chapter_title}

【本章正文（报告 1.0）】
---
{chapter_body}
---

【专家评审意见】（采纳可执行的改进）
---
{expert_text[:REVISE_EXPERT_LIMIT]}
---
{hall_section}{raw_section}

【极其重要的篇幅要求（必须遵守）】
- 本章输出字数**不少于 {target_chars} 字**。禁止压缩、禁止将多段合并成一句或要点罗列。
- 重写、去重、理顺逻辑，但**不要删减论证、案例、表格、数据**。
- 直接输出本章完整正文，以 `## {chapter_title}` 开头，使用 Markdown（### 等）。不要 JSON 或多余说明。"""

    resp = chat(
        [
            {
                "role": "system",
                "content": "你是专业的研究报告修订专家。核心原则：1) 篇幅必须充足，每章不少于目标字数；2) 保留论述逻辑与案例丰富度；3) 重写而非压缩；4) 吸收专家意见。输出严格为 Markdown。",
            },
            {"role": "user", "content": prompt},
        ],
        max_tokens=16384,
        temperature=0.4,
    )
    return resp.strip()


def run_report_v2_and_docx(
    report_v1_path: Path,
    expert_combined_path: Path = None,
    output_basename: str = None,
    raw_path: Path = None,
) -> dict:
    """
    根据报告 1.0、专家意见汇总与（可选）原始语料，生成报告 2.0 的 Markdown，再转为 Word。
    返回 report_v2_path（.md）与 docx_path（.docx）。
    """
    report_v1_path = Path(report_v1_path)
    if not report_v1_path.is_file():
        raise FileNotFoundError(f"报告 1.0 不存在: {report_v1_path}")
    report_v1_text = report_v1_path.read_text(encoding="utf-8", errors="replace")
    base = output_basename or report_v1_path.stem.replace("_report_v1", "")

    if expert_combined_path and Path(expert_combined_path).is_file():
        expert_text = Path(expert_combined_path).read_text(encoding="utf-8", errors="replace")
    else:
        expert_text = _load_expert_combined(base)

    hallucination_text = _load_hallucination_list(base)
    if hallucination_text:
        _log(f"已加载幻觉清单，共约 {len(hallucination_text)} 字")

    raw_text = _load_raw_content(raw_path, 120000) if raw_path else ""
    raw_full_len = len(Path(raw_path).read_text(encoding="utf-8", errors="replace")) if raw_path and Path(raw_path).is_file() else len(raw_text)
    target_min_chars = max(16000, int(raw_full_len * 0.6))

    header, chapters = _parse_report_v1_chapters(report_v1_text)
    num_chapters = len(chapters)
    target_per_chapter = max(2000, target_min_chars // num_chapters) if num_chapters else target_min_chars

    _log("=" * 60)
    _log("Step4 报告 2.0：开始（分章整改模式）")
    _log(f"报告 1.0: 约 {len(report_v1_text)} 字 | 原始语料: 约 {raw_full_len} 字 | 字数目标: ≥{target_min_chars} 字")
    _log(f"章节数: {num_chapters} | 每章目标: ≥{target_per_chapter} 字")
    _log("=" * 60)
    t0 = time.time()

    raw_len = len(raw_text)

    def _revise_one(idx, chapter):
        ch_title, ch_body = chapter
        _log(f"[并行] 整改第 {idx + 1}/{num_chapters} 章: {ch_title[:40]}...")
        start_pos = idx * raw_len // num_chapters if raw_len else 0
        end_pos = (idx + 1) * raw_len // num_chapters if raw_len else raw_len
        raw_chunk = raw_text[start_pos:end_pos] if raw_text else ""
        revised = _api_revise_chapter(
            ch_title,
            ch_body[:REVISE_CHAPTER_BODY_LIMIT],
            expert_text,
            hallucination_text,
            raw_chunk,
            target_per_chapter,
            idx + 1,
            num_chapters,
        )
        _log(f"[并行] 第 {idx + 1} 章完成，输出约 {len(revised)} 字")
        return revised

    revised_parts = parallel_map(_revise_one, chapters)

    # 拼接：头部 + 各章
    report_v2_body = "\n\n".join(revised_parts)
    report_v2_text = f"{header}\n\n{report_v2_body}".strip()

    _log(f"分章整改完成，总耗时 {time.time()-t0:.1f}s，报告 2.0 约 {len(report_v2_text)} 字")

    report_v2_path = REPORT_DIR / f"{base}_report_v2.md"
    report_v2_path.write_text(report_v2_text, encoding="utf-8")
    _log(f"报告 2.0 (Markdown) 已保存: {report_v2_path.name}")

    # 转为 Word：标题层级字号与粗体，正文段落与列表
    _log("导出 Word：报告 2.0 → .docx")
    docx_path = REPORT_DIR / f"{base}_report_v2.docx"
    try:
        md_to_docx(report_v2_text, docx_path)
    except PermissionError:
        alt_path = REPORT_DIR / f"{base}_report_v2_new.docx"
        md_to_docx(report_v2_text, alt_path)
        docx_path = alt_path
        _log(f"[提示] 原文件可能被占用，已保存为: {docx_path.name}")
    _log(f"Step4 完成：报告 2.0 (Word) 已保存 {docx_path.name}")

    return {
        "report_v2_path": str(report_v2_path),
        "docx_path": str(docx_path),
        "report_v2_text": report_v2_text,
    }


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="根据专家意见生成报告2.0并导出Word")
    parser.add_argument("report_v1", type=Path, help="报告 1.0 路径")
    parser.add_argument("-e", "--expert-file", type=Path, default=None, help="专家意见汇总路径（可选）")
    parser.add_argument("-r", "--raw-file", type=Path, default=None, help="原始语料路径（可选，用于补充论述逻辑）")
    parser.add_argument("-o", "--output-base", default=None, help="输出文件名前缀")
    args = parser.parse_args()
    raw = Path(args.raw_file) if args.raw_file else None
    if raw and not raw.is_absolute():
        raw = RAW_DIR / raw.name
    run_report_v2_and_docx(args.report_v1, args.expert_file, args.output_base, raw)
