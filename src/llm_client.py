# -*- coding: utf-8 -*-
"""
统一 LLM 客户端：支持 Kimi、Gemini、Grok、MiniMax、GLM、Qwen、DeepSeek、OpenAI、Perplexity、Claude。
通过 LLM_PROVIDER 环境变量或 provider 参数切换。
"""
import os
from pathlib import Path

import src  # noqa: F401  — 确保 PROJECT_ROOT 加入 sys.path

import time as _time

import httpx
from openai import OpenAI
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception

from config import (
    LLM_PROVIDER,
    KIMI_API_KEY, KIMI_BASE_URL, KIMI_MODEL, KIMI_VISION_MODEL,
    GEMINI_API_KEY, GEMINI_MODEL,
    GROK_API_KEY, GROK_BASE_URL, GROK_MODEL,
    MINIMAX_API_KEY, MINIMAX_BASE_URL, MINIMAX_MODEL,
    GLM_API_KEY, GLM_BASE_URL, GLM_MODEL, GLM_VISION_MODEL,
    QWEN_API_KEY, QWEN_BASE_URL, QWEN_MODEL,
    DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, DEEPSEEK_MODEL,
    OPENAI_API_KEY, OPENAI_BASE_URL, OPENAI_MODEL,
    PERPLEXITY_API_KEY, PERPLEXITY_BASE_URL, PERPLEXITY_MODEL,
    ANTHROPIC_API_KEY, ANTHROPIC_MODEL,
)

HTTP_TIMEOUT = httpx.Timeout(60.0, read=600.0)

# 所有 OpenAI 兼容 provider 的配置
PROVIDER_CONFIG = {
    "kimi": {
        "key": KIMI_API_KEY,
        "base_url": KIMI_BASE_URL,
        "model": KIMI_MODEL,
    },
    "grok": {
        "key": GROK_API_KEY,
        "base_url": GROK_BASE_URL,
        "model": GROK_MODEL,
    },
    "minimax": {
        "key": MINIMAX_API_KEY,
        "base_url": MINIMAX_BASE_URL,
        "model": MINIMAX_MODEL,
    },
    "glm": {
        "key": GLM_API_KEY,
        "base_url": GLM_BASE_URL,
        "model": GLM_MODEL,
    },
    "qwen": {
        "key": QWEN_API_KEY,
        "base_url": QWEN_BASE_URL,
        "model": QWEN_MODEL,
    },
    "deepseek": {
        "key": DEEPSEEK_API_KEY,
        "base_url": DEEPSEEK_BASE_URL,
        "model": DEEPSEEK_MODEL,
    },
    "openai": {
        "key": OPENAI_API_KEY,
        "base_url": OPENAI_BASE_URL,
        "model": OPENAI_MODEL,
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

# OpenAI 兼容的 provider 列表
_OPENAI_COMPATIBLE = ("kimi", "grok", "minimax", "glm", "qwen", "deepseek", "openai", "perplexity")


def _is_retryable(exc: BaseException) -> bool:
    """判断异常是否值得重试：5xx、429、超时、连接错误。"""
    # httpx 超时与连接错误
    if isinstance(exc, (httpx.TimeoutException, httpx.ConnectError, ConnectionError, TimeoutError)):
        return True
    # OpenAI SDK 包装的错误
    try:
        from openai import APIStatusError, APITimeoutError, APIConnectionError
        if isinstance(exc, (APITimeoutError, APIConnectionError)):
            return True
        if isinstance(exc, APIStatusError) and exc.status_code in (429, 500, 502, 503, 504):
            return True
    except ImportError:
        pass
    # Anthropic SDK 错误
    try:
        from anthropic import APIStatusError as AnthropicStatusError, APITimeoutError as AnthropicTimeout, APIConnectionError as AnthropicConnError
        if isinstance(exc, (AnthropicTimeout, AnthropicConnError)):
            return True
        if isinstance(exc, AnthropicStatusError) and exc.status_code in (429, 500, 502, 503, 504):
            return True
    except ImportError:
        pass
    # RuntimeError from Perplexity with 5xx / 429
    if isinstance(exc, RuntimeError):
        msg = str(exc)
        if any(f"API {code}" in msg for code in ("429", "500", "502", "503", "504")):
            return True
    return False


def _log_retry(retry_state):
    """重试时打印日志。"""
    exc = retry_state.outcome.exception()
    attempt = retry_state.attempt_number
    ts = _time.strftime("%H:%M:%S", _time.localtime())
    print(f"[{ts}] [LLM重试] 第 {attempt} 次失败: {type(exc).__name__}: {str(exc)[:200]}，即将重试...", flush=True)


_llm_retry = retry(
    retry=retry_if_exception(_is_retryable),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=2, min=2, max=16),
    before_sleep=_log_retry,
    reraise=True,
)


@_llm_retry
def _openai_compatible_chat(provider: str, messages: list, model: str = None, max_tokens: int = 8192, temperature: float = 0.6) -> str:
    """OpenAI 兼容 API。"""
    cfg = PROVIDER_CONFIG.get(provider, PROVIDER_CONFIG["kimi"])
    key = cfg["key"]
    base_url = cfg.get("base_url")
    default_model = cfg.get("model", "gpt-5.4")
    if not key:
        raise ValueError(f"请设置 {provider.upper()}_API_KEY 或在 .env 中配置")
    client = OpenAI(api_key=key, base_url=base_url, http_client=httpx.Client(timeout=HTTP_TIMEOUT))
    m = model or default_model
    # kimi-k2.5 等模型仅允许 temperature=1
    if provider == "kimi" and "k2" in m.lower():
        temperature = 1.0
    resp = client.chat.completions.create(
        model=m,
        messages=messages,
        max_tokens=max_tokens,
        temperature=temperature,
    )
    return (resp.choices[0].message.content or "").strip()


@_llm_retry
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


@_llm_retry
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
    优先: kimi, gemini, grok
    候选: minimax, glm, qwen, deepseek, openai, perplexity, claude
    """
    p = (provider or os.getenv("LLM_PROVIDER") or LLM_PROVIDER or "kimi").lower().strip()
    if p == "claude":
        return _claude_chat(messages, model, max_tokens, temperature)
    if p == "gemini":
        return _gemini_chat(messages, model, max_tokens, temperature)
    if p in _OPENAI_COMPATIBLE:
        return _openai_compatible_chat(p, messages, model, max_tokens, temperature)
    # 默认按 kimi 处理
    return _openai_compatible_chat("kimi", messages, model, max_tokens, temperature)


@_llm_retry
def perplexity_chat_with_citations(
    messages: list,
    model: str = None,
    max_tokens: int = 4096,
    temperature: float = 0.3,
) -> tuple[str, list[dict]]:
    """
    调用 Perplexity API，返回 (content, citations)。
    citations 格式: [{"url": str, "title": str}, ...]，来自 search_results 或 citations。
    """
    if not PERPLEXITY_API_KEY:
        raise ValueError("请设置 PERPLEXITY_API_KEY 或在 .env 中配置")
    cfg = PROVIDER_CONFIG["perplexity"]
    url = (cfg.get("base_url") or "https://api.perplexity.ai").rstrip("/") + "/chat/completions"
    m = model or cfg.get("model", "sonar")
    payload = {
        "model": m,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    resp = httpx.post(
        url,
        json=payload,
        headers={
            "Authorization": f"Bearer {PERPLEXITY_API_KEY}",
            "Content-Type": "application/json",
        },
        timeout=HTTP_TIMEOUT,
    )
    if resp.status_code >= 400:
        try:
            err_body = resp.text[:500] if resp.text else "(empty)"
            raise RuntimeError(f"Perplexity API {resp.status_code}: {err_body}")
        except RuntimeError:
            raise
    resp.raise_for_status()
    data = resp.json()
    content = ""
    if data.get("choices") and len(data["choices"]) > 0:
        msg = data["choices"][0].get("message", {})
        content = (msg.get("content") or "").strip()
    citations: list[dict] = []
    search_results = data.get("search_results") or []
    for r in search_results:
        if isinstance(r, dict) and r.get("url"):
            citations.append({
                "url": r["url"],
                "title": r.get("title") or r["url"],
            })
    if not citations and data.get("citations"):
        for c in data["citations"]:
            u = c if isinstance(c, str) else (c.get("url") or "")
            if u:
                citations.append({"url": u, "title": u})
    return content, citations


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
    if p in ("openai", "grok", "perplexity", "glm", "minimax", "qwen", "deepseek"):
        if p == "glm":
            model = model or GLM_VISION_MODEL
        return _openai_compatible_chat(p, messages, model, max_tokens, temperature)
    if p == "claude":
        return _claude_chat(messages, model, max_tokens, temperature)
    if p == "gemini":
        return _gemini_chat(messages, model, max_tokens, temperature)
    return _openai_compatible_chat("kimi", messages, model or KIMI_VISION_MODEL, max_tokens, temperature)
