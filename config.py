# -*- coding: utf-8 -*-
"""项目配置：多模型 API Key 与端点。"""
import os
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()


def _env(key: str, default: str = "") -> str:
    return os.getenv(key, default).strip()


# ============ 默认 Provider ============
# 可选: kimi, openai, grok, perplexity, claude, gemini
LLM_PROVIDER = _env("LLM_PROVIDER", "kimi")

# ============ Kimi（月之暗面） ============
KIMI_API_KEY = _env("KIMI_API_KEY")
KIMI_BASE_URL = "https://api.moonshot.cn/v1"
KIMI_MODEL = _env("KIMI_MODEL", "kimi-k2-turbo-preview")
KIMI_VISION_MODEL = _env("KIMI_VISION_MODEL", "moonshot-v1-32k-vision-preview")

# ============ OpenAI（ChatGPT） ============
OPENAI_API_KEY = _env("OPENAI_API_KEY")
OPENAI_BASE_URL = _env("OPENAI_BASE_URL") or "https://api.openai.com/v1"
OPENAI_MODEL = _env("OPENAI_MODEL", "gpt-4o-mini")

# ============ xAI（Grok） ============
GROK_API_KEY = _env("GROK_API_KEY")
GROK_BASE_URL = "https://api.x.ai/v1"
GROK_MODEL = _env("GROK_MODEL", "grok-2")

# ============ Perplexity ============
PERPLEXITY_API_KEY = _env("PERPLEXITY_API_KEY")
PERPLEXITY_BASE_URL = "https://api.perplexity.ai"
PERPLEXITY_MODEL = _env("PERPLEXITY_MODEL", "llama-3.1-sonar-small-128k-online")

# ============ Anthropic（Claude） ============
ANTHROPIC_API_KEY = _env("ANTHROPIC_API_KEY")
ANTHROPIC_MODEL = _env("ANTHROPIC_MODEL", "claude-3-5-sonnet-20241022")

# ============ Google（Gemini） ============
GEMINI_API_KEY = _env("GEMINI_API_KEY")
GEMINI_MODEL = _env("GEMINI_MODEL", "gemini-2.5-pro")

# 项目路径
PROJECT_ROOT = Path(__file__).resolve().parent
OUTPUT_DIR = PROJECT_ROOT / "output"
RAW_DIR = OUTPUT_DIR / "raw"           # 爬取原始文本
REPORT_DIR = OUTPUT_DIR / "reports"    # 报告 1.0 / 2.0
EXPERT_DIR = OUTPUT_DIR / "experts"    # 专家意见

# 爬虫
MIN_CONTENT_BYTES = 1000   # 低于此字节数视为未完整遍历
RETRY_WAIT_SECONDS = 15    # 重试前等待秒数
CRAWL_MAX_RETRIES = 5      # 最大重试次数

for d in (OUTPUT_DIR, RAW_DIR, REPORT_DIR, EXPERT_DIR):
    d.mkdir(parents=True, exist_ok=True)
