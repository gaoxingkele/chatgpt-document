# -*- coding: utf-8 -*-
"""
语料提取：Word、PDF、图片等格式。
Word/PDF 本地提取文本；图片提交云端 Vision API 处理。
"""
import base64
from pathlib import Path
from typing import Callable, Optional


def _get_vision_api() -> Callable[[list], str]:
    from src.kimi_client import chat_vision
    return chat_vision


def extract_from_docx(file_path: Path) -> str:
    """从 Word (.docx) 提取文本。"""
    from docx import Document
    doc = Document(file_path)
    parts = []
    for p in doc.paragraphs:
        if p.text.strip():
            parts.append(p.text.strip())
    for table in doc.tables:
        for row in table.rows:
            cells = [c.text.strip() for c in row.cells if c.text.strip()]
            if cells:
                parts.append(" | ".join(cells))
    return "\n\n".join(parts)


def extract_from_pdf(file_path: Path) -> str:
    """从 PDF 提取文本。"""
    try:
        from pypdf import PdfReader
    except ImportError:
        try:
            from PyPDF2 import PdfReader
        except ImportError:
            raise ImportError("请安装 pypdf: pip install pypdf")
    reader = PdfReader(file_path)
    parts = []
    for page in reader.pages:
        text = page.extract_text()
        if text and text.strip():
            parts.append(text.strip())
    return "\n\n".join(parts)


def extract_from_image(file_path: Path, vision_api: Optional[Callable[[list], str]] = None) -> str:
    """
    从图片提取内容：编码为 base64 后提交云端 Vision API 处理。
    vision_api: 接受 messages 列表，返回文本；未传入则使用 kimi_client.chat_vision。
    """
    if vision_api is None:
        vision_api = _get_vision_api()
    path = Path(file_path)
    raw = path.read_bytes()
    b64 = base64.b64encode(raw).decode("ascii")
    suffix = path.suffix.lower()
    mime = {
        ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
        ".png": "image/png", ".gif": "image/gif",
        ".webp": "image/webp", ".bmp": "image/bmp",
    }.get(suffix, "image/jpeg")
    data_url = f"data:{mime};base64,{b64}"

    content = [
        {
            "type": "text",
            "text": "请提取此图片中的全部文字、图表、表格及关键信息，输出为可直接用于语料整理的纯文本。若为截图或文档图片，请完整还原文字内容。",
        },
        {"type": "image_url", "image_url": {"url": data_url}},
    ]
    messages = [
        {"role": "system", "content": "你是专业的内容提取专家。任务：从图片中提取全部可读文字与关键信息，输出为结构清晰的纯文本，便于后续语料整理。"},
        {"role": "user", "content": content},
    ]
    return vision_api(messages)
