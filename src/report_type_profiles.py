# -*- coding: utf-8 -*-
"""按报告类型加载外部 Markdown 配置，并映射 Step3/Step7/Step8 行为。"""
from __future__ import annotations

import re
from pathlib import Path

from config import SKILL_DIR

DEFAULT_REPORT_TYPE = "academic_research"
REPORT_TYPES_DIR = Path(SKILL_DIR) / "report_types"
STATIC_REPORT_TYPES = [
    "academic_research",
    "political_commentary",
    "business_analysis",
    "feasibility_study",
]


def list_supported_report_types() -> list[str]:
    """返回可用报告类型（优先读取 report_types 目录中的 .md）。"""
    if REPORT_TYPES_DIR.exists():
        dynamic = sorted(
            p.stem
            for p in REPORT_TYPES_DIR.glob("*.md")
            if p.is_file() and not p.stem.startswith("_")
        )
        if dynamic:
            return dynamic
    return STATIC_REPORT_TYPES[:]


def _parse_front_matter(md_text: str) -> tuple[dict[str, str], str]:
    """解析 Markdown front matter（--- 包裹的 key: value）。"""
    text = md_text.lstrip("\ufeff")
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---\n", 4)
    if end < 0:
        return {}, text
    fm = text[4:end]
    body = text[end + 5 :]
    data: dict[str, str] = {}
    for line in fm.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        k, v = line.split(":", 1)
        data[k.strip()] = v.strip().strip('"').strip("'")
    return data, body


def _parse_sections(md_body: str) -> dict[str, str]:
    """按二级标题解析 Markdown 章节。"""
    parts = re.split(r"^##\s+(.+?)\s*$", md_body, flags=re.M)
    if len(parts) <= 1:
        return {}
    sections: dict[str, str] = {}
    # parts: [prefix, title1, body1, title2, body2, ...]
    for i in range(1, len(parts), 2):
        title = parts[i].strip()
        body = parts[i + 1].strip() if i + 1 < len(parts) else ""
        sections[title] = body
    return sections


def load_report_type_profile(report_type: str | None = None) -> dict:
    """
    加载报告类型配置。

    配置目录：
    - output/skill/report_types/{report_type}.md
    """
    rt = (report_type or DEFAULT_REPORT_TYPE).strip()
    profile_path = REPORT_TYPES_DIR / f"{rt}.md"
    if not profile_path.exists():
        raise FileNotFoundError(f"未找到报告类型配置: {profile_path}")
    text = profile_path.read_text(encoding="utf-8", errors="replace")
    front_matter, body = _parse_front_matter(text)
    sections = _parse_sections(body)
    # 解析整数型 front matter
    def _int_or_default(key, default):
        val = front_matter.get(key, "")
        try:
            return int(val)
        except (ValueError, TypeError):
            return default

    return {
        "report_type": front_matter.get("report_type", rt),
        "display_name": front_matter.get("display_name", rt),
        "policy_name": front_matter.get("policy_name", "policy1"),
        "step7_title_suffix": front_matter.get("step7_title_suffix", "学术风格分析报告"),
        "step8_output_suffix": front_matter.get("step8_output_suffix", "报告_v5"),
        # 模板约束（3.14）
        "min_chapters": _int_or_default("min_chapters", 3),
        "max_chapters": _int_or_default("max_chapters", 7),
        "min_total_chars": _int_or_default("min_total_chars", 10000),
        "default_style": front_matter.get("default_style", "A"),
        "sections": sections,
        "profile_path": str(profile_path),
    }

