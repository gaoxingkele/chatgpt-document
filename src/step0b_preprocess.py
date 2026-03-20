# -*- coding: utf-8 -*-
"""
Step0b 本地语料预处理：去重/过滤/压缩，零 API 调用。
支持 Mode A（摘要+聚类）和 Mode B（知识图谱）。
"""
import time
from pathlib import Path

from config import (
    RAW_DIR,
    PREPROCESS_MIN_BODY_CHARS,
    PREPROCESS_NEAR_DEDUP_THRESHOLD,
    PREPROCESS_PARAGRAPH_DEDUP_THRESHOLD,
    PREPROCESS_TEXTRANK_SENTENCES,
    PREPROCESS_CLUSTER_RANGE,
    PREPROCESS_MAX_REPRESENTATIVES,
    PREPROCESS_MINHASH_PERMS,
)
from src.preprocess.parser import load_corpus_dir, load_index_csv
from src.preprocess.filter import filter_by_status, filter_short, remove_boilerplate
from src.preprocess.dedup import dedup_exact, dedup_near, dedup_paragraphs
from src.preprocess.scoring import score_relevance
from src.utils.log import log


def run_preprocess(
    dir_path: Path,
    output_name: str,
    mode: str = "A",
    recursive: bool = False,
) -> Path:
    """
    Step0b 本地预处理。返回处理后语料文件路径。

    Args:
        dir_path: 语料目录
        output_name: 输出文件名前缀
        mode: "A"（摘要+聚类）、"B"（知识图谱）或 "AB"（融合）
        recursive: 是否递归读取子目录

    Returns:
        Path: output/raw/{output_name}_preprocessed.txt
    """
    t_start = time.time()
    mode = mode.upper()
    log(f"Step0b 预处理开始: {dir_path.name}, Mode {mode}")

    # ========== 共享流水线 ==========

    # 1. 解析全部 .txt 文件
    docs = load_corpus_dir(dir_path, recursive)
    if not docs:
        raise ValueError(f"目录 {dir_path} 中未找到有效 .txt 文件")
    original_count = len(docs)
    original_chars = sum(d.char_count for d in docs)

    # 2. 按 _index.csv status 过滤
    index = load_index_csv(dir_path)
    docs = filter_by_status(docs, index)

    # 3. 短文过滤
    docs = filter_short(docs, PREPROCESS_MIN_BODY_CHARS)

    # 4. boilerplate 清洗
    docs = remove_boilerplate(docs)

    # 5. MD5 精确去重
    docs = dedup_exact(docs)

    # 6. MinHash 近似去重
    docs = dedup_near(docs, PREPROCESS_NEAR_DEDUP_THRESHOLD, PREPROCESS_MINHASH_PERMS)

    # 7. 段落级去重
    docs = dedup_paragraphs(docs, PREPROCESS_PARAGRAPH_DEDUP_THRESHOLD)

    # 8. TF-IDF 相关性打分
    docs = score_relevance(docs)

    log(f"共享流水线完成: {original_count} → {len(docs)} 篇文档")

    # ========== 模式分支 ==========

    if mode == "AB":
        text_a = _run_mode_a(docs)
        text_b = _run_mode_b(docs)
        output_text = text_a + "\n\n" + "=" * 60 + "\n\n" + text_b
    elif mode == "B":
        output_text = _run_mode_b(docs)
    else:
        output_text = _run_mode_a(docs)

    # ========== 输出 ==========

    output_path = RAW_DIR / f"{output_name}_preprocessed.txt"
    output_path.write_text(output_text, encoding="utf-8")

    elapsed = time.time() - t_start
    final_chars = len(output_text)
    compression = (1 - final_chars / original_chars) * 100 if original_chars else 0

    log(f"Step0b 完成: {output_path.name}")
    log(f"  原始: {original_count} 篇, {original_chars:,} 字符")
    log(f"  输出: {final_chars:,} 字符, 压缩率 {compression:.0f}%")
    log(f"  耗时: {elapsed:.1f}s")

    return output_path


def _run_mode_a(docs):
    """Mode A: 聚类 + TextRank 摘要。"""
    from src.preprocess.clustering import cluster_documents

    log("Mode A: 聚类 + TextRank 摘要")
    return cluster_documents(
        docs,
        k_range=PREPROCESS_CLUSTER_RANGE,
        max_representatives=PREPROCESS_MAX_REPRESENTATIVES,
        num_summary_sentences=PREPROCESS_TEXTRANK_SENTENCES,
    )


def _run_mode_b(docs):
    """Mode B: 知识图谱。"""
    from src.preprocess.knowledge_graph import (
        extract_entities,
        extract_relationships,
        resolve_entities,
        build_knowledge_graph,
    )

    log("Mode B: 知识图谱")

    # 9. NER 实体抽取
    entities = extract_entities(docs)

    # 10. 关系抽取
    relations = extract_relationships(docs)

    # 11. 实体合并
    entities = resolve_entities(entities)

    # 12. 构建知识图谱输出
    return build_knowledge_graph(docs, entities, relations)
