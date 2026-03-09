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


def clean_json(text: str) -> str:
    """去除 LLM 回复中常见的 ```json ... ``` 代码块包裹。"""
    s = text.strip()
    for start in ("```json", "```"):
        if s.startswith(start):
            s = s[len(start):].strip()
        if s.endswith("```"):
            s = s[:-3].strip()
    return s
