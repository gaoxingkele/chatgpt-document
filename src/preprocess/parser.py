# -*- coding: utf-8 -*-
"""解析 kateer 格式语料文件：结构化 header + body，支持 _index.csv。"""
from __future__ import annotations

import csv
import re
from pathlib import Path
from typing import Dict, List, Optional

from src.preprocess.document import Document
from src.utils.log import log


# metadata header 字段名映射（大小写不敏感）
_HEADER_FIELDS = {
    "url": "url",
    "title": "title",
    "source": "source",
    "category": "category",
    "published": "published",
    "description": "description",
}

# 分隔线模式：连续 4 个以上 = 号
_SEPARATOR_RE = re.compile(r"^={4,}\s*$", re.MULTILINE)


def parse_document(filepath: Path) -> Document:
    """解析单个 .txt 文件为 Document 对象。"""
    text = filepath.read_text(encoding="utf-8", errors="replace")
    doc = Document(filepath=filepath, filename=filepath.name)

    # 查找分隔线
    match = _SEPARATOR_RE.search(text)
    if match:
        header_text = text[: match.start()]
        doc.body = text[match.end() :].strip()
    else:
        # 无分隔线，整个文件视为 body
        doc.body = text.strip()
        doc.compute_fields()
        return doc

    # 解析 header 中的 key: value 行
    for line in header_text.splitlines():
        line = line.strip()
        if not line or ":" not in line:
            continue
        key, _, value = line.partition(":")
        key_lower = key.strip().lower()
        if key_lower in _HEADER_FIELDS:
            setattr(doc, _HEADER_FIELDS[key_lower], value.strip())

    doc.compute_fields()
    return doc


def load_index_csv(dir_path: Path) -> Optional[Dict[str, str]]:
    """
    读取 _index.csv，返回 {filename: status} 映射。
    如果不存在则返回 None。
    """
    csv_path = dir_path / "_index.csv"
    if not csv_path.is_file():
        return None

    index = {}
    with open(csv_path, encoding="utf-8", errors="replace", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            # 尝试常见列名
            fname = row.get("filename") or row.get("file") or row.get("name") or ""
            status = row.get("status") or row.get("Status") or ""
            if fname:
                index[fname.strip()] = status.strip().lower()
    return index


def load_corpus_dir(
    dir_path: Path,
    recursive: bool = False,
) -> List[Document]:
    """
    批量加载目录下所有 .txt 文件为 Document 列表。
    跳过 _index.csv 等非语料文件。
    """
    if not dir_path.is_dir():
        raise FileNotFoundError(f"语料目录不存在: {dir_path}")

    pattern = "**/*.txt" if recursive else "*.txt"
    txt_files = sorted(dir_path.glob(pattern))

    # 过滤掉 _index.csv 和隐藏文件
    txt_files = [
        f for f in txt_files
        if not f.name.startswith("_") and not f.name.startswith(".")
    ]

    log(f"发现 {len(txt_files)} 个 .txt 文件")

    docs = []
    for fp in txt_files:
        try:
            doc = parse_document(fp)
            docs.append(doc)
        except Exception as e:
            log(f"  跳过 {fp.name}: {e}")

    log(f"成功解析 {len(docs)} 个文档")
    return docs
