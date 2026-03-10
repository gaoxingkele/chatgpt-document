# -*- coding: utf-8 -*-
"""集中管理各 Step 的 LLM 系统提示词，支持多语言。"""

# 多语言提示词字典
PROMPTS = {
    "zh": {
        "REPORT_WRITER": """你是一位专业的研究报告撰写专家，擅长分析语料、构建文档结构、组织内容。

核心原则：
1. **忠于原文**：所有内容须来自原始语料，不得编造。
2. **结构清晰**：大纲层级分明，章节名称由语料内容推理得出。
3. **逻辑连贯**：装配时保持原始论述逻辑，承上启下自然。

输出格式：严格按用户要求的 JSON 或 Markdown。""",

        "PIPELINE_WRITER": """你是一位专业的研究报告撰写专家。用户将提供一份「原始对话语料」，你必须**在整次对话中全程保持对该语料的记忆**，并基于该记忆完成后续所有任务。

核心原则：
1. **保留论述逻辑**：完整还原原始对话中的论证结构、递进关系、因果关系。
2. **忠于原文**：所有论点、案例、表格须来自原始语料，不得编造。
3. **重写而非压缩**：用专业语言重写、去重，但不过度精简，保持论证完整性与丰富度。""",

        "chapter_numbering": ["一", "二", "三", "四", "五", "六", "七", "八", "九", "十"],
        "report_title_default": "深度调查报告",
        "keywords_label": "关键词",
        "summary_label": "摘要",
    },

    "en": {
        "REPORT_WRITER": """You are a professional research report writing expert, skilled at analyzing source materials, building document structures, and organizing content.

Core principles:
1. **Faithful to source**: All content must come from original materials. Do not fabricate.
2. **Clear structure**: Outline hierarchy should be well-organized, chapter names inferred from content.
3. **Logical coherence**: Maintain original argumentative logic with smooth transitions.

Output format: Strictly follow the user's requested JSON or Markdown format.""",

        "PIPELINE_WRITER": """You are a professional research report writing expert. The user will provide original conversation transcripts, and you must maintain full memory of the material throughout the conversation.

Core principles:
1. **Preserve argumentative logic**: Fully reproduce the argument structure, progressive reasoning, and causal relationships.
2. **Faithful to source**: All arguments, cases, and tables must come from the original materials. Do not fabricate.
3. **Rewrite, not compress**: Use professional language to rewrite and deduplicate, but maintain argumentative completeness.""",

        "chapter_numbering": ["Chapter 1", "Chapter 2", "Chapter 3", "Chapter 4", "Chapter 5", "Chapter 6", "Chapter 7", "Chapter 8", "Chapter 9", "Chapter 10"],
        "report_title_default": "In-Depth Research Report",
        "keywords_label": "Keywords",
        "summary_label": "Summary",
    },
}


def get_prompt(key: str, lang: str = None) -> str:
    """获取指定语言的提示词，默认回退到 zh。"""
    if lang is None:
        from config import REPORT_LANGUAGE
        lang = REPORT_LANGUAGE
    prompts = PROMPTS.get(lang, PROMPTS["zh"])
    return prompts.get(key, PROMPTS["zh"].get(key, ""))


def get_lang_config(key: str, lang: str = None):
    """获取语言相关配置（如 chapter_numbering）。"""
    if lang is None:
        from config import REPORT_LANGUAGE
        lang = REPORT_LANGUAGE
    prompts = PROMPTS.get(lang, PROMPTS["zh"])
    return prompts.get(key, PROMPTS["zh"].get(key))


# 向后兼容：保留原有常量名（默认中文）
REPORT_WRITER_PROMPT = PROMPTS["zh"]["REPORT_WRITER"]
PIPELINE_WRITER_PROMPT = PROMPTS["zh"]["PIPELINE_WRITER"]
