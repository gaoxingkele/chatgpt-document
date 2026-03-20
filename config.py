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
GROK_MODEL = _env("GROK_MODEL", "grok-4-1-fast-non-reasoning")
GROK_REASONING_MODEL = _env("GROK_REASONING_MODEL", "grok-4.20-0309-reasoning")

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

# 报告语言
REPORT_LANGUAGE = _env("REPORT_LANGUAGE", "zh")

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

# ============ 内容截断限制（各 Step prompt 截取上限） ============
# Step2 报告 1.0
RAW_LOAD_LIMIT = 130_000               # 原始语料加载上限
OUTLINE_RAW_LIMIT = 80_000             # 构建大纲时语料截取
CHAPTER_INTRO_BODY_LIMIT = 25_000      # 章首章末正文截取
SUPPLEMENT_RAW_LIMIT = 70_000          # 补充缺失：原始语料截取
SUPPLEMENT_REPORT_LIMIT = 90_000       # 补充缺失：报告截取
DEDUP_REPORT_LIMIT = 100_000           # 去重：报告截取
ASSEMBLE_CHUNK_SIZE = 50_000           # 章节装配语料分块大小

# Step2 报告 3.0（step2_report_v3）
STRUCTURE_RAW_LIMIT = 60_000           # 规划结构时语料截取

# Step3 专家评审
EXPERT_PREVIEW_LIMIT = 60_000          # 专家评审报告截取

# Step4 报告 2.0
RAW_LOAD_LIMIT_V2 = 120_000            # 原始语料加载上限
HALLUCINATION_TEXT_LIMIT = 8_000       # 幻觉清单截取
REVISE_RAW_CHUNK_LIMIT = 35_000        # 整改时原始语料截取
REVISE_EXPERT_LIMIT = 25_000           # 整改时专家意见截取
REVISE_CHAPTER_BODY_LIMIT = 15_000     # 整改时章节正文截取

# Step5 报告 3.0 最终版
RAW_LOAD_LIMIT_FINAL = 100_000         # 原始语料加载上限
PROSE_RAW_LIMIT = 40_000               # 改写时原始语料截取（幻觉校验）
PROSE_CHAPTER_BODY_LIMIT = 18_000      # 改写时章节正文截取

# Step6 报告 4.0
CITATION_CHAPTER_BODY_LIMIT = 12_000   # 引用标注时章节正文截取

# Step7 风格化
POLICY_CHAPTER_BODY_LIMIT = 50_000     # 风格化章节正文截取
POLICY_RAW_PREVIEW_LIMIT = 8_000       # 风格化单章原始语料截取
SKILL_TEXT_LIMIT = 15_000              # Skill.md 截取
SUMMARY_TEXT_LIMIT = 12_000            # summary.md 截取
POLICY_RAW_TOTAL_LIMIT = 50_000        # 风格化原始语料总览截取

# Step8 迭代压缩
COMPRESS_SKILL_TEXT_LIMIT = 12_000     # 压缩时 Skill.md 截取
COMPRESS_SUMMARY_TEXT_LIMIT = 8_000    # 压缩时 summary.md 截取
COMPRESS_DOC_LIMIT = 60_000            # 压缩时文档截取

# Step4b 一致性校验
CONSISTENCY_REPORT_LIMIT = 80_000      # 一致性校验报告截取
CONSISTENCY_RAW_LIMIT = 30_000         # 一致性校验原始语料截取

# Step2 大纲审阅
OUTLINE_REVIEW_RAW_LIMIT = 60_000      # 大纲审阅时语料截取

# Step3 专家意见仲裁
ARBITRATE_EXPERT_LIMIT = 50_000        # 仲裁时专家意见截取

# ============ API 调用延迟（秒） ============
STEP6_CHAPTER_DELAY = float(_env("STEP6_CHAPTER_DELAY", "1.5"))
STEP8_ITERATION_DELAY = float(_env("STEP8_ITERATION_DELAY", "1"))

# ============ Step0b 语料预处理 ============
PREPROCESS_MODE = _env("PREPROCESS_MODE", "A")
PREPROCESS_NEAR_DEDUP_THRESHOLD = 0.85
PREPROCESS_PARAGRAPH_DEDUP_THRESHOLD = 0.90
PREPROCESS_MIN_BODY_CHARS = 500
PREPROCESS_TEXTRANK_SENTENCES = 5
PREPROCESS_CLUSTER_RANGE = (3, 10)
PREPROCESS_MAX_REPRESENTATIVES = 3
PREPROCESS_MINHASH_PERMS = 128

# ============ 支持的文件扩展名 ============
TEXT_EXTENSIONS = {".txt", ".md", ".json", ".html"}
DOCUMENT_EXTENSIONS = {".docx", ".pdf"}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}
CORPUS_EXTENSIONS = TEXT_EXTENSIONS | DOCUMENT_EXTENSIONS | IMAGE_EXTENSIONS

for d in (OUTPUT_DIR, RAW_DIR, REPORT_DIR, EXPERT_DIR, SKILL_DIR, FILES_DIR):
    d.mkdir(parents=True, exist_ok=True)
