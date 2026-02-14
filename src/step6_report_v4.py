# -*- coding: utf-8 -*-
"""
Step6: 对报告 3.0 进行事实核查与出处标注，生成报告 4.0。
- 按章节顺序将每章内容提交给 Perplexity API
- Perplexity 自动分析实体、事件、数据等事实并标注引用
- 引用编码按章节顺序递增，调用次数 = 章节数
"""
import re
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config import REPORT_DIR
from src.llm_client import perplexity_chat_with_citations
from src.step4_report_v2 import _parse_report_v1_chapters, md_to_docx


def _read_report_text(path: Path) -> str:
    """读取报告内容，支持 .md 和 .docx。"""
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix == ".docx":
        from docx import Document
        doc = Document(path)
        lines = []
        for p in doc.paragraphs:
            t = p.text.strip()
            if not t:
                lines.append("")
                continue
            style = (p.style.name or "").lower()
            if "heading 1" in style:
                lines.append(f"# {t}")
            elif "heading 2" in style:
                lines.append(f"## {t}")
            elif "heading 3" in style:
                lines.append(f"### {t}")
            else:
                lines.append(t)
        return "\n".join(lines)
    return path.read_text(encoding="utf-8", errors="replace")


def _log(msg: str):
    ts = time.strftime("%H:%M:%S", time.localtime())
    print(f"[{ts}] {msg}", flush=True)


def _process_chapter_with_perplexity(chapter_title: str, chapter_body: str) -> tuple[str, list[dict]]:
    """
    将单章内容提交给 Perplexity，让其分析事实、实体、事件并标注引用。
    返回 (带 [1],[2],... 标记的章节正文, 引用列表 [{"url","title"}, ...])
    """
    prompt = f"""请分析以下章节内容，完成以下任务：

1. **识别需要出处核查的陈述**：包括具体数据、比例、金额、人物、机构名称、行业标准、技术参数、可验证的事实性陈述。
2. **检索并标注引用**：利用你的检索能力，为上述陈述找到可靠的外部来源，在对应位置插入引用标记 [1]、[2]、[3]...（按首次出现顺序编号）。
3. **输出格式**：直接输出修改后的完整章节，包含：
   - 章标题：{chapter_title}
   - 正文：在需要引用的陈述后插入空格和 [n]
   - 不要添加额外的 References 小节（我会统一汇总）

对于无法找到公开来源的项目内部设计或假设性内容，可不标注。优先使用权威媒体、官方文档、学术来源。

【章节内容】
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


def _format_references(ref_list: list[dict]) -> str:
    """生成 References 小节 Markdown。"""
    lines = ["## References\n"]
    for i, r in enumerate(ref_list, 1):
        url = r.get("url", "")
        title = r.get("title", url)
        lines.append(f"[{i}] {title}. {url}")
    return "\n".join(lines)


def run_report_v4(report_v3_path: Path, output_basename: str = None) -> dict:
    """
    对报告 3.0 做事实核查与引用标注，生成报告 4.0。
    按章节顺序提交给 Perplexity，由 Perplexity 自动分析并标注引用。
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
        body_chunk = ch_body[:12000] + ("\n\n[已截断]" if len(ch_body) > 12000 else "")

        revised, citations = _process_chapter_with_perplexity(ch_title, body_chunk)

        # 按顺序追加引用（与正文 [1],[2] 一一对应，保持编号正确）
        for c in citations:
            url = (c.get("url") or "").strip()
            if url:
                ref_list.append({"url": url, "title": c.get("title") or url})

        n_refs_this_chapter = len(citations)
        # 重编号：本章的 [1],[2],... 改为 [ref_offset+1],[ref_offset+2],...
        revised = _renumber_citation_markers(revised, ref_offset)
        ref_offset += n_refs_this_chapter

        # 确保以章标题开头
        if not revised.strip().startswith("##"):
            revised = f"## {ch_title}\n\n{revised}"

        revised_parts.append(revised)
        _log(f"    完成，本章 {n_refs_this_chapter} 个引用")

        if idx < num_chapters - 1:
            time.sleep(1.5)

    report_v4_body = "\n\n".join(revised_parts)

    # 拼接：头部 + 正文 + References
    refs_section = _format_references(ref_list)
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

    # 保存 Markdown
    report_v4_path = REPORT_DIR / f"{base}_report_v4.md"
    report_v4_path.write_text(report_v4_text, encoding="utf-8")
    _log(f"报告 4.0 (Markdown) 已保存: {report_v4_path.name}")

    # 导出 Word
    docx_path = REPORT_DIR / f"{base}_report_v4.docx"
    try:
        md_to_docx(report_v4_text, docx_path)
    except PermissionError:
        docx_path = REPORT_DIR / f"{base}_report_v4_new.docx"
        md_to_docx(report_v4_text, docx_path)
        _log(f"[提示] 原文件可能被占用，已保存为: {docx_path.name}")
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
