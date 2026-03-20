# -*- coding: utf-8 -*-
"""
Step6: 对报告 3.0 进行事实核查与出处标注，生成报告 4.0。
- 按章节顺序将每章内容提交给 Perplexity API
- Perplexity 自动分析实体、事件、数据等事实并标注引用
- 引用编码按章节顺序递增，调用次数 = 章节数
"""
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import src  # noqa: F401  — 确保 PROJECT_ROOT 加入 sys.path

from config import REPORT_DIR, CITATION_CHAPTER_BODY_LIMIT, STEP6_CHAPTER_DELAY
from src.llm_client import perplexity_chat_with_citations
from src.utils.markdown_utils import parse_report_chapters as _parse_report_v1_chapters, read_report_text as _read_report_text
from src.utils.docx_utils import save_docx_safe
from src.utils.log import log as _log


def _process_chapter_with_perplexity(chapter_title: str, chapter_body: str) -> tuple[str, list[dict]]:
    """
    将单章内容提交给 Perplexity，让其分析事实、实体、事件并标注引用。
    返回 (带 [1],[2],... 标记的章节正文, 引用列表 [{"url","title"}, ...])
    """
    prompt = f"""请对以下章节进行事实核查，但**不要在正文中插入任何 [n] 引用标记**。

任务：
1. 核查章节中的关键事实（数据、人物、事件、机构）
2. 搜索可靠的外部来源验证这些事实
3. **原样输出章节正文**，不做任何修改、不插入引用标记
4. 引用来源会通过 API 的 citations 字段自动返回，无需在正文中标注

重要：保持章节正文的原始可读性，不要添加 [1]、[2] 等标记。数学公式 $...$ 和 $$...$$ 原样保留。

【章节内容】
## {chapter_title}

{chapter_body}
"""
    try:
        content, citations = perplexity_chat_with_citations(
            [{"role": "user", "content": prompt}],
            max_tokens=8192,
            temperature=0.2,
        )
        return (content.strip(), citations)
    except Exception as e:
        _log(f"    Perplexity 调用失败: {e}")
        return (chapter_body, [])


def _renumber_citation_markers(text: str, offset: int) -> str:
    """将正文中的 [1],[2],... 重新编号为 [offset+1],[offset+2],..."""
    def repl(m):
        n = int(m.group(1))
        return f"[{offset + n}]"

    return re.sub(r"\[(\d+)\]", repl, text)


def _format_references(ref_list: list[dict], style: str = "numbered") -> str:
    """
    生成 References 小节 Markdown。
    style: "numbered" → [1] Title. URL
           "author_year" → [1] Author (Year). Title. URL
    """
    lines = ["## References\n"]
    for i, r in enumerate(ref_list, 1):
        url = r.get("url", "")
        title = r.get("title", url)
        author = r.get("author", "")
        year = r.get("year", "")
        if style == "author_year" and (author or year):
            author_part = author or "Unknown"
            year_part = f" ({year})" if year else ""
            lines.append(f"[{i}] {author_part}{year_part}. {title}. {url}")
        else:
            lines.append(f"[{i}] {title}. {url}")
    return "\n".join(lines)


def _verify_citations(ref_list: list[dict], timeout: float = 10.0) -> list[dict]:
    """并行 HTTP HEAD 检查引用 URL 可达性，返回带 status 字段的列表。"""
    import urllib.request
    import urllib.error

    def _check_one(ref):
        url = ref.get("url", "")
        if not url:
            return {**ref, "status": "unreachable"}
        try:
            req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return {**ref, "status": "ok", "http_code": resp.status}
        except (urllib.error.URLError, urllib.error.HTTPError, OSError, Exception):
            return {**ref, "status": "unreachable"}

    results = []
    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = {executor.submit(_check_one, r): i for i, r in enumerate(ref_list)}
        indexed = [None] * len(ref_list)
        for future in as_completed(futures):
            i = futures[future]
            indexed[i] = future.result()
        results = indexed
    return results


def _mark_unverified_in_text(report_text: str, unverified_indices: list[int]) -> str:
    """将不可达引用的 [N] 标记替换为 [N 待验证]。"""
    for idx in unverified_indices:
        report_text = report_text.replace(f"[{idx}]", f"[{idx} 待验证]")
    return report_text


def run_report_v4(
    report_v3_path: Path,
    output_basename: str = None,
    skip_citation_verify: bool = False,
    citation_style: str = "numbered",
) -> dict:
    """
    对报告 3.0 做事实核查与引用标注，生成报告 4.0。
    按章节顺序提交给 Perplexity，由 Perplexity 自动分析并标注引用。
    citation_style: "numbered" → [1] Title. URL
                    "author_year" → [1] Author (Year). Title. URL
    返回 report_v4_path（.md）、docx_path（.docx）、report_v4_text。
    """
    report_v3_path = Path(report_v3_path)
    if not report_v3_path.is_file():
        raise FileNotFoundError(f"报告 3.0 不存在: {report_v3_path}")

    base = output_basename or report_v3_path.stem.replace("_report_v3", "")
    report_text = _read_report_text(report_v3_path)

    header, chapters = _parse_report_v1_chapters(report_text)
    num_chapters = len(chapters)

    _log("=" * 60)
    _log("Step6 报告 4.0：按章节事实核查与引用标注")
    _log(f"输入: {report_v3_path.name} | 章节数: {num_chapters}")
    _log("=" * 60)

    ref_list: list[dict] = []
    revised_parts: list[str] = []
    ref_offset = 0

    for idx, (ch_title, ch_body) in enumerate(chapters):
        _log(f"--- 处理第 {idx + 1}/{num_chapters} 章: {ch_title[:50]}...")

        # 单章不宜过长，截断以保证在上下文限制内
        body_chunk = ch_body[:CITATION_CHAPTER_BODY_LIMIT] + ("\n\n[已截断]" if len(ch_body) > CITATION_CHAPTER_BODY_LIMIT else "")

        revised, citations = _process_chapter_with_perplexity(ch_title, body_chunk)

        # 收集引用来源（不在正文插标记）
        for c in citations:
            url = (c.get("url") or "").strip()
            if url:
                ref_list.append({"url": url, "title": c.get("title") or url})

        n_refs_this_chapter = len(citations)
        # 清理 LLM 可能仍然插入的 [n] 标记
        revised = re.sub(r"\s*\[\d+\]", "", revised)

        # 确保以章标题开头
        if not revised.strip().startswith("##"):
            revised = f"## {ch_title}\n\n{revised}"

        revised_parts.append(revised)
        _log(f"    完成，本章 {n_refs_this_chapter} 个引用")

        if idx < num_chapters - 1:
            time.sleep(STEP6_CHAPTER_DELAY)

    report_v4_body = "\n\n".join(revised_parts)

    # 拼接：头部 + 正文 + References
    refs_section = _format_references(ref_list, style=citation_style)
    report_v4_text = f"{header}\n\n{report_v4_body}".strip()

    # 更新版本号
    report_v4_text = re.sub(
        r"3\.0\s*最终版|研究报告\s*3\.0|报告\s*3\.0",
        "4.0（含引用）",
        report_v4_text,
        count=1,
    )

    if ref_list:
        report_v4_text = report_v4_text.rstrip() + "\n\n---\n\n" + refs_section

    _log(f"共获得 {len(ref_list)} 个引用来源")

    # 引用验证
    if ref_list and not skip_citation_verify:
        _log("Step6 引用验证：并行检查 URL 可达性...")
        verified_refs = _verify_citations(ref_list)
        unverified = [i + 1 for i, r in enumerate(verified_refs) if r.get("status") != "ok"]
        if unverified:
            _log(f"    {len(unverified)} 个引用不可达，标记为 [N 待验证]")
            report_v4_text = _mark_unverified_in_text(report_v4_text, unverified)
        else:
            _log("    全部引用验证通过")

        # 保存验证结果
        cite_check_path = REPORT_DIR / f"{base}_citation_check.json"
        cite_check_path.write_text(
            json.dumps(verified_refs, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        _log(f"    验证结果已保存: {cite_check_path.name}")

    # 保存 Markdown
    report_v4_path = REPORT_DIR / f"{base}_report_v4.md"
    report_v4_path.write_text(report_v4_text, encoding="utf-8")
    _log(f"报告 4.0 (Markdown) 已保存: {report_v4_path.name}")

    # 导出 Word
    docx_path = save_docx_safe(report_v4_text, REPORT_DIR / f"{base}_report_v4.docx")
    _log(f"Step6 完成：报告 4.0 (Word) 已保存 {docx_path.name}")

    return {
        "report_v4_path": str(report_v4_path),
        "docx_path": str(docx_path),
        "report_v4_text": report_v4_text,
    }


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="对报告 3.0 做事实核查与引用，生成报告 4.0（按章节提交 Perplexity）")
    parser.add_argument("report_v3", type=Path, help="报告 3.0 路径")
    parser.add_argument("-o", "--output-base", default=None, help="输出文件名前缀")
    args = parser.parse_args()
    run_report_v4(args.report_v3, args.output_base)
