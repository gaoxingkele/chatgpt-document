# -*- coding: utf-8 -*-
"""
从本地文件导入对话内容，支持 .txt、.json、.md 等格式。
适配 Gemini、Perplexity 导出及用户手动复制的文本。
"""
import json
import re
from pathlib import Path


def import_from_file(file_path: Path) -> str:
    """
    从文件导入对话内容，返回归一化后的纯文本。
    支持：.txt（直接使用）、.md、.json（常见对话结构）。
    """
    path = Path(file_path)
    if not path.is_file():
        raise FileNotFoundError(f"文件不存在: {path}")

    suffix = path.suffix.lower()
    raw = path.read_text(encoding="utf-8", errors="replace")

    if suffix == ".txt":
        return _normalize_text(raw)

    if suffix == ".md":
        return _normalize_text(raw)

    if suffix == ".json":
        return _parse_json_conversation(raw)

    if suffix == ".html":
        return _parse_html(raw)

    # 未知后缀按纯文本处理
    return _normalize_text(raw)


def _normalize_text(text: str) -> str:
    """清理多余空行、统一换行。"""
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    return "\n\n".join(lines)


def _parse_json_conversation(raw: str) -> str:
    """
    解析常见对话 JSON 结构。
    支持：Perplexity 导出、Gemini 导出、OpenAI 格式等。
    """
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return _normalize_text(raw)

    parts = []

    # 结构1: {"conversations": [{"role":"user","content":"..."}, ...]}
    if isinstance(data, dict) and "conversations" in data:
        for msg in data.get("conversations", []):
            role = msg.get("role", msg.get("type", "")).lower()
            content = msg.get("content", msg.get("text", msg.get("message", "")))
            if content:
                prefix = "用户：" if role == "user" else "助手："
                parts.append(f"{prefix}\n{content}")

    # 结构2: {"messages": [...]} 或 {"chat": [...]}
    elif isinstance(data, dict):
        for key in ("messages", "chat", "turns", "items"):
            if key in data and isinstance(data[key], list):
                for msg in data[key]:
                    if isinstance(msg, dict):
                        role = msg.get("role", msg.get("author", msg.get("type", "")))
                        content = msg.get("content", msg.get("text", msg.get("parts", [""])))
                        if isinstance(content, list):
                            content = " ".join(
                                p.get("text", str(p)) if isinstance(p, dict) else str(p)
                                for p in content
                            )
                        if content:
                            prefix = "用户：" if str(role).lower() in ("user", "human") else "助手："
                            parts.append(f"{prefix}\n{content}")
                break

    # 结构3: 顶层数组 [{role, content}, ...]
    elif isinstance(data, list):
        for msg in data:
            if isinstance(msg, dict):
                content = msg.get("content", msg.get("text", ""))
                if content:
                    role = msg.get("role", "")
                    prefix = "用户：" if str(role).lower() == "user" else "助手："
                    parts.append(f"{prefix}\n{content}")

    if not parts:
        return _normalize_text(raw)
    return "\n\n".join(parts)


def _parse_html(raw: str) -> str:
    """简单提取 HTML 中的文本。"""
    # 移除 script、style
    text = re.sub(r"<script[^>]*>.*?</script>", "", raw, flags=re.DOTALL | re.I)
    text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL | re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return _normalize_text(text.strip())
