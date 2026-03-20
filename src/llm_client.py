# -*- coding: utf-8 -*-
"""
统一 LLM 客户端：支持 Kimi、Gemini、Grok、MiniMax、GLM、Qwen、DeepSeek、OpenAI、Perplexity、Claude。
通过 LLM_PROVIDER 环境变量或 provider 参数切换。
"""
import os
import threading

import src  # noqa: F401  — 确保 PROJECT_ROOT 加入 sys.path

import time as _time

import httpx
from openai import OpenAI
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception

from config import (
    LLM_PROVIDER,
    KIMI_API_KEY, KIMI_BASE_URL, KIMI_MODEL, KIMI_VISION_MODEL,
    GEMINI_API_KEY, GEMINI_MODEL,
    GROK_API_KEY, GROK_BASE_URL, GROK_MODEL, GROK_REASONING_MODEL,
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


# ============ Token 用量统计 ============
class _TokenTracker:
    """线程安全的 token 用量统计。"""

    def __init__(self):
        self._lock = threading.Lock()
        self._calls: list[dict] = []

    def record(self, provider: str, model: str, input_tokens: int = 0, output_tokens: int = 0):
        with self._lock:
            self._calls.append({
                "provider": provider, "model": model,
                "input_tokens": input_tokens, "output_tokens": output_tokens,
                "ts": _time.time(),
            })

    def summary(self) -> dict:
        with self._lock:
            total_in = sum(c["input_tokens"] for c in self._calls)
            total_out = sum(c["output_tokens"] for c in self._calls)
            by_provider: dict[str, dict] = {}
            for c in self._calls:
                p = c["provider"]
                g = by_provider.setdefault(p, {"calls": 0, "input_tokens": 0, "output_tokens": 0})
                g["calls"] += 1
                g["input_tokens"] += c["input_tokens"]
                g["output_tokens"] += c["output_tokens"]
            return {
                "total_calls": len(self._calls),
                "total_input_tokens": total_in,
                "total_output_tokens": total_out,
                "total_tokens": total_in + total_out,
                "by_provider": by_provider,
            }

    def reset(self):
        with self._lock:
            self._calls.clear()


_tracker = _TokenTracker()


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
    # deepseek max_tokens 上限 8192
    if provider == "deepseek" and max_tokens > 8192:
        max_tokens = 8192
    resp = client.chat.completions.create(
        model=m,
        messages=messages,
        max_tokens=max_tokens,
        temperature=temperature,
    )
    if hasattr(resp, "usage") and resp.usage:
        _tracker.record(provider, m, resp.usage.prompt_tokens or 0, resp.usage.completion_tokens or 0)
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
    if hasattr(resp, "usage") and resp.usage:
        _tracker.record("claude", m, getattr(resp.usage, "input_tokens", 0) or 0, getattr(resp.usage, "output_tokens", 0) or 0)
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
    if hasattr(resp, "usage_metadata") and resp.usage_metadata:
        _tracker.record("gemini", m,
            getattr(resp.usage_metadata, "prompt_token_count", 0) or 0,
            getattr(resp.usage_metadata, "candidates_token_count", 0) or 0)
    return (resp.text or "").strip()


def chat(
    messages: list,
    provider: str = None,
    model: str = None,
    max_tokens: int = 8192,
    temperature: float = 0.6,
    reasoning: bool = False,
) -> str:
    """
    统一对话接口。provider 未指定时使用环境变量 LLM_PROVIDER（默认 kimi）。
    reasoning=True 时，Grok 自动切换到推理模型（GROK_REASONING_MODEL）。
    """
    p = (provider or os.getenv("LLM_PROVIDER") or LLM_PROVIDER or "kimi").lower().strip()
    # Grok 推理模型路由
    if reasoning and p == "grok" and not model:
        model = GROK_REASONING_MODEL
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
    usage = data.get("usage", {})
    if usage:
        _tracker.record("perplexity", m, usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0))
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


def perplexity_deep_research(
    messages: list,
    max_tokens: int = 8192,
    poll_interval: float = 5.0,
    max_wait: float = 300.0,
) -> tuple[str, list[dict]]:
    """
    调用 Perplexity sonar-deep-research（异步模式）。
    提交请求后轮询直到完成，返回 (content, citations)。
    """
    if not PERPLEXITY_API_KEY:
        raise ValueError("请设置 PERPLEXITY_API_KEY 或在 .env 中配置")
    base_url = (PROVIDER_CONFIG["perplexity"].get("base_url") or "https://api.perplexity.ai").rstrip("/")
    headers = {
        "Authorization": f"Bearer {PERPLEXITY_API_KEY}",
        "Content-Type": "application/json",
    }
    model = "sonar-deep-research"

    # 1. 提交请求（deep research 耗时较长，用更大超时）
    deep_timeout = httpx.Timeout(60.0, read=300.0)
    payload = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
    }
    resp = httpx.post(
        f"{base_url}/chat/completions",
        json=payload,
        headers=headers,
        timeout=deep_timeout,
    )
    if resp.status_code >= 400:
        raise RuntimeError(f"Perplexity Deep Research 提交失败 {resp.status_code}: {resp.text[:500]}")
    data = resp.json()

    # 如果直接返回了结果（同步兼容）
    if data.get("choices"):
        content, citations = _extract_perplexity_response(data, model)
        return content, citations

    # 2. 异步模式：轮询
    request_id = data.get("id") or data.get("request_id")
    if not request_id:
        # 无 request_id，尝试直接解析
        content, citations = _extract_perplexity_response(data, model)
        return content, citations

    ts = _time.strftime("%H:%M:%S", _time.localtime())
    print(f"[{ts}] [Deep Research] 已提交，request_id={request_id}，等待完成...", flush=True)

    elapsed = 0.0
    while elapsed < max_wait:
        _time.sleep(poll_interval)
        elapsed += poll_interval
        try:
            poll_resp = httpx.get(
                f"{base_url}/chat/completions/{request_id}",
                headers=headers,
                timeout=HTTP_TIMEOUT,
            )
            if poll_resp.status_code == 200:
                poll_data = poll_resp.json()
                status = poll_data.get("status", "")
                if status == "completed" or poll_data.get("choices"):
                    content, citations = _extract_perplexity_response(poll_data, model)
                    return content, citations
                if status == "failed":
                    raise RuntimeError(f"Deep Research 失败: {poll_data}")
        except httpx.TimeoutException:
            pass

    raise TimeoutError(f"Deep Research 超时（{max_wait}s），request_id={request_id}")


def _extract_perplexity_response(data: dict, model: str) -> tuple[str, list[dict]]:
    """从 Perplexity 响应中提取 content 和 citations。"""
    usage = data.get("usage", {})
    if usage:
        _tracker.record("perplexity", model, usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0))
    content = ""
    if data.get("choices") and len(data["choices"]) > 0:
        msg = data["choices"][0].get("message", {})
        content = (msg.get("content") or "").strip()
    citations: list[dict] = []
    for r in data.get("search_results") or []:
        if isinstance(r, dict) and r.get("url"):
            citations.append({"url": r["url"], "title": r.get("title") or r["url"]})
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


# ============ Token 统计公开 API ============
def print_token_summary():
    """打印 token 用量摘要。"""
    s = _tracker.summary()
    if s["total_calls"] == 0:
        return
    print(f"\n{'='*60}")
    print(f"API 调用统计")
    print(f"{'='*60}")
    print(f"总调用次数: {s['total_calls']}")
    print(f"总 Token:    {s['total_tokens']:,} (输入 {s['total_input_tokens']:,} / 输出 {s['total_output_tokens']:,})")
    for p, g in s["by_provider"].items():
        print(f"  {p}: {g['calls']} 次, {g['input_tokens']+g['output_tokens']:,} tokens")
    print(f"{'='*60}\n")


def reset_token_tracker():
    """重置 token 统计。"""
    _tracker.reset()
