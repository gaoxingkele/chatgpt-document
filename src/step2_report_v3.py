# -*- coding: utf-8 -*-
"""
报告 3.0：先规划文档结构，再按章节分段生成，确保篇幅充足、不丢失信息。
流程：1) 生成 5~7 章结构 2) 逐章调用 API 生成内容 3) 合并输出 report_v3
"""
import json
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config import RAW_DIR, REPORT_DIR
from src.kimi_client import chat
from src.step4_report_v2 import md_to_docx


def _load_raw_content(raw_path: Path, max_chars: int = 130000) -> str:
    text = raw_path.read_text(encoding="utf-8", errors="replace")
    if len(text) > max_chars:
        text = text[:max_chars] + "\n\n[内容已截断]"
    return text


# 章节序号对应中文大写
_CHAPTER_CN = ("一", "二", "三", "四", "五", "六", "七")


def _parse_structure(json_str: str) -> list:
    """解析结构 JSON，返回章节列表。"""
    s = json_str.strip()
    for start in ("```json", "```"):
        if s.startswith(start):
            s = s[len(start):].strip()
        if s.endswith("```"):
            s = s[:-3].strip()
    try:
        data = json.loads(s)
        return data.get("chapters", data) if isinstance(data, dict) else data
    except json.JSONDecodeError:
        return []


def run_report_v3(raw_path: Path, output_basename: str = None) -> dict:
    """
    报告 3.0 生成流程：
    1. 规划文档结构（5~7 章）
    2. 按章节分段调用 API，逐章生成内容
    3. 合并为完整报告，保存 Markdown 与 Word
    """
    raw_path = Path(raw_path)
    if not raw_path.is_file():
        raise FileNotFoundError(f"原始文件不存在: {raw_path}")
    content = _load_raw_content(raw_path)
    base = output_basename or raw_path.stem

    # --- 3.1 规划文档结构
    print("[报告 3.0] Step 1/3: 规划文档结构...")
    structure_prompt = f"""请根据以下「ChatGPT 对话原始语料」规划一份深度报告的文档结构。

要求：
1. 严格 5~7 章，每章标题明确、范围清晰；
2. 按原始对话的论述逻辑划分，覆盖全部核心主题（积分体系、双币模型、Temple Bond/Seat、功德券、用户分层、典型案例、治理与合规等）；
3. 输出**仅**一个 JSON 对象，格式如下（不要其他说明）：

{{
  "title": "报告总标题",
  "summary": "150字以内摘要",
  "keywords": ["关键词1", "关键词2", "关键词3", "关键词4", "关键词5"],
  "chapters": [
    {{"num": 1, "title": "第一章标题", "scope": "本章应覆盖的原始语料主题与关键词"}},
    {{"num": 2, "title": "第二章标题", "scope": "本章应覆盖的..."}},
    ...
  ]
}}

原始语料（节选）：
---
{content[:60000]}
---

请直接输出上述 JSON。"""

    structure_str = chat(
        [
            {"role": "system", "content": "你是专业的研究报告结构规划专家，输出严格为 JSON。"},
            {"role": "user", "content": structure_prompt},
        ],
        max_tokens=2048,
        temperature=0.3,
    )

    chapters_spec = _parse_structure(structure_str)
    if not chapters_spec:
        raise ValueError("无法解析文档结构，请检查 Kimi 返回。")

    # 解析元数据
    try:
        full_data = json.loads(re.sub(r"```\w*\n?|\n?```", "", structure_str.strip()))
        meta = {
            "title": full_data.get("title", "深度调查报告 3.0"),
            "summary": full_data.get("summary", ""),
            "keywords": full_data.get("keywords", []),
        }
    except (json.JSONDecodeError, TypeError):
        meta = {"title": "深度调查报告 3.0", "summary": "", "keywords": []}

    # --- 3.2 逐章生成内容
    chapter_contents = []
    total_chapters = len(chapters_spec)

    for i, ch in enumerate(chapters_spec):
        num = ch.get("num", i + 1)
        title = ch.get("title", f"第{i+1}章")
        scope = ch.get("scope", "")
        cn_num = _CHAPTER_CN[i] if i < len(_CHAPTER_CN) else str(num)
        print(f"[报告 3.0] Step 2/3: 生成第 {num} 章 / {total_chapters} ...")
        chapter_prompt = f"""请根据以下「ChatGPT 对话原始语料」，**仅**撰写报告中「{title}」这一章的内容。

【本章范围】
{scope}

【硬性要求】
1. **篇幅充足**：本章应充分展开，涵盖原始语料中与本章相关的全部论述逻辑、案例、表格、公式，不得压缩成寡淡要点；
2. **保留论述逻辑**：完整还原原始对话中的论证结构、递进关系、因果关系；
3. **保留关键内容**：表格、案例（如厦门朝宗宫、潮汕大佬、莆田本地人等）、分层设计、公式必须完整纳入；
4. **专业语言**：用严谨、简洁的专业语言重写，去除口语化，但保持论证的完整与说服力；
5. **忠于原文**：所有论点、案例、表格须来自原始语料，不得编造。

【编号格式】（必须严格执行）
- **章**：本章为「{cn_num}、{title}」，合并时会自动添加，你从二级节开始输出；
- **二级（节）**：用 ## {num}.1、## {num}.2、## {num}.3 形式；
- **三级（小节）**：用 ### （1）、### （2）、### （3） 或段落中的（1）（2）（3）列举；
- 可对比内容用 | 表格 | 呈现；
- 从 ## {num}.1 开始，不要输出「{cn_num}、」章标题。

【加粗要求】
对正文中**重要概念、定义、判定结论、关键数据**使用 **加粗** 标出，如：**Web2.8 体系**、**1 元=10 积分**、**双币模型**、**Temple Bond** 等。适度加粗，避免整段加粗。

原始语料：
---
{content}
---

请输出「{title}」的完整正文。"""

        chapter_text = chat(
            [
                {
                    "role": "system",
                    "content": "你是专业的研究报告撰写专家。核心原则：按给定章节范围，充分展开、保留论述逻辑、篇幅充足、不压缩信息。对重要概念、定义、判定、数据用 **加粗** 标出。输出严格为 Markdown。",
                },
                {"role": "user", "content": chapter_prompt},
            ],
            max_tokens=10240,
            temperature=0.4,
        )
        chapter_contents.append((num, title, chapter_text.strip()))

    # --- 3.3 合并输出
    print("[报告 3.0] Step 3/3: 合并报告并导出 Word...")
    report_title = meta.get("title", "深度调查报告 3.0")
    report_body = f"# {report_title}\n\n"
    if meta.get("summary"):
        report_body += f"> {meta['summary']}\n\n"
    if meta.get("keywords"):
        report_body += f"**关键词**：{', '.join(meta['keywords'])}\n\n---\n\n"

    for i, (num, title, text) in enumerate(chapter_contents):
        cn_num = _CHAPTER_CN[i] if i < len(_CHAPTER_CN) else str(num)
        chapter_head = f"# {cn_num}、{title}\n\n"
        report_body += chapter_head + text.strip() + "\n\n"

    report_v3_path = REPORT_DIR / f"{base}_report_v3.md"
    report_v3_path.write_text(report_body, encoding="utf-8")

    # 元数据
    meta_path = REPORT_DIR / f"{base}_meta_v3.json"
    meta["chapters"] = [{"num": n, "title": t} for n, t, _ in chapter_contents]
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    # Word 导出
    docx_path = REPORT_DIR / f"{base}_report_v3.docx"
    try:
        md_to_docx(report_body, docx_path)
        print(f"[报告 3.0] Word 已保存: {docx_path}")
    except Exception as e:
        alt_path = REPORT_DIR / f"{base}_report_v3_final.docx"
        md_to_docx(report_body, alt_path)
        print(f"[报告 3.0] Word 已保存（备用）: {alt_path}")
        docx_path = alt_path

    result = {
        "meta": meta,
        "report_v3_path": str(report_v3_path),
        "docx_path": str(docx_path),
        "report_v3_text": report_body,
    }
    print(f"[报告 3.0] Markdown 已保存: {report_v3_path}")
    return result


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="报告 3.0：按章节分段生成，篇幅充足")
    parser.add_argument("raw_file", type=Path, help="原始文本路径")
    parser.add_argument("-o", "--output-base", default=None, help="输出文件名前缀")
    args = parser.parse_args()
    raw = Path(args.raw_file)
    if not raw.is_absolute():
        raw = RAW_DIR / raw.name
    run_report_v3(raw, args.output_base)
