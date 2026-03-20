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


def _evaluate_single_dimension(
    dim_key: str,
    dim: dict,
    report_text: str,
    raw_text: str,
    expert_persona: str,
    rubric_text: str,
    sota_knowledge: str,
) -> dict:
    """评估单个维度，返回 {score, assessment, issues}。"""
    focus_items = "\n".join(f"- {f}" for f in dim["focus"])

    rubric_section = ""
    if rubric_text:
        # 从 rubric 中提取该维度的标准
        import re
        pattern = rf"## {dim['name']}.*?(?=## |\Z)"
        match = re.search(pattern, rubric_text, re.DOTALL)
        if match:
            rubric_section = f"\n【评分标准】\n{match.group(0).strip()}\n"

    raw_section = ""
    if dim_key == "corpus_coverage" and raw_text:
        raw_section = f"\n【原始语料摘要（用于覆盖度比对）】\n{raw_text[:15000]}\n"

    sota_section = ""
    if sota_knowledge and dim_key in ("corpus_coverage", "internal_logic"):
        sota_section = f"\n【领域 SOTA 知识】\n{sota_knowledge[:3000]}\n"

    prompt = f"""请**仅**评估以下报告的「{dim['name']}」维度。

{dim['description']}

评估要点：
{focus_items}
{rubric_section}{raw_section}{sota_section}

【报告全文】
{report_text[:50000]}

【输出格式】严格输出 JSON：
{{
  "score": 0-100,
  "assessment": "100字评价，具体指出优缺点",
  "issues": [
    {{"location": "章节/段落位置", "problem": "具体问题", "suggestion": "修改建议", "severity": "高/中/低"}}
  ]
}}

请按以下步骤评估（Chain-of-Thought）：
1. 通读全文，列出与该维度相关的优点
2. 逐章检查，列出该维度的具体问题
3. 根据问题数量和严重程度给分
4. 输出 JSON

直接输出 JSON，不要代码块。"""

    resp = chat(
        [
            {"role": "system", "content": expert_persona + f"\n\n你当前只评估「{dim['name']}」这一个维度，请深入、具体。"},
            {"role": "user", "content": prompt},
        ],
        max_tokens=2048,
        temperature=0.2,
        reasoning=True,
    )

    try:
        from src.utils.file_utils import clean_json
        return json.loads(clean_json(resp))
    except (json.JSONDecodeError, Exception):
        return {"score": -1, "assessment": resp[:200], "issues": []}


def _verify_key_facts(report_text: str, domain: str) -> tuple[list, list]:
    """
    Chain-of-Verification：提取关键事实断言并用 Perplexity 验证。
    返回 (hallucinations, verified_facts)。
    """
    # Step 1: 提取关键事实断言
    _log("  Chain-of-Verification: 提取关键事实...")
    extract_resp = chat(
        [
            {"role": "system", "content": "从报告中提取所有可验证的事实断言（具体数据、日期、人物、事件）。"},
            {"role": "user", "content": f"提取以下报告中的关键事实断言（最多 10 条），每行一条：\n\n{report_text[:30000]}"},
        ],
        max_tokens=1024,
        temperature=0.2,
    )
    facts = [f.strip().lstrip("0123456789.-) ") for f in extract_resp.strip().split("\n") if f.strip() and len(f.strip()) > 15][:10]

    if not facts:
        return [], []

    # Step 2: Perplexity 验证
    _log(f"  Chain-of-Verification: 验证 {len(facts)} 条事实...")
    verify_prompt = f"""请验证以下关于{domain}的事实断言，逐条标注：
- ✅ 已验证（附来源）
- ⚠️ 部分准确（说明差异）
- ❌ 无法验证或与事实不符

事实断言：
""" + "\n".join(f"{i+1}. {f}" for i, f in enumerate(facts))

    try:
        verify_resp, _ = perplexity_chat_with_citations(
            [
                {"role": "system", "content": f"你是{domain}事实核查专家。逐条验证事实断言。"},
                {"role": "user", "content": verify_prompt},
            ],
            model="sonar-pro",
            max_tokens=4096,
            temperature=0.2,
        )
    except Exception as e:
        _log(f"  事实验证失败: {e}")
        return [], facts

    # 解析结果
    hallucinations = []
    for line in verify_resp.split("\n"):
        if "❌" in line:
            hallucinations.append(line.strip())

    verified_count = verify_resp.count("✅")
    _log(f"  验证结果: {verified_count} 条已验证, {len(hallucinations)} 条存疑")
    return hallucinations, facts


def _evaluate_report(
    report_text: str,
    raw_text: str,
    expert_persona: str,
    domain: str,
    sota_knowledge: str,
    policy_name: str = "",
) -> dict:
    """
    五维度并行评估 + Chain-of-Verification，返回结构化评估结果。
    """
    from src.utils.parallel import parallel_map
    from src.utils.prompt_loader import load_evaluation_rubric

    # 加载领域 rubric
    rubric_text = load_evaluation_rubric(policy_name) if policy_name else ""
    if rubric_text:
        _log(f"  已加载评分标准: {policy_name}/evaluation_rubric.md")

    # 并行评估 5 个维度
    dim_items = list(EVAL_DIMENSIONS.items())
    _log(f"  五维度并行评估中（{len(dim_items)} 个 reasoning 调用）...")
    t0 = time.time()

    def _eval_one(idx, item):
        dim_key, dim = item
        _log(f"    [{idx+1}/5] 评估: {dim['name']}...")
        result = _evaluate_single_dimension(
            dim_key, dim, report_text, raw_text, expert_persona, rubric_text, sota_knowledge,
        )
        _log(f"    [{idx+1}/5] {dim['name']}: {result.get('score', '?')}/100")
        return dim_key, result

    eval_results = parallel_map(_eval_one, dim_items)

    dimensions = {}
    for dim_key, result in eval_results:
        dimensions[dim_key] = result

    _log(f"  五维度评估完成，耗时 {time.time()-t0:.1f}s")

    # Chain-of-Verification
    cov_hallucinations, _ = _verify_key_facts(report_text, domain)

    # 汇总
    scores = [d.get("score", 0) for d in dimensions.values() if d.get("score", -1) >= 0]
    overall_score = int(sum(scores) / len(scores)) if scores else -1

    # 收集 top issues
    top_issues = []
    for dim_key, dim_result in dimensions.items():
        for issue in dim_result.get("issues", []):
            issue["dimension"] = dim_key
            top_issues.append(issue)
    top_issues.sort(key=lambda x: {"高": 0, "中": 1, "低": 2}.get(x.get("severity", "低"), 2))
    top_issues = top_issues[:10]

    # 合并幻觉（维度评估 + CoV）
    hallucinations = cov_hallucinations
    for dim_result in dimensions.values():
        for issue in dim_result.get("issues", []):
            if "幻觉" in issue.get("problem", "") or "编造" in issue.get("problem", ""):
                hallucinations.append(issue.get("problem", ""))

    # 遗漏主题
    missing_topics = []
    coverage = dimensions.get("corpus_coverage", {})
    for issue in coverage.get("issues", []):
        if "遗漏" in issue.get("problem", "") or "缺失" in issue.get("problem", ""):
            missing_topics.append(issue.get("problem", ""))

    # 总评
    assessments = [f"{k}: {v.get('assessment', '')}" for k, v in dimensions.items()]
    overall_assessment = f"总分 {overall_score}/100。" + " ".join(assessments)[:200]

    return {
        "domain": domain,
        "overall_score": overall_score,
        "overall_assessment": overall_assessment,
        "dimensions": dimensions,
        "top_issues": top_issues,
        "hallucinations": hallucinations,
        "missing_topics": missing_topics,
    }


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
    """注意：report_type 用于加载对应的 evaluation_rubric.md"""
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

    # 推断 policy_name
    policy_name = ""
    if report_type:
        try:
            from src.report_type_profiles import load_report_type_profile
            profile = load_report_type_profile(report_type)
            policy_name = profile.get("policy_name", "")
        except Exception:
            pass

    # 3. 五维度并行评估 + Chain-of-Verification
    eval_result = _evaluate_report(
        report_text, raw_text, expert_persona, domain, sota_knowledge, policy_name,
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
