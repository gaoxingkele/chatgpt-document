# -*- coding: utf-8 -*-
"""项目配置：多模型 API Key 与端点。"""
import os
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()


def _env(key: str, default: str = "") -> str:
    return os.getenv(key, default).strip()


# ============ 默认 Provider ============
# 优先: kimi, gemini, grok
# 候选: minimax, glm, qwen, deepseek, openai, perplexity, claude
LLM_PROVIDER = _env("LLM_PROVIDER", "kimi")

# ============ Kimi（月之暗面） ============
KIMI_API_KEY = _env("KIMI_API_KEY")
KIMI_BASE_URL = "https://api.moonshot.cn/v1"
KIMI_MODEL = _env("KIMI_MODEL", "kimi-k2.5")
KIMI_VISION_MODEL = _env("KIMI_VISION_MODEL", "moonshot-v1-32k-vision-preview")

# ============ Google（Gemini） ============
GEMINI_API_KEY = _env("GEMINI_API_KEY")
GEMINI_MODEL = _env("GEMINI_MODEL", "gemini-3.1-pro-preview")

# ============ xAI（Grok） ============
GROK_API_KEY = _env("GROK_API_KEY")
GROK_BASE_URL = "https://api.x.ai/v1"
GROK_MODEL = _env("GROK_MODEL", "grok-4-1-fast")

# ============ MiniMax ============
MINIMAX_API_KEY = _env("MINIMAX_API_KEY")
MINIMAX_BASE_URL = _env("MINIMAX_BASE_URL") or "https://api.minimax.chat/v1"
MINIMAX_MODEL = _env("MINIMAX_MODEL", "MiniMax-M2.5")

# ============ GLM（智谱清言） ============
GLM_API_KEY = _env("GLM_API_KEY")
_raw_glm_url = _env("GLM_BASE_URL") or "https://open.bigmodel.cn/api/paas/v4"
GLM_BASE_URL = _raw_glm_url.removesuffix("/chat/completions")
GLM_MODEL = _env("GLM_MODEL", "glm-4.7")
GLM_VISION_MODEL = _env("GLM_VISION_MODEL", "glm-4v-plus")

# ============ Qwen（通义千问） ============
QWEN_API_KEY = _env("QWEN_API_KEY") or _env("DASHSCOPE_API_KEY")
QWEN_BASE_URL = _env("QWEN_BASE_URL") or "https://dashscope.aliyuncs.com/compatible-mode/v1"
QWEN_MODEL = _env("QWEN_MODEL", "qwen3.5-plus")

# ============ DeepSeek ============
DEEPSEEK_API_KEY = _env("DEEPSEEK_API_KEY")
DEEPSEEK_BASE_URL = _env("DEEPSEEK_BASE_URL") or "https://api.deepseek.com"
DEEPSEEK_MODEL = _env("DEEPSEEK_MODEL", "deepseek-chat")

# ============ OpenAI（ChatGPT） ============
OPENAI_API_KEY = _env("OPENAI_API_KEY")
OPENAI_BASE_URL = _env("OPENAI_BASE_URL") or "https://api.openai.com/v1"
OPENAI_MODEL = _env("OPENAI_MODEL", "gpt-5.4")

# ============ Perplexity ============
PERPLEXITY_API_KEY = _env("PERPLEXITY_API_KEY")
PERPLEXITY_BASE_URL = "https://api.perplexity.ai"
PERPLEXITY_MODEL = _env("PERPLEXITY_MODEL", "sonar")

# ============ Anthropic（Claude） ============
ANTHROPIC_API_KEY = _env("ANTHROPIC_API_KEY")
ANTHROPIC_MODEL = _env("ANTHROPIC_MODEL", "claude-sonnet-4-6")

# 项目路径
PROJECT_ROOT = Path(__file__).resolve().parent
OUTPUT_DIR = PROJECT_ROOT / "output"
RAW_DIR = OUTPUT_DIR / "raw"           # 爬取原始文本
REPORT_DIR = OUTPUT_DIR / "reports"    # 报告 1.0 / 2.0
EXPERT_DIR = OUTPUT_DIR / "experts"    # 专家意见
SKILL_DIR = OUTPUT_DIR / "skill"       # Step7 风格化 Skill 目录
FILES_DIR = OUTPUT_DIR / "files"       # 用户语料目录（如 2026dong）

# 爬虫
MIN_CONTENT_BYTES = 1000   # 低于此字节数视为未完整遍历
RETRY_WAIT_SECONDS = 15    # 重试前等待秒数
CRAWL_MAX_RETRIES = 5      # 最大重试次数

for d in (OUTPUT_DIR, RAW_DIR, REPORT_DIR, EXPERT_DIR, SKILL_DIR, FILES_DIR):
    d.mkdir(parents=True, exist_ok=True)
