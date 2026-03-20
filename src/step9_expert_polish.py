# -*- coding: utf-8 -*-
"""
Step9（可选）：深度研究专家润色。
使用 Perplexity sonar-deep-research 对最终报告进行三维度专家研究：
  A — 事实验证与数据增补
  B — 政策背景与学术深化
  C — 对立观点与平衡性
最后合并研究成果到报告正文。
"""
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import src  # noqa: F401

from config import REPORT_DIR
from src.llm_client import perplexity_chat_with_citations, chat
from src.utils.markdown_utils import parse_report_chapters as _parse_chapters, read_report_text as _read_report_text
from src.utils.docx_utils import save_docx_safe
from src.utils.log import log as _log


# ============ 三位深度研究专家定义 ============

EXPERT_A = {
    "name": "事实验证与数据增补",
    "system": """你是一位资深事实核查研究员。请对以下报告章节进行深度搜索研究：

1. **验证**：核查章节中所有关键事实、数据、人物、时间线、机构名称。标注哪些有可靠来源支撑。
2. **纠错**：若发现错误或过时信息，给出正确数据及来源。
3. **增补**：搜索章节未覆盖但高度相关的重要事实、最新进展、关键数据。
4. **格式**：输出结构化的研究发现，分为【已验证】【需纠正】【建议增补】三部分，每条附来源。""",
}

EXPERT_B = {
    "name": "政策背景与学术深化",
    "system": """你是一位政策研究与学术分析专家。请对以下报告章节进行深度搜索研究：

1. **政策文献**：搜索与章节议题直接相关的政策文件、法规、国际条约、官方声明。
2. **学术视角**：搜索相关学术论文、智库报告、专家分析，补充理论框架和分析深度。
3. **历史脉络**：补充关键历史背景和先例，帮助读者理解当前事态的演变逻辑。
4. **格式**：输出结构化的研究发现，分为【政策文献】【学术研究】【历史背景】三部分，每条附来源。""",
}

EXPERT_C = {
    "name": "对立观点与平衡性",
    "system": """你是一位批判性分析专家，专注于多元视角平衡。请对以下报告章节进行深度搜索研究：

1. **对立证据**：搜索与章节主要结论不同或对立的证据、数据、案例。
2. **替代解释**：对章节中的因果推理，搜索是否存在其他合理解释。
3. **争议标注**：标注哪些论断存在学术或政策争议，给出各方立场及来源。
4. **格式**：输出结构化的研究发现，分为【对立证据】【替代解释】【争议议题】三部分，每条附来源。""",
}

EXPERTS = [EXPERT_A, EXPERT_B, EXPERT_C]

# 中文章序号前缀
_CH_PREFIXES = ("一", "二", "三", "四", "五", "六", "七", "八", "九", "十")


def _merge_subchapters(chapters: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """
    将 parse_report_chapters 拆出的子章节合并为顶层大章。
    如 '一、背景...' 下的多个 ## 合并为一个大块。
    """
    if not chapters:
        return chapters

    merged: list[tuple[str, str]] = []
    current_title = ""
    current_body = ""

    def _top_level_key(title: str) -> str:
        """提取顶层章序号，如 '一、背景与战略框架' → '一'。"""
        title = title.strip()
        for prefix in _CH_PREFIXES:
            if title.startswith(prefix + "、") or title.startswith(prefix + "．") or title.startswith(prefix + ","):
                return prefix
        # 数字编号: '1.', '1 ', 'Chapter 1'
        import re
        m = re.match(r"^(\d+)[.\s、]", title)
        if m:
            return m.group(1)
        return title[:20]  # 无法识别时用标题前 20 字符

    for ch_title, ch_body in chapters:
        key = _top_level_key(ch_title)
        if key == _top_level_key(current_title) and current_title:
            # 同一大章，合并
            current_body += f"\n\n## {ch_title}\n\n{ch_body}"
        else:
            # 新的大章
            if current_title:
                merged.append((current_title, current_body))
            current_title = ch_title
            current_body = ch_body

    if current_title:
        merged.append((current_title, current_body))

    return merged


def _research_chapter(
    expert: dict,
    ch_title: str,
    ch_body: str,
    ch_idx: int,
    total_chapters: int,
) -> tuple[str, list[dict]]:
    """对单章调用单位专家的 deep research。"""
    prompt = f"""请对以下报告第 {ch_idx}/{total_chapters} 章进行深度研究。

【章节标题】{ch_title}

【章节内容】
{ch_body[:15000]}

请搜索相关资料，输出你的研究发现。"""

    _log(f"    [{expert['name']}] 研究第 {ch_idx} 章: {ch_title[:40]}...")
    t0 = time.time()
    max_retries = 3
    for attempt in range(1, max_retries + 1):
        try:
            content, citations = perplexity_deep_research(
                [
                    {"role": "system", "content": expert["system"]},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=4096,
            )
            _log(f"    [{expert['name']}] 第 {ch_idx} 章完成，耗时 {time.time()-t0:.1f}s，{len(citations)} 个引用")
            return content, citations
        except Exception as e:
            err_msg = str(e)
            if "429" in err_msg and attempt < max_retries:
                wait = 30 * attempt
                _log(f"    [{expert['name']}] 第 {ch_idx} 章限流，等待 {wait}s 后重试 ({attempt}/{max_retries})...")
                time.sleep(wait)
            else:
                _log(f"    [{expert['name']}] 第 {ch_idx} 章失败: {e}")
                return "", []
    return "", []


def _merge_research_into_chapter(
    ch_title: str,
    ch_body: str,
    research_results: list[tuple[str, str, list[dict]]],
) -> tuple[str, list[dict]]:
    """
    用主 LLM 将三位专家的研究成果合并到章节正文。
    返回 (增强后的章节文本, 新增引用列表)。
    """
    # 拼接研究发现
    research_text = ""
    all_citations = []
    for expert_name, content, citations in research_results:
        if content:
            research_text += f"\n\n### {expert_name}的研究发现\n{content}\n"
            all_citations.extend(citations)

    if not research_text.strip():
        return ch_body, []

    prompt = f"""请将以下三位深度研究专家的发现**融入**报告章节，输出增强后的完整章节。

【融入规则】
1. 将专家发现的**新事实、数据、引用**自然嵌入到正文对应位置，不要单独列出。
2. 对专家指出的**错误**，直接在正文中修正。
3. 对专家补充的**对立观点**，用审慎措辞嵌入（如"值得注意的是""也有分析认为"）。
4. 保持原文结构和风格不变，不要重写整章。
5. 在引用处标注 [n]（编号从 1 开始）。
6. **篇幅只增不减**，不要压缩原有内容。

【原始章节】
## {ch_title}

{ch_body}

【专家研究发现】
{research_text[:20000]}

请直接输出融入后的完整章节，以 `## {ch_title}` 开头。"""

    resp = chat(
        [
            {"role": "system", "content": "你是专业的报告编辑。任务：将外部研究发现自然融入报告正文，保持风格统一。"},
            {"role": "user", "content": prompt},
        ],
        max_tokens=16384,
        temperature=0.3,
    )
    return resp.strip(), all_citations


def run_expert_polish(
    report_path: Path,
    output_basename: str = None,
) -> dict:
    """
    Step9：对最终报告进行深度研究专家润色。

    流程：
    1. 整篇报告提交给 Perplexity sonar-deep-research（1 次调用）
    2. 要求从三个角度分析：事实验证、政策背景、对立观点
    3. 保存专家意见 MD
    4. 用主 LLM 分章将研究成果融入报告
    5. 输出增强版报告

    参数:
        report_path: 最终报告路径（Step7 或 Step8 输出）
        output_basename: 输出文件名前缀

    返回:
        {"report_path": str, "docx_path": str}
    """
    report_path = Path(report_path)
    if not report_path.is_file():
        raise FileNotFoundError(f"报告不存在: {report_path}")

    base = output_basename or report_path.stem
    report_text = _read_report_text(report_path)
    header, raw_chapters = _parse_chapters(report_text)

    if not raw_chapters:
        raise ValueError("无法拆分章节")

    chapters = _merge_subchapters(raw_chapters)
    num_chapters = len(chapters)

    _log("=" * 60)
    _log("Step9 深度研究专家润色：开始")
    _log(f"输入: {report_path.name} | {len(raw_chapters)} 子节 → {num_chapters} 大章")
    _log(f"调用: 1 次 deep research + {num_chapters} 次分章合并")
    _log("=" * 60)
    t0 = time.time()

    # ========== Phase 1: 整篇深度研究（1 次调用） ==========
    _log("Phase 1: 整篇报告 → Perplexity Deep Research（三角度分析）")

    # 截取报告摘要（取每章前 1200 字，总计控制在 8000 字内）
    report_digest = ""
    per_chapter_limit = min(1200, 8000 // max(num_chapters, 1))
    for ch_title, ch_body in chapters:
        report_digest += f"\n\n## {ch_title}\n{ch_body[:per_chapter_limit]}"
    report_digest = report_digest[:8000]

    research_prompt = f"""请对以下政治评论研究报告进行深度搜索研究，从三个角度给出分析：

## 角度 A：事实验证与数据增补
- 核查报告中所有关键事实、数据、人物、时间线
- 指出错误或过时信息，给出正确数据及来源
- 补充报告未覆盖的重要事实和最新进展

## 角度 B：政策背景与学术深化
- 搜索相关政策文件、国际条约、智库报告
- 补充学术论文和理论框架
- 梳理关键历史背景和先例

## 角度 C：对立观点与平衡性
- 搜索与报告主要结论不同或对立的证据
- 对因果推理给出替代解释
- 标注存在学术或政策争议的论断

请按 A/B/C 三个角度分别输出研究发现，每条附来源。

【报告内容】
{report_digest}"""

    research_content = ""
    research_citations = []
    t1 = time.time()
    max_retries = 3
    for attempt in range(1, max_retries + 1):
        try:
            research_content, research_citations = perplexity_chat_with_citations(
                [
                    {"role": "system", "content": "你是一位资深政治分析研究员，擅长多角度深度研究。请搜索大量相关资料，给出有据可查的研究发现。"},
                    {"role": "user", "content": research_prompt},
                ],
                model="sonar-pro",
                max_tokens=8192,
                temperature=0.3,
            )
            _log(f"Phase 1 完成，耗时 {time.time()-t1:.1f}s，{len(research_citations)} 个引用")
            break
        except Exception as e:
            if "429" in str(e) and attempt < max_retries:
                wait = 30 * attempt
                _log(f"  限流，等待 {wait}s 后重试 ({attempt}/{max_retries})...")
                time.sleep(wait)
            else:
                _log(f"  Perplexity 研究失败: {e}")
                break

    if not research_content:
        _log("[警告] Deep Research 无结果，输出原始报告")
        out_name = f"{base}_expert_polished"
        md_path = REPORT_DIR / f"{out_name}.md"
        md_path.write_text(report_text, encoding="utf-8")
        docx_path = save_docx_safe(report_text, REPORT_DIR / f"{out_name}.docx")
        return {"report_path": str(md_path), "docx_path": str(docx_path), "report_text": report_text}

    # ========== 保存专家意见 MD ==========
    from config import EXPERT_DIR
    opinion_path = EXPERT_DIR / f"{base}_Step9_深度研究意见.md"
    opinion_lines = [
        f"# Step9 深度研究专家意见\n",
        f"来源数: {len(research_citations)} 个引用\n",
        f"\n{research_content}\n",
    ]
    if research_citations:
        opinion_lines.append("\n## 引用来源\n")
        for i, ref in enumerate(research_citations, 1):
            opinion_lines.append(f"{i}. [{ref.get('title', '')}]({ref.get('url', '')})")
    opinion_path.write_text("\n".join(opinion_lines), encoding="utf-8")
    _log(f"专家意见已保存: {opinion_path.name}")

    # ========== Phase 2: 用 LLM 为每章提炼对应的补注 ==========
    _log(f"Phase 2: 为 {num_chapters} 章提炼章节补注")
    t2 = time.time()

    enhanced_parts: list[str] = []
    for ch_idx, (ch_title, ch_body) in enumerate(chapters):
        _log(f"  第 {ch_idx+1}/{num_chapters} 章: {ch_title[:40]}...")
        annotation = _extract_chapter_annotation(ch_title, ch_body, research_content)
        # 原文不动，补注追加在章末
        original = f"## {ch_title}\n\n{ch_body}" if not ch_body.strip().startswith("##") else ch_body
        if annotation.strip():
            enhanced_parts.append(f"{original}\n\n---\n\n> **【深度研究补注】**\n>\n{annotation}")
        else:
            enhanced_parts.append(original)

    _log(f"Phase 2 完成，耗时 {time.time()-t2:.1f}s")

    # ========== Phase 3: 拼接输出 ==========
    body = "\n\n".join(enhanced_parts)
    report_out = f"{header}\n\n{body}".strip()

    if research_citations:
        refs_lines = ["\n\n---\n\n## References (Deep Research)\n"]
        for i, ref in enumerate(research_citations, 1):
            title = ref.get("title", ref.get("url", ""))
            url = ref.get("url", "")
            refs_lines.append(f"[{i}] {title}. {url}")
        report_out += "\n".join(refs_lines)

    out_name = f"{base}_expert_polished"
    md_path = REPORT_DIR / f"{out_name}.md"
    md_path.write_text(report_out, encoding="utf-8")
    _log(f"已保存: {md_path.name}")

    docx_path = save_docx_safe(report_out, REPORT_DIR / f"{out_name}.docx")

    elapsed = time.time() - t0
    _log(f"Step9 完成: {len(research_citations)} 个引用，总耗时 {elapsed:.1f}s")
    _log(f"已保存: {docx_path.name}")

    return {
        "report_path": str(md_path),
        "docx_path": str(docx_path),
        "report_text": report_out,
    }


def _extract_chapter_annotation(
    ch_title: str,
    ch_body: str,
    research_content: str,
) -> str:
    """从整篇研究成果中提炼与本章相关的补注（简洁、有针对性）。"""
    prompt = f"""从以下深度研究发现中，提炼出与本章**直接相关**的补充信息，输出为简洁补注。

【本章标题】{ch_title}
【本章核心内容】{ch_body[:3000]}

【深度研究发现（三角度）】
{research_content[:6000]}

【输出要求】
1. 只提取与本章议题直接相关的内容，无关内容不要写
2. 分三类输出（如有）：
   - **事实补充**：本章未提及的重要事实或数据修正
   - **背景深化**：相关政策/学术视角补充
   - **争议提示**：与本章结论不同的观点或争议
3. 每条 1-2 句话，附来源（如有）
4. 若本章无需补注，输出"无需补注"
5. 用 > 引用格式输出每一条"""

    resp = chat(
        [
            {"role": "system", "content": "你是报告编辑助手。任务：从研究发现中提炼与指定章节相关的精简补注。只提取有价值的增量信息。"},
            {"role": "user", "content": prompt},
        ],
        max_tokens=2048,
        temperature=0.3,
    )
    result = resp.strip()
    if "无需补注" in result:
        return ""
    return result


def _save_expert_opinions(
    base: str,
    chapters: list[tuple[str, str]],
    research_by_chapter: dict[int, list],
) -> None:
    """将三位专家的研究意见保存为独立 MD 文件。"""
    from config import EXPERT_DIR

    for expert in EXPERTS:
        lines = [f"# Step9 深度研究专家意见 — {expert['name']}\n"]
        for ch_idx, (ch_title, _) in enumerate(chapters):
            results = research_by_chapter.get(ch_idx, [])
            content = ""
            citations = []
            for name, c, cites in results:
                if name == expert["name"]:
                    content = c
                    citations = cites
                    break
            lines.append(f"\n## 第 {ch_idx+1} 章: {ch_title}\n")
            if content:
                lines.append(content)
                if citations:
                    lines.append("\n**来源：**")
                    for ref in citations[:10]:
                        lines.append(f"- [{ref.get('title', '')}]({ref.get('url', '')})")
            else:
                lines.append("（无研究成果）")
            lines.append("")

        suffix = expert["name"].replace("与", "_")
        out_path = EXPERT_DIR / f"{base}_Step9_{suffix}.md"
        out_path.write_text("\n".join(lines), encoding="utf-8")
        _log(f"  专家意见已保存: {out_path.name}")


def _renumber_citations(text: str, offset: int) -> str:
    """将 [1],[2],... 重编号为 [offset+1],[offset+2],..."""
    def repl(m):
        n = int(m.group(1))
        return f"[{offset + n}]"
    return re.sub(r"\[(\d+)\]", repl, text)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Step9: 深度研究专家润色")
    parser.add_argument("report", type=Path, help="最终报告路径")
    parser.add_argument("-o", "--output-base", default=None, help="输出文件名前缀")
    args = parser.parse_args()
    run_expert_polish(args.report, args.output_base)
