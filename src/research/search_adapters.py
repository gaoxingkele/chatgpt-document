# -*- coding: utf-8 -*-
"""
搜索适配器：统一接口，支持 Perplexity / Grok / Gemini 搜索。
默认 Perplexity（自带引用），Grok/Gemini 作为备选。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

from src.utils.log import log as _log


@dataclass
class SearchResult:
    """单条搜索结果。"""
    query: str = ""
    content: str = ""
    citations: List[dict] = field(default_factory=list)  # [{"url": str, "title": str}]


class SearchAdapter:
    """搜索源统一接口。"""

    def search(self, query: str, context: str = "", max_tokens: int = 4096) -> SearchResult:
        raise NotImplementedError


class PerplexitySearchAdapter(SearchAdapter):
    """Perplexity sonar-pro 搜索（自带引用，成本低，速度快）。"""

    def __init__(self, model: str = "sonar-pro"):
        self.model = model

    def search(self, query: str, context: str = "", max_tokens: int = 4096) -> SearchResult:
        from src.llm_client import perplexity_chat_with_citations

        system = "你是一位专业研究助手。请搜索相关资料，给出有据可查的回答，附来源。"
        if context:
            system += f"\n\n研究背景：{context[:2000]}"

        try:
            content, citations = perplexity_chat_with_citations(
                [
                    {"role": "system", "content": system},
                    {"role": "user", "content": query},
                ],
                model=self.model,
                max_tokens=max_tokens,
                temperature=0.3,
            )
            return SearchResult(query=query, content=content, citations=citations)
        except Exception as e:
            _log(f"  [Perplexity] 搜索失败: {e}")
            return SearchResult(query=query)


class GrokSearchAdapter(SearchAdapter):
    """Grok 搜索（实时 X/Twitter 数据优势）。"""

    def search(self, query: str, context: str = "", max_tokens: int = 4096) -> SearchResult:
        from src.llm_client import chat

        system = "你是一位拥有实时搜索能力的研究助手。请搜索最新信息回答问题，引用来源。"
        if context:
            system += f"\n\n研究背景：{context[:2000]}"

        try:
            content = chat(
                [
                    {"role": "system", "content": system},
                    {"role": "user", "content": query},
                ],
                provider="grok",
                max_tokens=max_tokens,
                temperature=0.3,
            )
            return SearchResult(query=query, content=content)
        except Exception as e:
            _log(f"  [Grok] 搜索失败: {e}")
            return SearchResult(query=query)


class GeminiSearchAdapter(SearchAdapter):
    """Gemini 搜索（学术文献覆盖好）。"""

    def search(self, query: str, context: str = "", max_tokens: int = 4096) -> SearchResult:
        from src.llm_client import chat

        system = "你是一位学术研究助手。请搜索相关学术文献和权威来源回答问题，引用来源。"
        if context:
            system += f"\n\n研究背景：{context[:2000]}"

        try:
            content = chat(
                [
                    {"role": "system", "content": system},
                    {"role": "user", "content": query},
                ],
                provider="gemini",
                max_tokens=max_tokens,
                temperature=0.3,
            )
            return SearchResult(query=query, content=content)
        except Exception as e:
            _log(f"  [Gemini] 搜索失败: {e}")
            return SearchResult(query=query)


def get_search_adapter(provider: str = "perplexity") -> SearchAdapter:
    """获取搜索适配器实例。"""
    adapters = {
        "perplexity": PerplexitySearchAdapter,
        "grok": GrokSearchAdapter,
        "gemini": GeminiSearchAdapter,
    }
    cls = adapters.get(provider.lower(), PerplexitySearchAdapter)
    return cls()
