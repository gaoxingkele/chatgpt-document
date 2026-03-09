# -*- coding: utf-8 -*-
"""Markdown 解析工具：章节拆分、docx 读取转 Markdown。"""
import re
from pathlib import Path


def parse_report_chapters(text: str) -> tuple[str, list[tuple[str, str]]]:
    """
    解析报告：提取正文前的头部（标题、摘要、关键词），及章节列表 [(章标题, 章正文), ...]。
    章标题匹配 ## 一、 ## 二、 ... 或 ## 1. ## 2. ...
    """
    pattern = re.compile(r"^##\s+[一二三四五六七八九十]+、.+$|^##\s+\d+\.\s+.+$", re.MULTILINE)
    matches = list(pattern.finditer(text))
    if not matches:
        return text, []

    header = text[: matches[0].start()].strip()
    chapters: list[tuple[str, str]] = []
    for i, m in enumerate(matches):
        title = m.group(0).strip()
        body_start = m.end()
        body_end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[body_start:body_end].strip()
        chapters.append((title, body))
    return header, chapters


def read_report_text(path: Path) -> str:
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
