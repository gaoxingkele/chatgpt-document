# -*- coding: utf-8 -*-
"""Kimi API 客户端。现统一由 llm_client 调度，支持多 Provider 切换。"""
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config import KIMI_API_KEY, KIMI_BASE_URL, KIMI_MODEL, KIMI_VISION_MODEL
from src.llm_client import chat as _chat, chat_vision as _chat_vision


def get_client():
    """兼容旧代码，返回可用于直接调用的 chat 函数。"""
    import httpx
    from openai import OpenAI
    if not KIMI_API_KEY:
        raise ValueError("请设置环境变量 KIMI_API_KEY 或在 .env 中配置")
    return OpenAI(api_key=KIMI_API_KEY, base_url=KIMI_BASE_URL, http_client=httpx.Client(timeout=60.0, read=180.0))


def chat(messages: list, model: str = None, max_tokens: int = 8192, temperature: float = 0.6, provider: str = None) -> str:
    """单次对话，返回 assistant 的 content。默认使用 LLM_PROVIDER，可传 provider 覆盖。"""
    return _chat(messages, provider=provider, model=model, max_tokens=max_tokens, temperature=temperature)


def chat_vision(messages: list, model: str = None, max_tokens: int = 8192, temperature: float = 0.3, provider: str = None) -> str:
    """多模态对话（支持图片）。默认使用 LLM_PROVIDER。"""
    return _chat_vision(messages, provider=provider, model=model, max_tokens=max_tokens, temperature=temperature)


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
