# -*- coding: utf-8 -*-
"""文档聚类 + 代表文档选择 + 聚类摘要组装（Mode A 输出）。"""
from __future__ import annotations

from typing import List, Tuple

from src.preprocess.document import Document
from src.preprocess.scoring import textrank_summary
from src.utils.log import log


def cluster_documents(
    docs: List[Document],
    k_range: Tuple[int, int] = (3, 10),
    max_representatives: int = 3,
    num_summary_sentences: int = 5,
) -> str:
    """
    KMeans 聚类 + TextRank 摘要，返回 Mode A 输出文本。

    自动选择最佳 k（silhouette score），为每个簇：
    1. 选取代表文档（离簇中心最近）
    2. 生成 TextRank 摘要
    3. 提取关键段落（附来源标注）
    """
    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.cluster import KMeans
        from sklearn.metrics import silhouette_score
        import numpy as np
    except ImportError:
        log("  [警告] scikit-learn 未安装，跳过聚类（pip install scikit-learn）")
        return _fallback_output(docs, num_summary_sentences)

    if len(docs) <= 3:
        return _fallback_output(docs, num_summary_sentences)

    # TF-IDF 向量化
    corpus = [doc.body for doc in docs]
    vectorizer = TfidfVectorizer(
        max_features=10000,
        stop_words="english",
        min_df=2,
        max_df=0.95,
    )
    try:
        tfidf_matrix = vectorizer.fit_transform(corpus)
    except ValueError:
        return _fallback_output(docs, num_summary_sentences)

    # 自动选择 k（silhouette score）
    k_min, k_max = k_range
    k_max = min(k_max, len(docs) - 1)
    k_min = min(k_min, k_max)

    best_k = k_min
    best_score = -1.0

    for k in range(k_min, k_max + 1):
        km = KMeans(n_clusters=k, random_state=42, n_init=10)
        labels = km.fit_predict(tfidf_matrix)
        if len(set(labels)) < 2:
            continue
        score = silhouette_score(tfidf_matrix, labels)
        if score > best_score:
            best_score = score
            best_k = k

    log(f"  聚类: 最佳 k={best_k}, silhouette={best_score:.3f}")

    # 执行最终聚类
    km = KMeans(n_clusters=best_k, random_state=42, n_init=10)
    labels = km.fit_predict(tfidf_matrix)

    for doc, label in zip(docs, labels):
        doc.cluster_id = int(label)

    # 按簇组织
    clusters: dict[int, List[Document]] = {}
    for doc in docs:
        clusters.setdefault(doc.cluster_id, []).append(doc)

    # 为每个簇选代表文档（离簇中心最近）
    from sklearn.metrics.pairwise import cosine_similarity

    output_parts = []
    total_original = len(docs)
    total_chars = sum(d.char_count for d in docs)

    output_parts.append("# 语料预处理报告")
    output_parts.append(f"- 有效文档: {total_original}")
    output_parts.append(f"- 聚类数: {best_k} | silhouette: {best_score:.3f}")
    output_parts.append("")
    output_parts.append("---")

    for cluster_id in sorted(clusters.keys()):
        cluster_docs = clusters[cluster_id]
        cluster_docs.sort(key=lambda d: d.relevance_score, reverse=True)

        # 选代表文档
        representatives = cluster_docs[:max_representatives]

        # 推断主题标签（用最常见的 title 关键词）
        titles = " ".join(d.title for d in cluster_docs if d.title)
        topic_label = titles[:80] if titles else f"主题 {cluster_id + 1}"

        output_parts.append("")
        output_parts.append(f"## {topic_label} ({len(cluster_docs)} 篇)")
        output_parts.append("")

        # TextRank 合并摘要
        output_parts.append("### 摘要")
        combined_body = "\n\n".join(d.body for d in representatives)
        temp_doc = Document(body=combined_body)
        temp_doc.compute_fields()
        summary = textrank_summary(temp_doc, num_summary_sentences)
        output_parts.append(summary)
        output_parts.append("")

        # 关键段落（附来源标注）
        output_parts.append("### 关键段落")
        for rep in representatives:
            # 取 relevance 最高的段落
            paragraphs = [p.strip() for p in rep.body.split("\n\n") if len(p.strip()) > 100]
            if paragraphs:
                best_para = max(paragraphs, key=len)[:500]
                output_parts.append(f"> [来源: {rep.source_label}] {best_para}")
                output_parts.append("")

        output_parts.append("---")

    output_text = "\n".join(output_parts)
    compression = (1 - len(output_text) / total_chars) * 100 if total_chars else 0
    # 在报告头部插入压缩率
    output_text = output_text.replace(
        f"- 聚类数: {best_k}",
        f"- 聚类数: {best_k} | 压缩率: {compression:.0f}%",
        1,
    )

    log(f"  Mode A 输出: {len(output_text):,} 字符, 压缩率 {compression:.0f}%")
    return output_text


def _fallback_output(docs: List[Document], num_sentences: int = 5) -> str:
    """无法聚类时的降级输出：直接拼接摘要。"""
    parts = ["# 语料预处理报告（降级模式）", f"- 文档数: {len(docs)}", "", "---", ""]
    for doc in docs:
        summary = textrank_summary(doc, num_sentences)
        parts.append(f"## {doc.title or doc.filename}")
        parts.append(f"> [来源: {doc.source_label}]")
        parts.append(summary)
        parts.append("")
        parts.append("---")
    return "\n".join(parts)
