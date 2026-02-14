# -*- coding: utf-8 -*-
"""
Step2: 根据本地原始语料，调用远程 API 生成报告 1.0。

流程：1）API 分析整体语料 → 构建文档大纲（≤7 章，≤3 级目录）
     2）按大纲将原始语料装配到各章节
     3）每章开头加简要描述、结尾加简要总结（承上启下）
     4）检查原始语料中未进入报告的内容，补充到对应目录下
     5）对报告 1.0 进行重复内容去重
     6）输出 1.0 Markdown 与 Word，供专家评审。
"""
import json
import re
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _log(msg: str, api_call: str = ""):
    ts = time.strftime("%H:%M:%S", time.localtime())
    prefix = f"[{ts}] [API#{api_call}] " if api_call else f"[{ts}] "
    print(prefix + msg, flush=True)
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config import RAW_DIR, REPORT_DIR
from src.kimi_client import chat


SYSTEM_PROMPT = """你是一位专业的研究报告撰写专家，擅长分析语料、构建文档结构、组织内容。

核心原则：
1. **忠于原文**：所有内容须来自原始语料，不得编造。
2. **结构清晰**：大纲层级分明，章节名称由语料内容推理得出。
3. **逻辑连贯**：装配时保持原始论述逻辑，承上启下自然。

输出格式：严格按用户要求的 JSON 或 Markdown。"""


def _load_raw_content(raw_path: Path, max_chars: int = 130000) -> str:
    text = raw_path.read_text(encoding="utf-8", errors="replace")
    if len(text) > max_chars:
        text = text[:max_chars] + "\n\n[内容已截断，仅保留前 {} 字]".format(max_chars)
    return text


def _clean_json(text: str) -> str:
    for start in ("```json", "```"):
        if text.strip().startswith(start):
            text = text.strip()[len(start):].strip()
        if text.strip().endswith("```"):
            text = text.strip()[:-3].strip()
    return text.strip()


def _api_build_outline(content: str) -> dict:
    """调用 API 分析语料，构建文档大纲。≤7 章，最多三级目录。"""
    prompt = f"""请分析以下「原始对话语料」的整体内容，构建一份文档大纲。

【硬性要求】
1. **章节数量**：一般不超过 7 章。
2. **目录层级**：最多三级。一级用「一、二、三…」，二级用「1.1、1.2…」，三级用「（1）（2）（3）…」。
3. **名称推理**：根据语料内容，推理出各层级目录的名称，要准确概括该部分主题。
4. **结构合理**：按逻辑顺序组织，避免碎片化。

【输出格式】仅输出一个 JSON 对象，不要其他说明：
{{
  "title": "报告主标题",
  "summary": "200字以内摘要",
  "keywords": ["关键词1", "关键词2", "关键词3", "关键词4", "关键词5"],
  "outline": [
    {{
      "level1": "一、第一章标题",
      "level2": [
        {{"title": "1.1 第一节标题", "level3": ["（1）小标题", "（2）小标题"]}},
        {{"title": "1.2 第二节标题", "level3": []}}
      ]
    }},
    {{
      "level1": "二、第二章标题",
      "level2": [...]
    }}
  ]
}}

原始语料：
---
{content[:80000]}
---

直接输出 JSON，不要 markdown 代码块包裹。"""

    _log("调用 API：分析语料，构建文档大纲（标题/摘要/关键词/章节结构）...", "1")
    t0 = time.time()
    resp = chat(
        [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": prompt}],
        max_tokens=8192,
        temperature=0.3,
    )
    _log(f"API#1 完成，耗时 {time.time()-t0:.1f}s，响应约 {len(resp)} 字", "1")
    text = _clean_json(resp)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # 尝试修复常见问题：截断处补全、去除控制字符
    try:
        text_fix = text.replace("\r\n", " ").replace("\n", " ")
        if '"outline":' in text_fix and text_fix.rstrip() and not text_fix.rstrip().endswith("}"):
            idx = text_fix.rfind('"level1"')
            if idx > 0:
                text_fix = text_fix[:idx] + ']}'
        return json.loads(text_fix)
    except (json.JSONDecodeError, Exception):
        pass
    # 兜底：从响应中提取 title/summary/keywords，使用默认大纲
    meta = {"title": "深度调查报告", "summary": "", "keywords": [], "outline": []}
    if '"title"' in text:
        m = re.search(r'"title"\s*:\s*"([^"]*)"', text)
        if m:
            meta["title"] = m.group(1).strip() or meta["title"]
    if '"summary"' in text:
        m = re.search(r'"summary"\s*:\s*"([^"]*)"', text)
        if m:
            meta["summary"] = m.group(1).strip()
    if '"keywords"' in text:
        m = re.search(r'"keywords"\s*:\s*\[(.*?)\]', text, re.DOTALL)
        if m:
            kw = re.findall(r'"([^"]+)"', m.group(1))
            meta["keywords"] = kw[:5]
    if not meta["outline"]:
        meta["outline"] = [
            {"level1": "一、概述与背景", "level2": [{"title": "1.1 主要内容", "level3": []}]},
            {"level1": "二、核心分析", "level2": [{"title": "2.1 要点", "level3": []}]},
            {"level1": "三、案例与数据", "level2": [{"title": "3.1 案例", "level3": []}]},
            {"level1": "四、结论与建议", "level2": [{"title": "4.1 结论", "level3": []}]},
        ]
    return meta


def _api_assemble_section(
    raw_chunk: str,
    chapter_title: str,
    section_titles: list,
    batch_hint: str = "",
    step_desc: str = "",
) -> str:
    """将原始语料装配到指定章节/小节，输出 Markdown 正文。强调保留篇幅，不压缩。"""
    if step_desc:
        _log(step_desc)
    t0 = time.time()
    sections_desc = "\n".join(f"- {s}" for s in section_titles) if section_titles else "（按逻辑组织）"
    prompt = f"""请将以下「原始语料」中与当前部分相关的内容**装配**成报告正文。

【当前章节】{chapter_title}
【二级目录】
{sections_desc}

【篇幅与内容要求（必须遵守）】
1. **尽量保留原文表述与篇幅**：只做归类、去重与重组，**不要删减论证、案例、数据**。不要将多段内容提炼成一句或寡淡要点。
2. **仅使用原始语料中的原文**：摘取、归类、重组，不得编造或改写含义。表格、案例、具体数据须**完整保留**。
3. **按二级/三级目录组织**：将语料归入对应小节，保持逻辑顺序。同一观点多处出现时合并为一处表述，但保留论证展开。
4. 该部分输出应覆盖语料中与本部分相关内容的**绝大部分**，不要压缩。
5. 直接输出 Markdown 正文（##、###），不要 JSON 或多余说明。
{batch_hint}

【原始语料】
---
{raw_chunk}
---

请输出该部分的完整正文（保持充实篇幅）。"""

    resp = chat(
        [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": prompt}],
        max_tokens=16384,
        temperature=0.4,
    )
    if step_desc:
        _log(f"完成，耗时 {time.time()-t0:.1f}s，输出约 {len(resp)} 字")
    return resp


def _api_add_chapter_intro_summary(
    chapter_title: str,
    chapter_body: str,
    prev_chapter: str = "",
    next_chapter: str = "",
    step_desc: str = "",
) -> str:
    """为章节添加开头简要描述与结尾简要总结，形成承上启下。"""
    if step_desc:
        _log(step_desc)
    t0 = time.time()
    ctx = ""
    if prev_chapter:
        ctx += f"【上一章主题】{prev_chapter}\n"
    if next_chapter:
        ctx += f"【下一章主题】{next_chapter}\n"
    prompt = f"""请为以下章节内容添加「承上启下」的过渡文字。

{ctx}
【本章标题】{chapter_title}

【本章正文】
---
{chapter_body[:25000]}
---

【要求】
1. **章首**：在本章正文开头添加 2~4 句简要描述，概括本章核心内容，并自然承接上文（如有）。
2. **章末**：在本章正文结尾添加 2~4 句简要总结，提炼本章要点，并自然过渡到下一章（如有）。
3. 过渡文字要简洁、专业，不要重复正文内容。
4. 直接输出**完整章节**（含新增的章首描述 + 原文正文 + 章末总结），使用 Markdown 格式。不要单独输出描述和总结。"""

    resp = chat(
        [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": prompt}],
        max_tokens=16384,
        temperature=0.4,
    )
    if step_desc:
        _log(f"完成，耗时 {time.time()-t0:.1f}s")
    return resp


def _api_supplement_missing(raw_content: str, report_text: str, step_desc: str = "") -> str:
    """对比原始语料与报告 1.0，找出缺失内容并补充到对应章节。"""
    if step_desc:
        _log(step_desc)
    t0 = time.time()
    raw_chunk = raw_content[:70000]
    report_chunk = report_text[:90000]
    prompt = f"""请对比以下「原始语料」与「报告 1.0」，完成补充任务。

【任务】
1. 找出原始语料中**尚未出现在报告 1.0 中**的内容（论证、案例、数据、表格等）。
2. 将缺失内容按主题**补充到报告 1.0 的对应章节**下，保持原有目录结构不变。
3. 补充时保持原文表述，不编造。若某段内容可归入多个章节，放入最相关的一处。
4. 若未发现明显缺失，则输出报告原文（可做必要格式整理）。

【要求】
- 直接输出**完整的更新后报告**，须包含开头的 # 主标题、摘要、关键词及所有章节。
- 使用 Markdown（# ## ###），表格用 | 呈现。
- 不要输出「缺失清单」或分析说明，只输出报告全文。
- 保持章节顺序与结构不变，仅在相应位置插入补充内容。

---
【原始语料】
{raw_chunk}

---
【报告 1.0】
{report_chunk}

---
请输出补充后的完整报告。"""

    resp = chat(
        [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": prompt}],
        max_tokens=32768,
        temperature=0.3,
    )
    if step_desc:
        _log(f"完成，耗时 {time.time()-t0:.1f}s，补充后约 {len(resp)} 字")
    return resp


def _api_deduplicate(report_text: str, step_desc: str = "") -> str:
    """对报告进行重复内容去重。"""
    if step_desc:
        _log(step_desc)
    t0 = time.time()
    report_chunk = report_text[:100000]
    prompt = f"""请对以下「报告 1.0」进行**重复内容去重**。

【任务】
1. 识别报告中**重复表述**、**重复案例**、**重复数据**（同一观点、同一案例、同一表格或数据在文中多次出现）。
2. 合并重复内容：保留一处完整、表述最佳的版本，删除其余重复处。
3. 保持报告结构、章节顺序、论证逻辑不变。
4. 去重后语句应通顺，段落衔接自然。

【要求】
- 直接输出**去重后的完整报告**，须包含 # 主标题、摘要、关键词及所有章节。
- 使用 Markdown（# ## ###）。
- 不要输出去重说明或修改清单，只输出报告全文。
- 若未发现明显重复，保持原文输出或做少量润色。

---
【报告 1.0】
{report_chunk}

---
请输出去重后的完整报告。"""

    resp = chat(
        [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": prompt}],
        max_tokens=32768,
        temperature=0.3,
    )
    if step_desc:
        _log(f"完成，耗时 {time.time()-t0:.1f}s，去重后约 {len(resp)} 字")
    return resp


def _assemble_chapter(
    content: str,
    chapter_title: str,
    level2_list: list,
    chunk_size: int = 50000,
    api_start: int = 2,
) -> tuple[str, int]:
    """
    装配单章内容。若二级目录较多或语料较长，按二级目录或语料块分批次装配后合并。
    返回 (装配结果, 下次 API 编号)。
    """
    section_titles = [s.get("title", str(s)) for s in level2_list if s]
    raw_len = len(content)
    n = api_start

    if raw_len <= chunk_size and len(level2_list) <= 4:
        part = _api_assemble_section(
            content, chapter_title, section_titles,
            step_desc=f"API#{n} 装配章节「{chapter_title}」（整章一次）"
        )
        return part, n + 1

    parts = []
    overlap = chunk_size // 2
    if len(level2_list) > 4:
        for j, sec in enumerate(level2_list):
            sec_title = sec.get("title", str(sec))
            sub_titles = [sec_title]
            start = min(j * (chunk_size - overlap), max(0, raw_len - chunk_size))
            raw_chunk = content[start : start + chunk_size]
            if not raw_chunk.strip():
                raw_chunk = content[:chunk_size]
            batch_hint = f"【说明】当前仅装配二级目录「{sec_title}」。语料为全文第 {start} 字起的一段，请从该段中摘取与本小节相关的内容并尽量保留篇幅。"
            part = _api_assemble_section(
                raw_chunk, chapter_title, sub_titles, batch_hint,
                step_desc=f"API#{n} 装配「{chapter_title}」→ 小节 {j+1}/{len(level2_list)}「{sec_title}」（语料 {start}-{start+len(raw_chunk)} 字）"
            )
            n += 1
            if part.strip():
                parts.append(part)
    else:
        start = 0
        idx = 0
        while start < raw_len:
            raw_chunk = content[start : start + chunk_size]
            if not raw_chunk.strip():
                break
            idx += 1
            batch_hint = f"【说明】此为语料第 {idx} 段（约 {start}-{start+len(raw_chunk)} 字），请装配与本章相关的部分并尽量保留篇幅。"
            part = _api_assemble_section(
                raw_chunk, chapter_title, section_titles, batch_hint,
                step_desc=f"API#{n} 装配「{chapter_title}」→ 语料段 {idx}（{start}-{start+len(raw_chunk)} 字）"
            )
            n += 1
            if part.strip():
                parts.append(part)
            start += chunk_size

    return "\n\n".join(parts) if parts else "", n


def run_meta_and_report_v1(raw_path: Path, output_basename: str = None) -> dict:
    """
    读取原始语料 → 构建大纲 → 装配 → 章首章末 → 补充缺失 → 去重 → 输出 1.0。
    """
    raw_path = Path(raw_path)
    if not raw_path.is_file():
        raise FileNotFoundError(f"原始文件不存在: {raw_path}")
    content = _load_raw_content(raw_path)
    base = output_basename or raw_path.stem

    # --- 1. API 分析整体语料，构建大纲
    _log("=" * 60)
    _log("Step2 报告 1.0：开始")
    _log(f"原始语料: {raw_path.name}, 共 {len(content)} 字")
    _log("=" * 60)
    meta = _api_build_outline(content)
    outline = meta.get("outline", [])
    if not outline:
        outline = [{"level1": "一、概述", "level2": [{"title": "1.1 主要内容", "level3": []}]}]

    meta_path = REPORT_DIR / f"{base}_meta.json"
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    _log(f"大纲已保存: {meta_path.name}，共 {len(outline)} 章")

    # --- 2. 按大纲分章节装配原始语料（内容多时按二级目录分批次）
    chapter_bodies = []
    total_chapters = len(outline)
    api_num = 2

    _log(f"Step2 装配：共 {total_chapters} 章，原始语料 {len(content)} 字")
    for i, ch in enumerate(outline):
        level1 = ch.get("level1", f"第{i+1}章")
        level2_list = ch.get("level2", [])
        _log(f"--- 装配章节 {i+1}/{total_chapters}: {level1} ---")

        body, api_num = _assemble_chapter(content, level1, level2_list, api_start=api_num)
        chapter_bodies.append({"title": level1, "body": body})

    # --- 3. 为每章添加章首描述、章末总结（承上启下）
    _log("Step2 为各章节添加章首描述、章末总结（承上启下）...")
    final_chapters = []
    for i, cb in enumerate(chapter_bodies):
        prev_title = chapter_bodies[i - 1]["title"] if i > 0 else ""
        next_title = chapter_bodies[i + 1]["title"] if i < len(chapter_bodies) - 1 else ""
        enhanced = _api_add_chapter_intro_summary(
            cb["title"], cb["body"], prev_title, next_title,
            step_desc=f"API#{api_num} 章首章末「{cb['title']}」"
        )
        api_num += 1
        final_chapters.append(enhanced)

    # --- 4. 组装最终 1.0 文档
    report_lines = [
        f"# {meta.get('title', '深度调查报告')}",
        "",
        f"> {meta.get('summary', '')}",
        "",
        f"**关键词**：{', '.join(meta.get('keywords', []))}",
        "",
        "---",
        "",
    ]
    for i, ch_text in enumerate(final_chapters):
        if not ch_text.strip().startswith("#"):
            ch_text = f"## {chapter_bodies[i]['title']}\n\n{ch_text}"
        report_lines.append(ch_text.strip())
        report_lines.append("")
        report_lines.append("")

    report_v1_text = "\n".join(report_lines)
    _log(f"Step2 初稿完成：约 {len(report_v1_text)} 字")

    # --- 5. 检查原始语料缺失并补充
    _log("Step2 检查原始语料缺失并补充到对应目录...")
    report_v1_text = _api_supplement_missing(
        content, report_v1_text,
        step_desc=f"API#{api_num} 对比原始语料与报告 1.0，补充缺失内容"
    )
    api_num += 1

    # --- 6. 重复内容去重
    _log("Step2 对报告 1.0 进行重复内容去重...")
    report_v1_text = _api_deduplicate(
        report_v1_text,
        step_desc=f"API#{api_num} 去重：合并重复表述、案例、数据"
    )

    report_v1_path = REPORT_DIR / f"{base}_report_v1.md"
    report_v1_path.write_text(report_v1_text, encoding="utf-8")
    _log(f"Step2 报告 1.0 定稿：约 {len(report_v1_text)} 字，已保存 {report_v1_path.name}")

    from src.step4_report_v2 import md_to_docx
    _log("Step2 导出 Word：报告 1.0 → .docx（格式同 2.0）")
    docx_path = REPORT_DIR / f"{base}_report_v1.docx"
    try:
        md_to_docx(report_v1_text, docx_path)
    except PermissionError:
        docx_path = REPORT_DIR / f"{base}_report_v1_new.docx"
        md_to_docx(report_v1_text, docx_path)
        _log(f"[提示] 原文件可能被占用，已保存为: {docx_path.name}")
    _log(f"Step2 报告 1.0 (Word) 已保存: {docx_path}")

    result = {
        "meta": meta,
        "meta_path": str(meta_path),
        "report_v1_path": str(report_v1_path),
        "report_v1_docx_path": str(docx_path),
        "report_v1_text": report_v1_text,
    }
    return result


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="根据原始语料生成大纲、装配内容、输出报告1.0")
    parser.add_argument("raw_file", type=Path, help="原始文本路径，如 output/raw/xxx.txt")
    parser.add_argument("-o", "--output-base", default=None, help="输出文件名前缀")
    args = parser.parse_args()
    run_meta_and_report_v1(args.raw_file, args.output_base)
