# -*- coding: utf-8 -*-
"""
Prompt 模板加载器：从 prompts/ 目录加载外部化 prompt。
支持 common/ 公共规范注入。
"""
from __future__ import annotations

from pathlib import Path

from config import PROJECT_ROOT

PROMPTS_DIR = PROJECT_ROOT / "prompts"
COMMON_DIR = PROMPTS_DIR / "common"


def load_prompt(name: str) -> str:
    """加载指定 prompt 模板。name 如 'common/mermaid_rules'。"""
    path = PROMPTS_DIR / f"{name}.md"
    if path.is_file():
        return path.read_text(encoding="utf-8", errors="replace").strip()
    return ""


def load_common_rules() -> str:
    """加载所有公共规范（mermaid + table + language），拼接返回。"""
    rules = []
    for name in ["mermaid_rules", "table_rules", "language_rules"]:
        path = COMMON_DIR / f"{name}.md"
        if path.is_file():
            rules.append(path.read_text(encoding="utf-8", errors="replace").strip())
    return "\n\n".join(rules)


def load_evaluation_rubric(policy_name: str) -> str:
    """加载领域评估评分标准。"""
    from config import SKILL_DIR
    path = SKILL_DIR / policy_name / "evaluation_rubric.md"
    if path.is_file():
        return path.read_text(encoding="utf-8", errors="replace").strip()
    return ""


def load_structure_template(policy_name: str) -> str:
    """加载领域结构模板。"""
    from config import SKILL_DIR
    path = SKILL_DIR / policy_name / "structure_template.md"
    if path.is_file():
        return path.read_text(encoding="utf-8", errors="replace").strip()
    return ""
