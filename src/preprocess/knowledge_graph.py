# -*- coding: utf-8 -*-
"""Mode B：spaCy NER + 关系抽取 + 实体合并 + 知识图谱序列化。"""
from __future__ import annotations

import re
from collections import Counter, defaultdict
from typing import Dict, List, Set, Tuple

from src.preprocess.document import Document
from src.utils.log import log


def _load_spacy():
    """延迟导入 spaCy，仅 Mode B 使用。"""
    try:
        import spacy
    except ImportError:
        raise ImportError(
            "Mode B 需要 spaCy：pip install spacy && python -m spacy download en_core_web_sm"
        )
    try:
        nlp = spacy.load("en_core_web_sm")
    except OSError:
        raise OSError(
            "spaCy 模型未下载：python -m spacy download en_core_web_sm"
        )
    return nlp


# 目标实体类型
_TARGET_LABELS = {"PERSON", "ORG", "GPE", "DATE", "QUANTITY", "NORP", "FAC", "EVENT"}


def extract_entities(docs: List[Document]) -> Dict[str, Dict]:
    """
    用 spaCy NER 从全部文档中抽取实体。
    返回: {entity_text: {label, count, docs: [filename, ...], contexts: [str, ...]}}
    """
    nlp = _load_spacy()
    entities: Dict[str, Dict] = {}

    for doc in docs:
        # spaCy 有长度限制，截取前 100K 字符
        text = doc.body[:100_000]
        spacy_doc = nlp(text)
        seen_in_doc: Set[str] = set()

        for ent in spacy_doc.ents:
            if ent.label_ not in _TARGET_LABELS:
                continue
            key = ent.text.strip()
            if len(key) < 2:
                continue

            if key not in entities:
                entities[key] = {
                    "label": ent.label_,
                    "count": 0,
                    "docs": [],
                    "contexts": [],
                }

            entities[key]["count"] += 1

            if key not in seen_in_doc:
                seen_in_doc.add(key)
                entities[key]["docs"].append(doc.filename)

            # 保存上下文（前后各 100 字符，最多 5 个）
            if len(entities[key]["contexts"]) < 5:
                start = max(0, ent.start_char - 100)
                end = min(len(text), ent.end_char + 100)
                context = text[start:end].replace("\n", " ").strip()
                entities[key]["contexts"].append(context)

    log(f"  NER 抽取: {len(entities)} 个实体")
    return entities


def extract_relationships(docs: List[Document]) -> List[Tuple[str, str, str]]:
    """
    基于依存句法模式抽取实体间关系。
    返回: [(subject, predicate, object), ...]
    """
    nlp = _load_spacy()
    relations: List[Tuple[str, str, str]] = []

    for doc in docs:
        text = doc.body[:100_000]
        spacy_doc = nlp(text)

        for sent in spacy_doc.sents:
            ents = [e for e in sent.ents if e.label_ in _TARGET_LABELS]
            if len(ents) < 2:
                continue

            # 简单模式：主语-谓语-宾语
            root = sent.root
            if root.pos_ == "VERB":
                subj_ents = [e for e in ents if _overlaps_subtree(e, root, "nsubj")]
                obj_ents = [e for e in ents if _overlaps_subtree(e, root, "dobj")]
                for s in subj_ents:
                    for o in obj_ents:
                        relations.append((s.text, root.lemma_, o.text))

            # 介词模式：A prep B
            for token in sent:
                if token.dep_ == "prep" and token.head.pos_ in ("VERB", "NOUN"):
                    pobj_ents = [
                        e for e in ents
                        if any(t.dep_ == "pobj" and t.head == token for t in e)
                    ]
                    head_ents = [
                        e for e in ents
                        if e.start <= token.head.i <= e.end
                    ]
                    for h in head_ents:
                        for p in pobj_ents:
                            relations.append((h.text, f"{token.head.lemma_} {token.text}", p.text))

    log(f"  关系抽取: {len(relations)} 条关系")
    return relations


def _overlaps_subtree(ent, root, dep_label: str) -> bool:
    """检查实体是否与 root 的某个依存子节点重叠。"""
    for child in root.children:
        if child.dep_ == dep_label:
            if ent.start <= child.i <= ent.end:
                return True
    return False


def resolve_entities(entities: Dict[str, Dict]) -> Dict[str, Dict]:
    """
    实体链接/合并：将别名映射到规范名。
    策略：
    1. 完全包含关系（"El Mencho" vs "Nemesio Oseguera Cervantes aka El Mencho"）
    2. 同一 label 的短名 → 长名合并
    """
    # 按出现频次降序排列
    sorted_ents = sorted(entities.items(), key=lambda x: x[1]["count"], reverse=True)

    canonical: Dict[str, str] = {}  # alias → canonical_name
    merged: Dict[str, Dict] = {}

    for name, info in sorted_ents:
        name_lower = name.lower().strip()

        # 检查是否是已有实体的别名
        found_canonical = None
        for canon_name in merged:
            canon_lower = canon_name.lower()
            if (
                name_lower in canon_lower
                or canon_lower in name_lower
            ) and info["label"] == merged[canon_name]["label"]:
                found_canonical = canon_name
                break

        if found_canonical:
            # 合并到规范实体
            merged[found_canonical]["count"] += info["count"]
            merged[found_canonical]["docs"] = list(
                set(merged[found_canonical]["docs"]) | set(info["docs"])
            )
            merged[found_canonical]["aliases"].add(name)
            canonical[name] = found_canonical
        else:
            merged[name] = {**info, "aliases": set()}

    log(f"  实体合并: {len(entities)} → {len(merged)} 个规范实体")
    return merged


def build_knowledge_graph(
    docs: List[Document],
    entities: Dict[str, Dict],
    relations: List[Tuple[str, str, str]],
) -> str:
    """
    构建知识图谱文本输出（Mode B）。
    输出格式：实体列表 + 关系列表 + 高密度证据段落。
    """
    total_chars = sum(d.char_count for d in docs)

    parts = []
    parts.append(f"# 知识图谱语料（{len(docs)} 文档压缩）")
    parts.append("")

    # ============ 实体 ============
    parts.append("## 实体")

    # 按 label 分组，按 count 降序
    by_label: Dict[str, List] = defaultdict(list)
    for name, info in entities.items():
        by_label[info["label"]].append((name, info))

    for label in ["PERSON", "ORG", "GPE", "DATE", "NORP", "EVENT", "QUANTITY", "FAC"]:
        if label not in by_label:
            continue
        ents = sorted(by_label[label], key=lambda x: x[1]["count"], reverse=True)
        for name, info in ents[:30]:  # 每类最多 30 个
            aliases = info.get("aliases", set())
            alias_str = f" (aka {', '.join(aliases)})" if aliases else ""
            doc_count = len(set(info["docs"]))
            parts.append(f"- {label}: {name}{alias_str} [{info['count']} mentions, {doc_count} docs]")

    parts.append("")

    # ============ 关系 ============
    parts.append("## 关系")

    # 去重并计数
    rel_counter = Counter(relations)
    for (subj, pred, obj), count in rel_counter.most_common(100):
        parts.append(f"- {subj} --{pred}--> {obj}" + (f" (x{count})" if count > 1 else ""))

    parts.append("")

    # ============ 证据段落 ============
    parts.append("## 证据段落")

    # 收集与高频实体相关的段落
    top_entities = sorted(entities.items(), key=lambda x: x[1]["count"], reverse=True)[:20]
    top_entity_names = {name.lower() for name, _ in top_entities}

    evidence_paragraphs = []
    for doc in docs:
        paragraphs = [p.strip() for p in doc.body.split("\n\n") if len(p.strip()) > 80]
        for para in paragraphs:
            para_lower = para.lower()
            # 计算段落中包含多少个高频实体
            entity_hits = sum(1 for e in top_entity_names if e in para_lower)
            if entity_hits >= 2:  # 至少包含 2 个高频实体
                evidence_paragraphs.append((entity_hits, para[:500], doc.source_label))

    # 按实体密度降序，取 top 50
    evidence_paragraphs.sort(key=lambda x: x[0], reverse=True)
    for _, para, source in evidence_paragraphs[:50]:
        parts.append(f"> [来源: {source}] {para}")
        parts.append("")

    output_text = "\n".join(parts)
    compression = (1 - len(output_text) / total_chars) * 100 if total_chars else 0
    parts_header = parts[0]
    output_text = output_text.replace(
        parts_header,
        f"# 知识图谱语料（{len(docs)} 文档压缩, 压缩率 {compression:.0f}%）",
        1,
    )

    log(f"  Mode B 输出: {len(output_text):,} 字符, 压缩率 {compression:.0f}%")
    return output_text
