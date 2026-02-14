# -*- coding: utf-8 -*-
"""
统一 LLM 客户端：支持 Kimi、OpenAI、Grok、Perplexity、Claude、Gemini。
通过 LLM_PROVIDER 环境变量或 provider 参数切换。
"""
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import httpx
from openai import OpenAI

from config import (
    LLM_PROVIDER,
    KIMI_API_KEY, KIMI_BASE_URL, KIMI_MODEL, KIMI_VISION_MODEL,
    OPENAI_API_KEY, OPENAI_BASE_URL, OPENAI_MODEL,
    GROK_API_KEY, GROK_BASE_URL, GROK_MODEL,
    PERPLEXITY_API_KEY, PERPLEXITY_BASE_URL, PERPLEXITY_MODEL,
    ANTHROPIC_API_KEY, ANTHROPIC_MODEL,
    GEMINI_API_KEY, GEMINI_MODEL,
)

HTTP_TIMEOUT = httpx.Timeout(60.0, read=180.0)

PROVIDER_CONFIG = {
    "kimi": {
        "key": KIMI_API_KEY,
        "base_url": KIMI_BASE_URL,
        "model": KIMI_MODEL,
    },
    "openai": {
        "key": OPENAI_API_KEY,
        "base_url": OPENAI_BASE_URL,
        "model": OPENAI_MODEL,
    },
    "grok": {
        "key": GROK_API_KEY,
        "base_url": GROK_BASE_URL,
        "model": GROK_MODEL,
    },
    "perplexity": {
        "key": PERPLEXITY_API_KEY,
        "base_url": PERPLEXITY_BASE_URL,
        "model": PERPLEXITY_MODEL,
    },
    "claude": {
        "key": ANTHROPIC_API_KEY,
        "model": ANTHROPIC_MODEL,
    },
    "gemini": {
        "key": GEMINI_API_KEY,
        "model": GEMINI_MODEL,
    },
}


def _openai_compatible_chat(provider: str, messages: list, model: str = None, max_tokens: int = 8192, temperature: float = 0.6) -> str:
    """OpenAI 兼容 API（Kimi、OpenAI、Grok、Perplexity）。"""
    cfg = PROVIDER_CONFIG.get(provider, PROVIDER_CONFIG["kimi"])
    key = cfg["key"]
    base_url = cfg.get("base_url")
    default_model = cfg.get("model", "gpt-4o-mini")
    if not key:
        raise ValueError(f"请设置 {provider.upper()}_API_KEY 或在 .env 中配置")
    client = OpenAI(api_key=key, base_url=base_url, http_client=httpx.Client(timeout=HTTP_TIMEOUT))
    m = model or default_model
    resp = client.chat.completions.create(
        model=m,
        messages=messages,
        max_tokens=max_tokens,
        temperature=temperature,
    )
    return (resp.choices[0].message.content or "").strip()


def _claude_chat(messages: list, model: str = None, max_tokens: int = 8192, temperature: float = 0.6) -> str:
    """Anthropic Claude API。"""
    if not ANTHROPIC_API_KEY:
        raise ValueError("请设置 ANTHROPIC_API_KEY 或在 .env 中配置")
    try:
        from anthropic import Anthropic
    except ImportError:
        raise ImportError("Claude 需安装 anthropic: pip install anthropic")
    client = Anthropic(api_key=ANTHROPIC_API_KEY)
    m = model or ANTHROPIC_MODEL
    system = ""
    msgs = []
    for item in messages:
        role = item.get("role", "")
        content = item.get("content", "")
        if isinstance(content, list):
            content = "\n".join(
                p.get("text", str(p)) for p in content
                if isinstance(p, dict) and ("text" in p or p.get("type") == "text")
            )
        if role == "system":
            system = content
        elif role == "assistant":
            msgs.append({"role": "assistant", "content": content})
        elif role == "user":
            msgs.append({"role": "user", "content": content})
    kwargs = {"model": m, "max_tokens": max_tokens, "temperature": temperature, "messages": msgs}
    if system:
        kwargs["system"] = system
    resp = client.messages.create(**kwargs)
    return (resp.content[0].text if resp.content else "").strip()


def _gemini_chat(messages: list, model: str = None, max_tokens: int = 8192, temperature: float = 0.6) -> str:
    """Google Gemini API。"""
    if not GEMINI_API_KEY:
        raise ValueError("请设置 GEMINI_API_KEY 或在 .env 中配置")
    try:
        import google.generativeai as genai
    except ImportError:
        raise ImportError("Gemini 需安装 google-generativeai: pip install google-generativeai")
    genai.configure(api_key=GEMINI_API_KEY)
    m = model or GEMINI_MODEL
    parts = []
    for item in messages:
        role = item.get("role", "")
        content = item.get("content", "")
        if isinstance(content, list):
            content = "\n".join(
                p.get("text", str(p)) for p in content
                if isinstance(p, dict) and ("text" in p or p.get("type") == "text")
            )
        if role == "system":
            parts.append(f"[System]\n{content}")
        elif role == "user":
            parts.append(f"[User]\n{content}")
        elif role == "assistant":
            parts.append(f"[Assistant]\n{content}")
    prompt = "\n\n".join(parts) if parts else ""
    gen_model = genai.GenerativeModel(m)
    resp = gen_model.generate_content(
        prompt,
        generation_config=genai.types.GenerationConfig(
            max_output_tokens=max_tokens,
            temperature=temperature,
        ),
    )
    return (resp.text or "").strip()


def chat(
    messages: list,
    provider: str = None,
    model: str = None,
    max_tokens: int = 8192,
    temperature: float = 0.6,
) -> str:
    """
    统一对话接口。provider 未指定时使用环境变量 LLM_PROVIDER（默认 kimi）。
    支持: kimi, openai, grok, perplexity, claude, gemini
    """
    p = (provider or os.getenv("LLM_PROVIDER") or LLM_PROVIDER or "kimi").lower().strip()
    if p == "claude":
        return _claude_chat(messages, model, max_tokens, temperature)
    if p == "gemini":
        return _gemini_chat(messages, model, max_tokens, temperature)
    if p in ("kimi", "openai", "grok", "perplexity"):
        return _openai_compatible_chat(p, messages, model, max_tokens, temperature)
    # 默认按 kimi 处理
    return _openai_compatible_chat("kimi", messages, model, max_tokens, temperature)


def chat_vision(
    messages: list,
    provider: str = None,
    model: str = None,
    max_tokens: int = 8192,
    temperature: float = 0.3,
) -> str:
    """多模态对话（支持图片）。优先使用 Vision 模型。"""
    p = (provider or os.getenv("LLM_PROVIDER") or LLM_PROVIDER or "kimi").lower().strip()
    if p == "kimi":
        from config import KIMI_VISION_MODEL
        model = model or KIMI_VISION_MODEL
        return _openai_compatible_chat("kimi", messages, model, max_tokens, temperature)
    if p in ("openai", "grok", "perplexity"):
        return _openai_compatible_chat(p, messages, model, max_tokens, temperature)
    if p == "claude":
        return _claude_chat(messages, model, max_tokens, temperature)
    if p == "gemini":
        return _gemini_chat(messages, model, max_tokens, temperature)
    return _openai_compatible_chat("kimi", messages, model or KIMI_VISION_MODEL, max_tokens, temperature)
