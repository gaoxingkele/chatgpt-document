# -*- coding: utf-8 -*-
"""Document 数据模型：统一表示一篇语料文档。"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional


@dataclass
class Document:
    """一篇语料文档，包含 metadata + body + 计算字段。"""

    # 来源
    filepath: Path = field(default_factory=lambda: Path())
    filename: str = ""

    # metadata（从 header 解析）
    url: str = ""
    title: str = ""
    source: str = ""
    category: str = ""
    published: str = ""
    description: str = ""

    # 正文
    body: str = ""

    # 计算字段（延迟填充）
    md5: str = ""
    char_count: int = 0
    relevance_score: float = 0.0
    cluster_id: int = -1
    summary: str = ""

    def compute_fields(self) -> None:
        """计算 MD5 和字符数。"""
        self.char_count = len(self.body)
        self.md5 = hashlib.md5(self.body.encode("utf-8")).hexdigest()

    @property
    def source_label(self) -> str:
        """用于输出引用标注的来源标签（简洁格式，去掉 ISO 时间戳）。"""
        import re
        parts = []
        if self.source:
            parts.append(self.source)
        if self.published:
            # 只保留日期部分，去掉 T 后的时间和时区
            date_clean = re.sub(r"T\d{2}:\d{2}:\d{2}[+\-]\d{2}:\d{2}", "", self.published).strip()
            if date_clean:
                parts.append(date_clean)
        if not parts:
            parts.append(self.filename)
        return " ".join(parts)

    @property
    def published_date(self) -> Optional[datetime]:
        """尝试解析 published 字段为日期。"""
        for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%B %d, %Y", "%d %B %Y"):
            try:
                return datetime.strptime(self.published.strip(), fmt)
            except (ValueError, AttributeError):
                continue
        return None
