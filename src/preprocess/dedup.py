# -*- coding: utf-8 -*-
"""去重：MD5 精确去重 + MinHash 近似去重 + 段落级跨文档去重。"""
from __future__ import annotations

import hashlib
import re
from typing import List, Set

from src.preprocess.document import Document
from src.utils.log import log


def dedup_exact(docs: List[Document]) -> List[Document]:
    """MD5 精确去重：完全相同的 body 只保留第一篇。"""
    seen: Set[str] = set()
    result = []
    for doc in docs:
        if doc.md5 not in seen:
            seen.add(doc.md5)
            result.append(doc)
    removed = len(docs) - len(result)
    if removed:
        log(f"  精确去重: {len(docs)} → {len(result)} （去掉 {removed} 篇完全重复）")
    return result


def _make_shingles(text: str, k: int = 5) -> Set[str]:
    """生成字符级 k-shingle 集合（对中英文混合都有效）。"""
    text = re.sub(r"\s+", " ", text.lower().strip())
    if len(text) < k:
        return {text}
    return {text[i : i + k] for i in range(len(text) - k + 1)}


def dedup_near(
    docs: List[Document],
    threshold: float = 0.85,
    num_perm: int = 128,
) -> List[Document]:
    """
    MinHash 近似去重：Jaccard 相似度超过阈值的文档只保留第一篇。
    使用 datasketch 库。
    """
    try:
        from datasketch import MinHash, MinHashLSH
    except ImportError:
        log("  [警告] datasketch 未安装，跳过近似去重（pip install datasketch）")
        return docs

    if len(docs) <= 1:
        return docs

    # 构建 MinHash
    minhashes = []
    for doc in docs:
        m = MinHash(num_perm=num_perm)
        for shingle in _make_shingles(doc.body):
            m.update(shingle.encode("utf-8"))
        minhashes.append(m)

    # LSH 索引
    lsh = MinHashLSH(threshold=threshold, num_perm=num_perm)
    keep_indices: Set[int] = set()
    drop_indices: Set[int] = set()

    for i, (doc, mh) in enumerate(zip(docs, minhashes)):
        if i in drop_indices:
            continue
        key = f"doc_{i}"
        # 查找已有的近似文档
        try:
            lsh.insert(key, mh)
        except ValueError:
            # 重复 key，跳过
            drop_indices.add(i)
            continue
        keep_indices.add(i)

    # 第二遍：用 LSH query 标记冗余
    keep_indices.clear()
    drop_indices.clear()
    lsh2 = MinHashLSH(threshold=threshold, num_perm=num_perm)

    for i, mh in enumerate(minhashes):
        if i in drop_indices:
            continue
        # 查询是否有相似文档已入库
        candidates = lsh2.query(mh)
        if candidates:
            drop_indices.add(i)
        else:
            try:
                lsh2.insert(f"doc_{i}", mh)
                keep_indices.add(i)
            except ValueError:
                drop_indices.add(i)

    result = [docs[i] for i in sorted(keep_indices)]
    removed = len(docs) - len(result)
    if removed:
        log(f"  近似去重: {len(docs)} → {len(result)} （去掉 {removed} 篇近似重复，阈值 {threshold}）")
    return result


def dedup_paragraphs(
    docs: List[Document],
    threshold: float = 0.90,
    min_para_len: int = 100,
) -> List[Document]:
    """
    段落级跨文档去重：去除跨文档中重复出现的段落。
    使用简单的段落 MD5 指纹。
    """
    # 第一遍：收集所有段落指纹，统计出现次数
    para_count: dict[str, int] = {}

    for doc in docs:
        paragraphs = re.split(r"\n\s*\n", doc.body)
        seen_in_doc: Set[str] = set()
        for para in paragraphs:
            para = para.strip()
            if len(para) < min_para_len:
                continue
            fingerprint = hashlib.md5(para.encode("utf-8")).hexdigest()
            if fingerprint not in seen_in_doc:
                seen_in_doc.add(fingerprint)
                para_count[fingerprint] = para_count.get(fingerprint, 0) + 1

    # 找出在多篇文档中出现的段落
    duplicate_fps = {fp for fp, count in para_count.items() if count > 1}

    if not duplicate_fps:
        return docs

    # 第二遍：从每篇文档中去除重复段落（保留首次出现）
    seen_global: Set[str] = set()
    total_removed = 0

    for doc in docs:
        paragraphs = re.split(r"\n\s*\n", doc.body)
        kept = []
        for para in paragraphs:
            stripped = para.strip()
            if len(stripped) < min_para_len:
                kept.append(para)
                continue
            fingerprint = hashlib.md5(stripped.encode("utf-8")).hexdigest()
            if fingerprint in duplicate_fps and fingerprint in seen_global:
                total_removed += 1
                continue
            seen_global.add(fingerprint)
            kept.append(para)
        doc.body = "\n\n".join(kept)
        doc.char_count = len(doc.body)

    if total_removed:
        log(f"  段落去重: 移除 {total_removed} 个跨文档重复段落")
    return docs
