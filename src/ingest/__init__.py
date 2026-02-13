# -*- coding: utf-8 -*-
"""
多平台对话记录采集：支持 ChatGPT、Gemini、Perplexity 的分享链接或导出文件。
统一输出为 output/raw/{name}.txt 供后续报告生成使用。
"""
from .sources import run_ingest, detect_source

__all__ = ["run_ingest", "detect_source"]
