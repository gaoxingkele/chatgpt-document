# -*- coding: utf-8 -*-
"""共享文件操作工具：加载语料、清理 JSON 包裹。"""
from pathlib import Path


def load_raw_content(raw_path: Path | None, max_chars: int = 130_000) -> str:
    """加载文本文件并按 max_chars 截断。raw_path 为 None 或不存在时返回空串。"""
    if not raw_path or not Path(raw_path).is_file():
        return ""
    text = Path(raw_path).read_text(encoding="utf-8", errors="replace")
    if len(text) > max_chars:
        text = text[:max_chars] + f"\n\n[内容已截断，仅保留前 {max_chars} 字]"
    return text


def load_skill_and_summary(policy_name: str = "policy1") -> tuple[str, str]:
    """加载 Skill.md 与 summary.md，返回 (skill_text, summary_text)。"""
    from config import SKILL_DIR
    policy_dir = Path(SKILL_DIR) / policy_name
    skill_path = policy_dir / "Skill.md"
    if not skill_path.exists():
        skill_path = policy_dir / "SKILL.md"
    summary_path = policy_dir / "summary.md"

    skill_text = skill_path.read_text(encoding="utf-8", errors="replace") if skill_path.exists() else ""
    summary_text = summary_path.read_text(encoding="utf-8", errors="replace") if summary_path.exists() else ""

    if not skill_text and not summary_text:
        raise FileNotFoundError(f"未找到 Skill.md 或 summary.md：{policy_dir}")
    return skill_text, summary_text


def clean_json(text: str) -> str:
    """去除 LLM 回复中常见的 ```json ... ``` 代码块包裹。"""
    s = text.strip()
    for start in ("```json", "```"):
        if s.startswith(start):
            s = s[len(start):].strip()
        if s.endswith("```"):
            s = s[:-3].strip()
    return s
