# -*- coding: utf-8 -*-
"""
Step5: 在报告 2.0 基础上生成 3.0 最终版。
- 将过多的列表内容改为更自然流畅的叙述性语言
- 支持三种文档风格：A=商业模式设计报告，B=可行性研究报告，C=学术综述
"""
import re
import time
from pathlib import Path

import src  # noqa: F401  — 确保 PROJECT_ROOT 加入 sys.path

from config import REPORT_DIR, PROSE_RAW_LIMIT, PROSE_CHAPTER_BODY_LIMIT
from src.llm_client import chat
from src.utils.markdown_utils import parse_report_chapters as _parse_report_v1_chapters, extract_chapter_context as _extract_chapter_context
from src.utils.docx_utils import save_docx_safe
from src.utils.file_utils import load_raw_content as _load_raw_content
from src.utils.parallel import parallel_map

STYLE_PROMPTS = {
    "A": {
        "name": "商业模式设计报告",
        "desc": """本报告为**商业模式设计报告**。要求：
- 面向投资人、合作方、产品团队，突出商业逻辑与落地路径
- 语言简洁、决策导向，多用「可」「需」「将」等行动型表述
- 强调价值主张、收入来源、关键资源与成本结构
- 保留全部参数、表格与数据，用段落自然串联""",
    },
    "B": {
        "name": "可行性研究报告",
        "desc": """本报告为**可行性研究报告**。要求：
- 面向立项评审、决策层，突出可行性、风险与建议
- 语言严谨、论证充分，多用「经评估」「建议」「需注意」等
- 强调技术可行性、经济可行性、合规边界与实施路径
- 保留全部参数、表格与数据，用段落自然串联""",
    },
    "C": {
        "name": "学术综述",
        "desc": """本报告为**学术综述**。要求：
- 面向学术发表或行业研究，突出系统性、综述性与引用价值
- 语言规范、逻辑严密，多用「研究表明」「现有文献」「综上所述」等
- 强调概念界定、理论框架、研究进展与展望
- 保留全部参数、表格与数据，用段落自然串联""",
    },
}


from src.utils.log import log as _log


def _api_convert_chapter_to_prose(
    chapter_title: str,
    chapter_body: str,
    style_desc: str,
    raw_chunk: str,
    chapter_idx: int,
    total_chapters: int,
    context: dict = None,
) -> str:
    """将单章内容转换为自然叙述文体，应用指定风格；并剔除报告 2.0 中未在原始语料出现的幻觉内容。"""
    hallucination_rule = ""
    if raw_chunk:
        hallucination_rule = f"""
5. **幻觉剔除（必须执行）**：报告 2.0 中若有**新的知识、新的观点、新的数据或案例**，若在下方【原始语料】中**未曾出现**，一律视为幻觉，须删除。报告 3.0 的内容范围与事实必须严格符合原始语料，不得超出或编造。

【原始语料】（ChatGPT 等对话的原始文本，为内容与事实的唯一起源）
---
{raw_chunk[:PROSE_RAW_LIMIT]}
---
"""
    prompt = f"""请将以下报告章节改写为**自然流畅的叙述性语言**，输出完整章节正文。

【本章标题】{chapter_title}

【风格要求】
{style_desc}

【核心改写规则（必须遵守）】
1. **列表改段落**：将过多的 - 列表、①②③ 条目、编号列表，改写为连贯的段落叙述。可保留少量必要的要点列表（如参数表、对照表），但主体内容应为叙述性段落。
2. **自然衔接**：用「首先」「其次」「在此基础上」「具体而言」等过渡词串联，使阅读如文章而非大纲。
3. **信息不丢失**：所有**在原始语料中有依据**的论证、案例、数据、参数须完整保留，仅改变呈现形式。
4. **篇幅相当**：输出长度与原文相当或略长，不得压缩删减。{hallucination_rule}

【本章原文（报告 2.0）】
---
{chapter_body[:PROSE_CHAPTER_BODY_LIMIT]}
---

"""
    # 章节上下文注入（仅较长章节）
    if context and len(chapter_body) >= 1500:
        ctx_section = "\n【章节上下文（供衔接参考）】\n"
        if context.get("toc"):
            ctx_section += f"全文目录：\n{context['toc']}\n"
        if context.get("prev_summary"):
            ctx_section += f"上一章末尾：{context['prev_summary']}\n"
        if context.get("next_summary"):
            ctx_section += f"下一章开头：{context['next_summary']}\n"
        prompt += ctx_section

    prompt += f"""
请直接输出改写后的完整章节，以 `## {chapter_title}` 开头，使用 Markdown（### 等）。不要 JSON 或多余说明。"""

    system_content = "你是专业的文档改写专家。核心任务：将列表式、大纲式内容改写为自然流畅的叙述文体，同时保持信息完整、逻辑清晰。"
    if raw_chunk:
        system_content += " 重要：报告内容须严格忠于原始语料，删除报告 2.0 中未在原始语料出现的新知识、新观点、新数据（视为幻觉）。"
    system_content += " 输出严格为 Markdown。"

    resp = chat(
        [
            {"role": "system", "content": system_content},
            {"role": "user", "content": prompt},
        ],
        max_tokens=16384,
        temperature=0.4,
    )
    return resp.strip()


def run_report_final(
    report_v2_path: Path,
    output_basename: str = None,
    style: str = "A",
    raw_path: Path = None,
) -> dict:
    """
    根据报告 2.0 生成 3.0 最终版。
    style: A=商业模式设计报告, B=可行性研究报告, C=学术综述
    raw_path: 原始语料路径（必填，用于幻觉校验，剔除 2.0 中未在原始语料出现的内容）
    返回 report_v3_path（.md）与 docx_path（.docx）。
    """
    report_v2_path = Path(report_v2_path)
    if not report_v2_path.is_file():
        raise FileNotFoundError(f"报告 2.0 不存在: {report_v2_path}")

    style_upper = style.upper()
    if style_upper not in STYLE_PROMPTS:
        raise ValueError(f"风格须为 A/B/C 之一，当前: {style}")
    style_info = STYLE_PROMPTS[style_upper]

    base = output_basename or report_v2_path.stem.replace("_report_v2", "").replace("_report_v2_new", "")
    report_v2_text = report_v2_path.read_text(encoding="utf-8", errors="replace")

    raw_text = _load_raw_content(raw_path) if raw_path else ""
    if raw_path and not raw_text:
        _log(f"[警告] 未加载到原始语料: {raw_path}，无法进行幻觉校验")

    header, chapters = _parse_report_v1_chapters(report_v2_text)
    num_chapters = len(chapters)

    _log("=" * 60)
    _log("Step5 报告 3.0 最终版：开始")
    _log(f"报告 2.0: 约 {len(report_v2_text)} 字 | 风格: {style_info['name']} ({style_upper})")
    _log(f"章节数: {num_chapters} | 原始语料: 约 {len(raw_text)} 字（幻觉校验）")
    _log("=" * 60)
    t0 = time.time()

    # 更新头部：标注 3.0 与风格
    header_v3 = header
    if "2.0" in header or "补充完整版" in header:
        header_v3 = re.sub(r"（补充完整版）|2\.0", "3.0 最终版", header_v3, count=1)
    if "## " not in header_v3.split("\n")[0]:
        first_line = header_v3.split("\n")[0]
        if first_line.startswith("# "):
            header_v3 = header_v3.replace(first_line, first_line + f"（{style_info['name']}）", 1)

    contexts = _extract_chapter_context(chapters)

    def _convert_one(idx, chapter):
        ch_title, ch_body = chapter
        _log(f"[并行] 改写第 {idx + 1}/{num_chapters} 章: {ch_title[:40]}...")
        revised = _api_convert_chapter_to_prose(
            ch_title,
            ch_body,
            style_info["desc"],
            raw_text,
            idx + 1,
            num_chapters,
            context=contexts[idx],
        )
        _log(f"[并行] 第 {idx + 1} 章完成，输出约 {len(revised)} 字")
        return revised

    prose_parts = parallel_map(_convert_one, chapters)

    report_v3_body = "\n\n".join(prose_parts)
    report_v3_text = f"{header_v3}\n\n{report_v3_body}".strip()

    _log(f"报告 3.0 生成完成，总耗时 {time.time()-t0:.1f}s，约 {len(report_v3_text)} 字")

    report_v3_path = REPORT_DIR / f"{base}_report_v3.md"
    report_v3_path.write_text(report_v3_text, encoding="utf-8")
    _log(f"报告 3.0 (Markdown) 已保存: {report_v3_path.name}")

    _log("导出 Word：报告 3.0 → .docx")
    docx_path = save_docx_safe(report_v3_text, REPORT_DIR / f"{base}_report_v3.docx")
    _log(f"Step5 完成：报告 3.0 (Word) 已保存 {docx_path.name}")

    return {
        "report_v3_path": str(report_v3_path),
        "docx_path": str(docx_path),
        "report_v3_text": report_v3_text,
    }
