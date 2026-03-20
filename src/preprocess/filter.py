# -*- coding: utf-8 -*-
"""语料过滤：status 过滤、短文过滤、boilerplate 正则清洗。"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List, Optional

from src.preprocess.document import Document
from src.utils.log import log

# ============ Boilerplate 正则模式 ============
# 每个元组: (pattern, description)
_BOILERPLATE_PATTERNS = [
    # 通用网页噪音
    (r"(?m)^.*cookie[s]?\s*(policy|settings|preferences|consent).*$", "cookie notices"),
    (r"(?m)^.*accept\s+(all\s+)?cookies.*$", "cookie accept"),
    (r"(?m)^.*subscribe\s+(to\s+)?(our\s+)?newsletter.*$", "newsletter prompts"),
    (r"(?m)^.*sign\s+up\s+for\s+.*newsletter.*$", "newsletter signups"),
    (r"(?m)^.*advertisement\s*[-–—]?\s*$", "ad markers"),
    (r"(?m)^.*skip\s+to\s+(main\s+)?content.*$", "skip navigation"),
    (r"(?m)^.*toggle\s+navigation.*$", "nav toggles"),

    # CNN 特有
    (r"(?ms)^.*?Listen to CNN.*?$", "CNN listen prompts"),
    (r"(?m)^.*CNN\s+(Audio|Podcasts|Newsletter).*$", "CNN promo sections"),
    (r"(?m)^.*Download our app.*$", "app download prompts"),
    (r"(?m)^.*Get our free.*app.*$", "app prompts"),

    # 社交媒体和分享按钮
    (r"(?m)^.*share\s+(this|on)\s+(facebook|twitter|x|linkedin|email).*$", "share buttons"),
    (r"(?m)^.*follow\s+us\s+on.*$", "follow prompts"),
    (r"(?mi)^.*(facebook|twitter|instagram|linkedin|youtube)\s*$", "social links"),

    # 导航和菜单残留
    (r"(?m)^(Home|News|World|Politics|Business|Opinion|Health|Entertainment|Style|Travel|Sports|Video|Audio)\s*$",
     "nav menu items"),

    # 版权和法律
    (r"(?m)^.*©\s*\d{4}.*$", "copyright lines"),
    (r"(?m)^.*all\s+rights\s+reserved.*$", "rights reserved"),
    (r"(?m)^.*terms\s+(of\s+)?(use|service).*$", "terms of use"),
    (r"(?m)^.*privacy\s+policy.*$", "privacy policy"),

    # 广告和赞助
    (r"(?m)^.*sponsored\s+(content|by).*$", "sponsored content"),
    (r"(?m)^.*paid\s+(content|partner).*$", "paid content"),

    # 连续短行（导航碎片：5+ 个连续 <=3 词的行）
    (r"(?m)(^\S{1,20}\s*\n){5,}", "navigation fragments"),

    # ISO 时间戳（2026-02-24T21:29:17+00:00 等）
    (r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+\-]\d{2}:\d{2}", "ISO timestamps"),
    # 行内日期时间戳（February 24 2026, 1:48 p.m. 等独立一行时）
    (r"(?m)^\s*(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2}[,]?\s+\d{4}[,.]?\s*(?:\d{1,2}[:.]\d{2}\s*(?:a\.m\.|p\.m\.|AM|PM)?)?\s*(?:EST|PST|UTC|GMT|EDT|PDT)?\s*$",
     "standalone date lines"),

    # 裸 URL（独立一行或行内 https://... 链接）
    (r"https?://[^\s)\]\"'<>]{10,}", "bare URLs"),

    # HTML 实体
    (r"&#?\w{2,8};", "HTML entities"),

    # 网站特有导航碎片
    (r"(?m)^.*(?:Special Investigations|Press Freedom Defense Fund|Impact\s*(?:&|and)\s*Reports).*$",
     "site section headers"),
    (r"(?m)^.*(?:Powered and implemented by|FactSet Digital Solutions|Mutual Fund and ETF data provided by).*$",
     "site footer fragments"),
    (r"(?m)^.*(?:Add \w+ (?:on|to) Google|Powered by \w+|Show me more content from).*$", "site promo"),
    (r"(?m)^.*(?:Join Our (?:Talent|Newsletter) Community|CBS News Investigates|Updated on:).*$",
     "site metadata lines"),
    (r"(?m)^.*(?:Getty Images|AFP via Getty|Anadolu via Getty|AP Photo|Reuters).*$",
     "photo credits"),
    (r"(?m)^.*(?:Tiempo de lectura|Responsabilidad Social|Oportunidades de Empleo).*$",
     "Spanish site nav"),

    # 图片说明残片（截断的 alt text）
    (r"(?m)^.*(?:Screenshot from a video|A view of the site where|Photo:|Image:).*$",
     "image captions"),

    # 连续空行压缩
    (r"\n{4,}", "excessive blank lines"),
]

# 编译正则
_COMPILED_PATTERNS = [
    (re.compile(p, re.IGNORECASE), desc) for p, desc in _BOILERPLATE_PATTERNS
]


def filter_by_status(
    docs: List[Document],
    index: Optional[Dict[str, str]],
) -> List[Document]:
    """按 _index.csv status 过滤，只保留 'ok' 或无 index 的文档。"""
    if index is None:
        return docs

    before = len(docs)
    result = []
    for doc in docs:
        status = index.get(doc.filename, "ok")
        if status in ("ok", ""):
            result.append(doc)
    after = len(result)
    if before != after:
        log(f"  status 过滤: {before} → {after} （去掉 {before - after} 篇 failed/skipped）")
    return result


def filter_short(docs: List[Document], min_chars: int = 500) -> List[Document]:
    """去掉 body 过短的文档。"""
    before = len(docs)
    result = [d for d in docs if d.char_count >= min_chars]
    after = len(result)
    if before != after:
        log(f"  短文过滤: {before} → {after} （去掉 {before - after} 篇 < {min_chars} 字）")
    return result


def remove_boilerplate(docs: List[Document]) -> List[Document]:
    """对每篇文档执行 boilerplate 正则清洗。"""
    total_removed = 0
    for doc in docs:
        original_len = len(doc.body)
        text = doc.body
        for pattern, _desc in _COMPILED_PATTERNS:
            if _desc == "excessive blank lines":
                text = pattern.sub("\n\n", text)
            else:
                text = pattern.sub("", text)
        # 清理多余空行
        text = re.sub(r"\n{3,}", "\n\n", text).strip()
        doc.body = text
        doc.char_count = len(text)
        removed = original_len - len(text)
        if removed > 0:
            total_removed += removed

    log(f"  boilerplate 清洗: 共移除 {total_removed:,} 字符")
    return docs
