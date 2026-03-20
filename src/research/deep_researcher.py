# -*- coding: utf-8 -*-
"""
深度研究 Agent：GPT-Researcher 轻量替代。
零额外依赖，复用 llm_client + 搜索适配器。

核心算法：
1. 分析主题 → 生成研究计划（3-5 个子问题）
2. 对每个子问题 → 搜索 → 收集来源 + 摘要
3. 评估覆盖度 → 发现弱点 → 追问搜索（可选迭代）
4. 综合所有发现 → 生成结构化研究报告
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import List, Optional

from src.llm_client import chat
from src.research.search_adapters import SearchAdapter, SearchResult, get_search_adapter
from src.utils.log import log as _log


@dataclass
class ResearchFinding:
    """单条研究发现。"""
    question: str = ""
    answer: str = ""
    citations: List[dict] = field(default_factory=list)
    confidence: str = ""  # high / medium / low


@dataclass
class ResearchReport:
    """研究报告。"""
    topic: str = ""
    findings: List[ResearchFinding] = field(default_factory=list)
    synthesis: str = ""
    all_citations: List[dict] = field(default_factory=list)
    total_searches: int = 0
    elapsed_seconds: float = 0.0


def run_deep_research(
    topic: str,
    context: str = "",
    search_provider: str = "perplexity",
    max_questions: int = 5,
    max_iterations: int = 2,
    search_delay: float = 3.0,
) -> ResearchReport:
    """
    执行深度研究，返回结构化研究报告。

    Args:
        topic: 研究主题/问题
        context: 背景上下文（如报告摘要）
        search_provider: 搜索源 (perplexity/grok/gemini)
        max_questions: 最大子问题数
        max_iterations: 最大迭代轮次（1=不追问，2=追问一次）
        search_delay: 搜索间隔秒数（避免限流）

    Returns:
        ResearchReport: 结构化研究报告
    """
    t0 = time.time()
    adapter = get_search_adapter(search_provider)

    _log(f"深度研究开始: {topic[:60]}...")
    _log(f"  搜索源: {search_provider} | 最大问题数: {max_questions} | 迭代: {max_iterations}")

    # ========== Phase 1: 生成研究计划 ==========
    questions = _generate_research_plan(topic, context, max_questions)
    _log(f"  研究计划: {len(questions)} 个子问题")

    # ========== Phase 2: 逐个搜索 ==========
    findings: List[ResearchFinding] = []
    all_citations: List[dict] = []
    total_searches = 0

    for i, question in enumerate(questions):
        if i > 0:
            time.sleep(search_delay)

        _log(f"  [{i+1}/{len(questions)}] 搜索: {question[:60]}...")
        result = adapter.search(question, context)
        total_searches += 1

        if result.content:
            finding = ResearchFinding(
                question=question,
                answer=result.content,
                citations=result.citations,
            )
            findings.append(finding)
            all_citations.extend(result.citations)
            _log(f"  [{i+1}] 完成, {len(result.citations)} 个来源")
        else:
            _log(f"  [{i+1}] 无结果")

    # ========== Phase 3: 评估覆盖度 + 追问（可选） ==========
    if max_iterations >= 2 and findings:
        followup_questions = _evaluate_and_followup(topic, findings, context)
        if followup_questions:
            _log(f"  追问: {len(followup_questions)} 个补充问题")
            for i, fq in enumerate(followup_questions):
                time.sleep(search_delay)
                _log(f"  [追问 {i+1}/{len(followup_questions)}] {fq[:60]}...")
                result = adapter.search(fq, context)
                total_searches += 1
                if result.content:
                    findings.append(ResearchFinding(
                        question=fq,
                        answer=result.content,
                        citations=result.citations,
                    ))
                    all_citations.extend(result.citations)

    # ========== Phase 4: 综合研究发现 ==========
    synthesis = _synthesize_findings(topic, findings, context)

    # 去重引用
    seen_urls = set()
    unique_citations = []
    for c in all_citations:
        url = c.get("url", "")
        if url and url not in seen_urls:
            seen_urls.add(url)
            unique_citations.append(c)

    elapsed = time.time() - t0
    _log(f"深度研究完成: {total_searches} 次搜索, {len(unique_citations)} 个来源, {elapsed:.1f}s")

    return ResearchReport(
        topic=topic,
        findings=findings,
        synthesis=synthesis,
        all_citations=unique_citations,
        total_searches=total_searches,
        elapsed_seconds=elapsed,
    )


def _generate_research_plan(topic: str, context: str, max_questions: int) -> List[str]:
    """用 reasoning 模型分解研究主题为子问题。"""
    context_section = f"\n\n研究背景：\n{context[:3000]}" if context else ""
    prompt = f"""请将以下研究主题分解为 {max_questions} 个具体的搜索查询问题。

【研究主题】
{topic}
{context_section}

【要求】
1. 每个问题应聚焦一个具体方面，适合单次搜索
2. 问题之间不重叠，覆盖主题的不同维度
3. 包含：事实验证类、背景分析类、对立观点类、最新进展类
4. 用搜索引擎友好的表述（具体、明确、含关键实体）

直接输出问题列表，每行一个，不要编号或多余说明。"""

    resp = chat(
        [
            {"role": "system", "content": "你是研究规划专家。将复杂主题分解为精准的搜索查询。"},
            {"role": "user", "content": prompt},
        ],
        max_tokens=1024,
        temperature=0.3,
        reasoning=True,
    )

    questions = [q.strip().lstrip("0123456789.-) ") for q in resp.strip().split("\n") if q.strip() and len(q.strip()) > 10]
    return questions[:max_questions]


def _evaluate_and_followup(
    topic: str,
    findings: List[ResearchFinding],
    context: str,
) -> List[str]:
    """评估已有发现的覆盖度，生成追问问题。"""
    findings_summary = ""
    for f in findings:
        findings_summary += f"\n\n问题: {f.question}\n发现: {f.answer[:500]}"

    prompt = f"""评估以下研究发现对主题的覆盖度，找出遗漏。

【研究主题】{topic}

【已有发现】{findings_summary[:6000]}

【任务】
1. 哪些重要方面尚未覆盖？
2. 哪些发现需要更深入的验证？
3. 是否存在需要搜索对立观点的领域？

如果覆盖充分，输出"覆盖充分"。
否则输出 1-3 个补充搜索问题，每行一个。"""

    resp = chat(
        [
            {"role": "system", "content": "你是研究覆盖度评估专家。"},
            {"role": "user", "content": prompt},
        ],
        max_tokens=512,
        temperature=0.3,
        reasoning=True,
    )

    if "覆盖充分" in resp:
        return []

    questions = [q.strip().lstrip("0123456789.-) ") for q in resp.strip().split("\n") if q.strip() and len(q.strip()) > 10]
    return questions[:3]


def _synthesize_findings(
    topic: str,
    findings: List[ResearchFinding],
    context: str,
) -> str:
    """综合所有研究发现，生成结构化研究报告。"""
    findings_text = ""
    for i, f in enumerate(findings, 1):
        citations_str = ""
        if f.citations:
            citations_str = "\n来源: " + ", ".join(c.get("title", c.get("url", ""))[:50] for c in f.citations[:5])
        findings_text += f"\n\n### 发现 {i}: {f.question}\n{f.answer}{citations_str}"

    prompt = f"""请综合以下研究发现，输出一份结构化研究报告。

【研究主题】{topic}

【研究发现】{findings_text[:10000]}

【输出格式】
## 研究综述
（200字总结核心发现）

## 关键事实
（按重要性列出已验证的关键事实，附来源）

## 分析与洞察
（跨发现的交叉分析、因果推理、趋势判断）

## 争议与不确定性
（各方分歧、证据不足的领域、替代解释）

## 信息缺口
（尚未解答的问题、需要进一步研究的方向）

要求：审慎、证据导向，区分事实与推测。"""

    resp = chat(
        [
            {"role": "system", "content": "你是资深研究分析师。综合多源信息，输出平衡、有深度的研究报告。"},
            {"role": "user", "content": prompt},
        ],
        max_tokens=4096,
        temperature=0.3,
        reasoning=True,
    )
    return resp.strip()


def format_report_markdown(report: ResearchReport) -> str:
    """将研究报告格式化为 Markdown。"""
    lines = [
        f"# 深度研究报告: {report.topic}\n",
        f"搜索次数: {report.total_searches} | 来源数: {len(report.all_citations)} | 耗时: {report.elapsed_seconds:.1f}s\n",
        "---\n",
        report.synthesis,
        "\n\n---\n",
        "## 参考来源\n",
    ]
    for i, c in enumerate(report.all_citations, 1):
        title = c.get("title", c.get("url", ""))
        url = c.get("url", "")
        lines.append(f"{i}. [{title}]({url})")

    return "\n".join(lines)
