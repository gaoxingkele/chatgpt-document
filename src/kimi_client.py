# -*- coding: utf-8 -*-
"""Kimi API 客户端（兼容 OpenAI SDK）。"""
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import httpx
from openai import OpenAI
from config import KIMI_API_KEY, KIMI_BASE_URL, KIMI_MODEL

# 超时设置：连接 60 秒，读取 180 秒（报告生成可能较久）
HTTP_TIMEOUT = httpx.Timeout(60.0, read=180.0)


def get_client() -> OpenAI:
    if not KIMI_API_KEY:
        raise ValueError("请设置环境变量 KIMI_API_KEY 或在 .env 中配置")
    http_client = httpx.Client(timeout=HTTP_TIMEOUT)
    return OpenAI(api_key=KIMI_API_KEY, base_url=KIMI_BASE_URL, http_client=http_client)


def chat(messages: list, model: str = None, max_tokens: int = 8192, temperature: float = 0.6) -> str:
    """单次对话，返回 assistant 的 content。"""
    client = get_client()
    model = model or KIMI_MODEL
    resp = client.chat.completions.create(
        model=model,
        messages=messages,
        max_tokens=max_tokens,
        temperature=temperature,
    )
    return (resp.choices[0].message.content or "").strip()


def chat_append(
    messages: list,
    user_content: str,
    model: str = None,
    max_tokens: int = 8192,
    temperature: float = 0.6,
) -> tuple[str, list]:
    """
    多轮对话：追加 user 消息，调用 API，追加 assistant 回复。
    返回 (assistant 回复文本, 更新后的 messages 列表)。
    """
    messages = list(messages)
    messages.append({"role": "user", "content": user_content})
    reply = chat(messages, model=model, max_tokens=max_tokens, temperature=temperature)
    messages.append({"role": "assistant", "content": reply})
    return reply, messages
