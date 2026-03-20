# -*- coding: utf-8 -*-
"""
Step3b: 领域自适应专家评估（替代 Step3+Step4 的膨胀-压缩循环）。

流程：
1. 自动识别报告领域 → 生成领域专家人设
2. Perplexity 搜索领域 SOTA 知识作为评估基准
3. 五维度精准评估：文本质量、语料覆盖、内在逻辑、章节递进、重点突出
4. 输出结构化评估报告（评分 + 具体修改意见）

评估结果供 Step5 直接消费，实现 v1 → v3 一步改写。
"""
import json
import time
from pathlib import Path

import src  # noqa: F401

from config import EXPERT_DIR, REPORT_DIR, EXPERT_PREVIEW_LIMIT
from src.llm_client import chat, perplexity_chat_with_citations
from src.utils.log import log as _log
from src.utils.file_utils import load_raw_content as _load_raw_content


# ============ 五维度评估框架 ============

EVAL_DIMENSIONS = {
    "text_quality": {
        "name": "文本质量",
        "description": "语言表达的准确性、流畅性、专业性。是否有 AI 味、套话、冗余表述、语法错误。",
        "focus": [
            "术语使用是否准确、符合领域惯例",
            "句式是否多样、自然，有无机械排比或模板化表达",
            "段落衔接是否流畅，过渡是否生硬",
            "是否有空洞概括代替具体论述的问题",
        ],
    },
    "corpus_coverage": {
        "name": "语料覆盖",
        "description": "报告对原始语料的覆盖程度。是否遗漏重要信息，是否有编造（幻觉）。",
        "focus": [
            "原始语料中的关键事实、数据、案例是否被纳入",
            "是否存在报告中有但语料中没有的内容（幻觉）",
            "覆盖是否均衡，有无重要主题被忽略",
            "引用来源是否可追溯到原始语料",
        ],
    },
    "internal_logic": {
        "name": "内在逻辑",
        "description": "论证的逻辑自洽性。因果推理、论据支撑、结论推导是否严密。",
        "focus": [
            "论点与论据是否匹配，有无逻辑跳跃",
            "因果关系推导是否合理，有无混淆相关与因果",
            "不同章节的观点是否相互矛盾",
            "结论是否由前文论证自然推出",
        ],
    },
    "chapter_progression": {
        "name": "章节递进",
        "description": "章节间的逻辑顺序和递进关系。是否由浅入深、环环相扣。",
        "focus": [
            "章节排列顺序是否合理（背景→现状→分析→结论）",
            "相邻章节的衔接是否自然，是否有突兀跳跃",
            "各章节篇幅是否均衡，有无严重失衡",
            "是否存在重复章节或可合并的内容",
        ],
    },
    "focus_emphasis": {
        "name": "重点突出",
        "description": "核心论点是否鲜明，重要内容是否得到充分展开，次要内容是否精简。",
        "focus": [
            "报告的核心论点是否清晰可辨",
            "高价值内容（关键数据、重要案例）是否充分展开",
            "低价值内容（背景铺垫、重复论述）是否过多",
            "读者能否在 30 秒内把握报告核心结论",
        ],
    },
}


def _detect_domain_and_build_persona(report_preview: str) -> tuple[str, str]:
    """
    自动识别报告领域，生成领域专家人设。
    返回 (domain_name, expert_persona)。
    """
    prompt = f"""分析以下报告的核心领域，输出 JSON：

{{
  "domain": "领域名称（如：国际安全与反毒品政策、人工智能伦理、新能源产业...）",
  "sub_domains": ["子领域1", "子领域2", "子领域3"],
  "expert_persona": "一段 100 字以内的专家人设描述，说明这位评审专家的学术背景、研究方向、评审资质",
  "key_concepts": ["报告中的核心概念1", "核心概念2", "核心概念3", "核心概念4", "核心概念5"],
  "evaluation_focus": "针对此领域，评估时应特别关注什么（50字）"
}}

【报告预览】
{report_preview[:8000]}

直接输出 JSON，不要代码块。"""

    _log("  识别报告领域，生成专家人设...")
    resp = chat(
        [
            {"role": "system", "content": "你是学术领域分类专家。根据文本内容精准识别研究领域并构建对应的评审专家画像。输出严格 JSON。"},
            {"role": "user", "content": prompt},
        ],
        max_tokens=1024,
        temperature=0.2,
        reasoning=True,
    )

    try:
        from src.utils.file_utils import clean_json
        data = json.loads(clean_json(resp))
    except (json.JSONDecodeError, Exception):
        data = {
            "domain": "综合研究",
            "sub_domains": [],
            "expert_persona": "跨学科研究学者，擅长多领域深度分析与质量评估",
            "key_concepts": [],
            "evaluation_focus": "整体质量与逻辑严密性",
        }

    domain = data.get("domain", "综合研究")
    persona = data.get("expert_persona", "")
    key_concepts = data.get("key_concepts", [])
    eval_focus = data.get("evaluation_focus", "")

    # 构建完整专家人设
    full_persona = f"""你是一位{domain}领域的资深评审专家。
{persona}

你熟悉以下核心概念：{', '.join(key_concepts)}。
评估重点：{eval_focus}。

你的评估标准：
- 以该领域顶级期刊/智库报告的水准为基准
- 对事实准确性零容忍，可疑之处必须标注
- 对逻辑漏洞敏感，能区分相关性与因果性
- 对文本质量有精准判断，能识别 AI 生成痕迹"""

    _log(f"  领域: {domain}")
    return domain, full_persona


def _search_domain_sota(domain: str, key_concepts: list[str], report_preview: str) -> str:
    """
    用 Perplexity 搜索领域 SOTA 知识，作为评估基准。
    返回搜索结果文本。
    """
    concepts_str = "、".join(key_concepts[:5]) if key_concepts else domain
    prompt = f"""请搜索以下领域的最新研究进展和权威观点，作为评审基准：

领域：{domain}
核心概念：{concepts_str}

请提供：
1. 该领域 2025-2026 年的最新重要进展（3-5 条）
2. 当前学术界/政策界的主流观点和争议焦点
3. 该领域最权威的数据来源和参考标准

【待评审报告摘要】
{report_preview[:3000]}"""

    _log("  搜索领域 SOTA 知识作为评估基准...")
    try:
        content, citations = perplexity_chat_with_citations(
            [
                {"role": "system", "content": f"你是{domain}领域的研究助手。请搜索该领域最新、最权威的信息。"},
                {"role": "user", "content": prompt},
            ],
            model="sonar-pro",
            max_tokens=4096,
            temperature=0.3,
        )
        if citations:
            content += "\n\n**参考来源：**\n" + "\n".join(
                f"- [{c.get('title', '')}]({c.get('url', '')})" for c in citations[:10]
            )
        _log(f"  SOTA 搜索完成，{len(citations)} 个来源")
        return content
    except Exception as e:
        _log(f"  SOTA 搜索失败: {e}，使用通用评估标准")
        return ""


def _evaluate_report(
    report_text: str,
    raw_text: str,
    expert_persona: str,
    domain: str,
    sota_knowledge: str,
) -> dict:
    """
    五维度精准评估，返回结构化评估结果。
    """
    dimensions_desc = ""
    for dim_key, dim in EVAL_DIMENSIONS.items():
        focus_items = "\n".join(f"    - {f}" for f in dim["focus"])
        dimensions_desc += f"""
### {dim['name']}（{dim_key}）
{dim['description']}
评估要点：
{focus_items}
"""

    sota_section = ""
    if sota_knowledge:
        sota_section = f"""
【领域 SOTA 知识（评估基准）】
{sota_knowledge[:5000]}
"""

    raw_section = ""
    if raw_text:
        raw_section = f"""
【原始语料摘要（用于覆盖度评估）】
{raw_text[:15000]}
"""

    prompt = f"""请对以下报告进行**五维度精准评估**。

{sota_section}
{raw_section}

【评估维度】
{dimensions_desc}

【报告全文】
{report_text[:60000]}

【输出格式】严格输出以下 JSON：
{{
  "domain": "{domain}",
  "overall_score": 0-100,
  "overall_assessment": "200字总体评价",
  "dimensions": {{
    "text_quality": {{
      "score": 0-100,
      "assessment": "100字评价",
      "issues": [
        {{"location": "章节/段落位置", "problem": "具体问题", "suggestion": "修改建议", "severity": "高/中/低"}}
      ]
    }},
    "corpus_coverage": {{
      "score": 0-100,
      "assessment": "100字评价",
      "issues": [...]
    }},
    "internal_logic": {{
      "score": 0-100,
      "assessment": "100字评价",
      "issues": [...]
    }},
    "chapter_progression": {{
      "score": 0-100,
      "assessment": "100字评价",
      "issues": [...]
    }},
    "focus_emphasis": {{
      "score": 0-100,
      "assessment": "100字评价",
      "issues": [...]
    }}
  }},
  "top_issues": [
    {{"dimension": "维度名", "location": "位置", "problem": "问题", "suggestion": "修改建议", "severity": "高"}}
  ],
  "hallucinations": ["疑似幻觉内容1", "疑似幻觉内容2"],
  "missing_topics": ["遗漏的重要主题1", "遗漏的重要主题2"]
}}

要求：
1. 评分标准：90+ 优秀，80-89 良好，70-79 中等，60-69 及格，<60 不合格
2. issues 只列有价值的具体问题（每维度最多 5 条），不要泛泛而谈
3. top_issues 列出全文最需优先修改的 5-10 个问题（按严重程度排序）
4. hallucinations 列出报告中疑似编造的内容（与原始语料不符的事实）
5. missing_topics 列出原始语料中有但报告中遗漏的重要主题

直接输出 JSON，不要代码块。"""

    _log("  五维度评估中（reasoning 模型）...")
    t0 = time.time()
    resp = chat(
        [
            {"role": "system", "content": expert_persona},
            {"role": "user", "content": prompt},
        ],
        max_tokens=8192,
        temperature=0.2,
        reasoning=True,
    )
    _log(f"  评估完成，耗时 {time.time()-t0:.1f}s")

    try:
        from src.utils.file_utils import clean_json
        result = json.loads(clean_json(resp))
    except (json.JSONDecodeError, Exception):
        _log("  [警告] 评估 JSON 解析失败，保存原始响应")
        result = {"raw_response": resp, "overall_score": -1}

    return result


def _save_evaluation_report(base: str, eval_result: dict, domain: str, sota_knowledge: str) -> Path:
    """将评估结果保存为可读 MD 文件。"""
    lines = [f"# Step3b 领域专家评估报告\n"]
    lines.append(f"**领域**: {domain}")
    lines.append(f"**总分**: {eval_result.get('overall_score', 'N/A')}/100\n")
    lines.append(f"**总评**: {eval_result.get('overall_assessment', '')}\n")

    # 五维度评分
    lines.append("## 五维度评分\n")
    lines.append("| 维度 | 分数 | 评价 |")
    lines.append("|------|------|------|")
    dims = eval_result.get("dimensions", {})
    for dim_key, dim_info in EVAL_DIMENSIONS.items():
        d = dims.get(dim_key, {})
        score = d.get("score", "N/A")
        assessment = d.get("assessment", "").replace("\n", " ")[:80]
        lines.append(f"| {dim_info['name']} | {score} | {assessment} |")
    lines.append("")

    # 各维度详细问题
    for dim_key, dim_info in EVAL_DIMENSIONS.items():
        d = dims.get(dim_key, {})
        issues = d.get("issues", [])
        if issues:
            lines.append(f"### {dim_info['name']}（{d.get('score', 'N/A')}分）\n")
            lines.append(d.get("assessment", ""))
            lines.append("")
            for issue in issues:
                severity = issue.get("severity", "中")
                lines.append(f"- **[{severity}]** {issue.get('location', '')}: {issue.get('problem', '')}")
                lines.append(f"  - 建议: {issue.get('suggestion', '')}")
            lines.append("")

    # 优先修改清单
    top_issues = eval_result.get("top_issues", [])
    if top_issues:
        lines.append("## 优先修改清单\n")
        for i, issue in enumerate(top_issues, 1):
            lines.append(f"{i}. **[{issue.get('severity', '高')}] [{issue.get('dimension', '')}]** {issue.get('location', '')}")
            lines.append(f"   问题: {issue.get('problem', '')}")
            lines.append(f"   建议: {issue.get('suggestion', '')}")
        lines.append("")

    # 幻觉清单
    hallucinations = eval_result.get("hallucinations", [])
    if hallucinations:
        lines.append("## 疑似幻觉清单\n")
        for h in hallucinations:
            lines.append(f"- {h}")
        lines.append("")

    # 遗漏主题
    missing = eval_result.get("missing_topics", [])
    if missing:
        lines.append("## 遗漏的重要主题\n")
        for m in missing:
            lines.append(f"- {m}")
        lines.append("")

    # SOTA 知识参考
    if sota_knowledge:
        lines.append("## 领域 SOTA 参考（评估基准）\n")
        lines.append(sota_knowledge[:3000])
        lines.append("")

    md_path = EXPERT_DIR / f"{base}_Step3b_评估报告.md"
    md_path.write_text("\n".join(lines), encoding="utf-8")
    return md_path


def run_expert_eval(
    report_v1_path: Path,
    output_basename: str = None,
    raw_path: Path = None,
    report_type: str = None,
) -> dict:
    """
    Step3b: 领域自适应专家评估。

    流程：
    1. 自动识别领域 → 生成专家人设
    2. Perplexity 搜索 SOTA 知识
    3. 五维度评估（reasoning 模型）
    4. 输出结构化评估报告

    返回：
        {"eval_path": str, "eval_json_path": str, "eval_result": dict}
    """
    report_v1_path = Path(report_v1_path)
    if not report_v1_path.is_file():
        raise FileNotFoundError(f"报告不存在: {report_v1_path}")

    base = output_basename or report_v1_path.stem.replace("_report_v1", "")
    report_text = report_v1_path.read_text(encoding="utf-8", errors="replace")
    raw_text = _load_raw_content(raw_path) if raw_path else ""

    _log("=" * 60)
    _log("Step3b 领域专家评估：开始")
    _log(f"报告: {report_v1_path.name}, 约 {len(report_text)} 字")
    _log(f"原始语料: {raw_path.name if raw_path else '未提供'}, 约 {len(raw_text)} 字")
    _log("=" * 60)
    t0 = time.time()

    # 1. 领域识别 + 专家人设
    domain, expert_persona = _detect_domain_and_build_persona(report_text)

    # 提取关键概念（从领域检测结果复用）
    key_concepts = []
    try:
        # 尝试从 meta.json 获取 keywords
        meta_path = REPORT_DIR / f"{base}_meta.json"
        if meta_path.is_file():
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            key_concepts = meta.get("keywords", [])
    except Exception:
        pass

    # 2. SOTA 知识搜索
    sota_knowledge = _search_domain_sota(domain, key_concepts, report_text)

    # 3. 五维度评估
    eval_result = _evaluate_report(
        report_text, raw_text, expert_persona, domain, sota_knowledge,
    )

    # 4. 保存评估报告
    md_path = _save_evaluation_report(base, eval_result, domain, sota_knowledge)
    _log(f"评估报告已保存: {md_path.name}")

    # 保存 JSON（供 Step5 消费）
    json_path = EXPERT_DIR / f"{base}_Step3b_评估结果.json"
    json_path.write_text(
        json.dumps(eval_result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    _log(f"评估 JSON 已保存: {json_path.name}")

    # 输出摘要
    score = eval_result.get("overall_score", -1)
    dims = eval_result.get("dimensions", {})
    _log(f"\n  总分: {score}/100")
    for dim_key, dim_info in EVAL_DIMENSIONS.items():
        d = dims.get(dim_key, {})
        _log(f"  {dim_info['name']}: {d.get('score', 'N/A')}/100")
    top_n = len(eval_result.get("top_issues", []))
    _log(f"  优先修改: {top_n} 条")
    _log(f"  疑似幻觉: {len(eval_result.get('hallucinations', []))} 条")
    _log(f"  遗漏主题: {len(eval_result.get('missing_topics', []))} 条")

    elapsed = time.time() - t0
    _log(f"\nStep3b 完成，总耗时 {elapsed:.1f}s")

    return {
        "eval_path": str(md_path),
        "eval_json_path": str(json_path),
        "eval_result": eval_result,
    }


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Step3b: 领域自适应专家评估")
    parser.add_argument("report", type=Path, help="报告路径（如 _report_v1.md）")
    parser.add_argument("-r", "--raw-file", type=Path, default=None, help="原始语料路径")
    parser.add_argument("-o", "--output-base", default=None, help="输出文件名前缀")
    args = parser.parse_args()
    run_expert_eval(args.report, args.output_base, args.raw_file)
