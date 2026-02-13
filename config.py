# -*- coding: utf-8 -*-
"""项目配置：Kimi API Key 等。"""
import os
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

# 从环境变量读取，或在此填写（勿提交到版本库）
KIMI_API_KEY = os.getenv("KIMI_API_KEY", "")
KIMI_BASE_URL = "https://api.moonshot.cn/v1"
# kimi-k2-turbo-preview 较快；kimi-latest 质量更高，可于 .env 中设置 KIMI_MODEL
KIMI_MODEL = os.getenv("KIMI_MODEL", "kimi-k2-turbo-preview")

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
