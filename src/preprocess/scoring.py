# -*- coding: utf-8 -*-
"""TF-IDF 相关性打分 + TextRank 抽取式摘要。"""
from __future__ import annotations

import re
from typing import List

from src.preprocess.document import Document
from src.utils.log import log


def score_relevance(docs: List[Document]) -> List[Document]:
    """
    用 TF-IDF 对每篇文档打相关性分数。
    分数越高 = 与语料整体主题越相关。
    """
    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.metrics.pairwise import cosine_similarity
        import numpy as np
    except ImportError:
        log("  [警告] scikit-learn 未安装，跳过 TF-IDF 打分（pip install scikit-learn）")
        for doc in docs:
            doc.relevance_score = 1.0
        return docs

    if not docs:
        return docs

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
        # 语料太少或全是停用词
        for doc in docs:
            doc.relevance_score = 1.0
        return docs

    # 计算每篇与整体中心的余弦相似度
    centroid = tfidf_matrix.mean(axis=0)
    centroid = np.asarray(centroid)
    similarities = cosine_similarity(tfidf_matrix, centroid.reshape(1, -1)).flatten()

    for doc, score in zip(docs, similarities):
        doc.relevance_score = float(score)

    scores = [d.relevance_score for d in docs]
    log(f"  TF-IDF 打分: min={min(scores):.3f}, max={max(scores):.3f}, mean={sum(scores)/len(scores):.3f}")
    return docs


def _split_sentences(text: str) -> List[str]:
    """简单的句子分割（英文为主，兼容中文句号）。"""
    # 按英文句号、问号、感叹号、中文句号分割
    parts = re.split(r"(?<=[.!?。！？])\s+", text)
    sentences = []
    for p in parts:
        p = p.strip()
        if len(p) > 20:  # 过滤太短的碎片
            sentences.append(p)
    return sentences


def textrank_summary(doc: Document, num_sentences: int = 5) -> str:
    """
    对单篇文档做 TextRank 抽取式摘要。
    返回 top-N 句子组成的摘要文本。
    """
    try:
        import networkx as nx
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.metrics.pairwise import cosine_similarity
    except ImportError:
        # 降级：取前 N 句
        sentences = _split_sentences(doc.body)
        return " ".join(sentences[:num_sentences])

    sentences = _split_sentences(doc.body)
    if len(sentences) <= num_sentences:
        return " ".join(sentences)

    # TF-IDF 向量化句子
    try:
        vectorizer = TfidfVectorizer(stop_words="english")
        tfidf_matrix = vectorizer.fit_transform(sentences)
    except ValueError:
        return " ".join(sentences[:num_sentences])

    # 构建句子相似度图
    sim_matrix = cosine_similarity(tfidf_matrix)
    graph = nx.from_numpy_array(sim_matrix)

    # PageRank 打分
    scores = nx.pagerank(graph)

    # 选取 top-N 句子（保持原文顺序）
    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    top_indices = sorted([idx for idx, _ in ranked[:num_sentences]])

    return " ".join(sentences[i] for i in top_indices)
