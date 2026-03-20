# -*- coding: utf-8 -*-
"""
Step2: 根据本地原始语料，调用远程 API 生成报告 1.0。

流程：1）API 分析整体语料 → 构建文档大纲（≤7 章，≤3 级目录）
     2）按大纲将原始语料装配到各章节 【并行：各章节同时装配】
     3）每章开头加简要描述、结尾加简要总结（承上启下）【并行】
     4）检查原始语料中未进入报告的内容，补充到对应目录下
     5）对报告 1.0 进行重复内容去重
     6）输出 1.0 Markdown 与 Word，供专家评审。
"""
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import src  # noqa: F401  — 确保 PROJECT_ROOT 加入 sys.path

from config import (
    REPORT_DIR,
    OUTLINE_RAW_LIMIT, OUTLINE_REVIEW_RAW_LIMIT, CHAPTER_INTRO_BODY_LIMIT,
    SUPPLEMENT_RAW_LIMIT,
    ASSEMBLE_CHUNK_SIZE,
)
from src.llm_client import chat
from src.utils.log import log as _log
from src.utils.file_utils import load_raw_content as _load_raw_content, clean_json as _clean_json


from src.prompts import REPORT_WRITER_PROMPT as SYSTEM_PROMPT

# 并行工作线程数（章节装配 / 专家评审）
MAX_WORKERS = 4


def _merge_duplicate_chapters(report_text: str) -> str:
    """合并补充/去重后产生的同名 ## 章节。"""
    from src.utils.markdown_utils import parse_report_chapters

    header, chapters = parse_report_chapters(report_text)
    if len(chapters) <= 1:
        return report_text

    # 提取顶层标题关键字（去掉序号）
    def _norm(title: str) -> str:
        t = title.strip().lstrip("#").strip()
        t = re.sub(r"^[一二三四五六七八九十]+[、．,]\s*", "", t)
        t = re.sub(r"^\d+[.、]\s*", "", t)
        return t.strip()

    merged_parts = []
    i = 0
    while i < len(chapters):
        current_key = _norm(chapters[i][0])
        title = chapters[i][0]
        body = chapters[i][1]
        j = i + 1
        while j < len(chapters) and _norm(chapters[j][0]) == current_key:
            body += "\n\n" + chapters[j][1]
            j += 1
        # 始终用 ## + 原始标题（去掉可能已有的 ## 前缀）
        clean_title = title.lstrip("#").strip()
        merged_parts.append(f"## {clean_title}\n\n{body}")
        i = j

    before = len(chapters)
    after = len(merged_parts)
    if before != after:
        _log(f"  同名章节合并: {before} → {after}")

    return f"{header}\n\n" + "\n\n".join(merged_parts)


def _api_build_outline(content: str, template_constraints: str = "") -> dict:
    """调用 API 分析语料，构建文档大纲。≤7 章，最多三级目录。"""
    prompt = """请分析以下「原始对话语料」的整体内容，构建一份文档大纲。

【硬性要求】
1. **章节数量**：一般不超过 7 章。
2. **目录层级**：最多三级。一级用「一、二、三…」，二级用「1.1、1.2…」，三级用「（1）（2）（3）…」。
3. **名称推理**：根据语料内容，推理出各层级目录的名称，要准确概括该部分主题。
4. **结构合理**：按逻辑顺序组织，避免碎片化。
5. **篇幅密度**：为每章标注 "density"（1-5），表示该章在原始语料中的内容丰富度：1=概述性/简短，5=数据密集/案例丰富。

【输出格式】仅输出一个 JSON 对象，不要其他说明：
{
  "title": "报告主标题",
  "summary": "200字以内摘要",
  "keywords": ["关键词1", "关键词2", "关键词3", "关键词4", "关键词5"],
  "outline": [
    {
      "level1": "一、第一章标题",
      "density": 3,
      "level2": [
        {"title": "1.1 第一节标题", "level3": ["（1）小标题", "（2）小标题"]},
        {"title": "1.2 第二节标题", "level3": []}
      ]
    },
    {
      "level1": "二、第二章标题",
      "density": 4,
      "level2": [...]
    }
  ]
}

"""
    if template_constraints:
        prompt += f"""
【报告模板约束（须遵守）】
{template_constraints}
"""
    prompt += f"""
原始语料：
---
{content[:OUTLINE_RAW_LIMIT]}
---

直接输出 JSON，不要 markdown 代码块包裹。"""

    _log("调用 API：分析语料，构建文档大纲（标题/摘要/关键词/章节结构）...", "1")
    t0 = time.time()
    resp = chat(
        [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": prompt}],
        max_tokens=8192,
        temperature=0.3,
        reasoning=True,
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


def _api_review_outline(outline_json: dict, content: str) -> dict:
    """重新审阅大纲，检查覆盖度、独立性、逻辑递进、均衡性，返回修正后的大纲 JSON。"""
    outline_str = json.dumps(outline_json, ensure_ascii=False, indent=2)
    prompt = f"""请审阅以下文档大纲 JSON，结合原始语料，从四个维度进行优化：

1. **覆盖度**：大纲是否涵盖了语料中的所有核心主题？有无遗漏的重要话题？
2. **独立性**：各章节之间是否存在内容重叠？是否需要合并或拆分？
3. **逻辑递进**：章节顺序是否合理？是否遵循由浅入深、从背景到结论的逻辑？
4. **均衡性**：各章节的二级目录数量是否均衡？是否有章节过于庞杂或过于单薄？
5. **篇幅密度**：每章的 density 值（1-5）是否合理反映了该章在语料中的内容丰富度？必要时调整。

【当前大纲 JSON】
{outline_str}

【原始语料】
---
{content[:OUTLINE_REVIEW_RAW_LIMIT]}
---

【输出要求】
- 直接输出**修正后的完整大纲 JSON**，格式与输入相同（含 title、summary、keywords、outline）
- 若大纲已经合理，可仅做微调或原样返回
- 不要输出分析说明，只输出 JSON
- 不要 markdown 代码块包裹"""

    _log("调用 API：审阅并优化大纲...", "1b")
    t0 = time.time()
    resp = chat(
        [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": prompt}],
        max_tokens=8192,
        temperature=0.3,
        reasoning=True,
    )
    _log(f"API#1b 大纲审阅完成，耗时 {time.time()-t0:.1f}s", "1b")
    text = _clean_json(resp)
    try:
        reviewed = json.loads(text)
        # 确保关键字段存在
        if "outline" in reviewed and isinstance(reviewed["outline"], list):
            # 保留原始 title/summary/keywords 如果审阅版缺失
            for key in ("title", "summary", "keywords"):
                if key not in reviewed and key in outline_json:
                    reviewed[key] = outline_json[key]
            return reviewed
    except (json.JSONDecodeError, Exception):
        pass
    _log("[警告] 大纲审阅结果解析失败，保留原始大纲")
    return outline_json


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
1. **尽量保留原文表述与篇幅**：只做归类、去重与重组，**不要删减论证、案例、数据、公式**。不要将多段内容提炼成一句或寡淡要点。
2. **仅使用原始语料中的原文**：摘取、归类、重组，不得编造或改写含义。表格、案例、具体数据、数学公式（`$...$` 或 `$$...$$`）须**完整保留**。
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
{chapter_body[:CHAPTER_INTRO_BODY_LIMIT]}
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


def _api_supplement_chapter(
    chapter_title: str,
    chapter_body: str,
    raw_chunk: str,
    chapter_idx: int,
    total_chapters: int,
) -> str:
    """对比原始语料与单章内容，补充缺失内容。"""
    prompt = f"""请对比以下「原始语料片段」与「报告第 {chapter_idx}/{total_chapters} 章」，补充缺失内容。

【本章标题】{chapter_title}

【任务】
1. 找出原始语料中与本章相关、但**尚未出现在本章正文中**的内容（论证、案例、数据、表格、公式等）。
2. 将缺失内容**补充到本章对应小节**下，保持目录结构不变。
3. 补充时保持原文表述，不编造。
4. 若未发现明显缺失，输出原章节内容（可做必要格式整理）。

【要求】
- 直接输出本章**完整正文**（以 ## 标题开头），使用 Markdown。
- 不要输出缺失清单或分析说明。
- 篇幅只增不减，不要压缩已有内容。

---
【原始语料片段】
{raw_chunk[:SUPPLEMENT_RAW_LIMIT]}

---
【本章正文】
{chapter_body}

---
请输出补充后的本章完整正文。"""

    resp = chat(
        [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": prompt}],
        max_tokens=16384,
        temperature=0.3,
    )
    return resp.strip()


def _api_deduplicate_chapter(
    chapter_title: str,
    chapter_body: str,
    chapter_idx: int,
    total_chapters: int,
) -> str:
    """对单章进行重复内容去重。"""
    prompt = f"""请对以下报告第 {chapter_idx}/{total_chapters} 章进行**重复内容去重**。

【本章标题】{chapter_title}

【任务】
1. 识别本章中**重复表述**、**重复案例**、**重复数据**。数学公式（`$...$` / `$$...$$` / `\\(...\\)` / `\\[...\\]`）不视为重复，须保留。
2. 合并重复内容：保留表述最佳的版本，删除其余重复处。
3. 保持小节结构、论证逻辑不变。
4. 去重后语句通顺，段落衔接自然。

【要求】
- 直接输出本章**去重后的完整正文**（以 ## 标题开头），使用 Markdown。
- 不要输出去重说明，只输出本章正文。
- 若未发现明显重复，保持原文输出或做少量润色。

---
【本章正文】
{chapter_body}

---
请输出去重后的本章正文。"""

    resp = chat(
        [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": prompt}],
        max_tokens=16384,
        temperature=0.3,
    )
    return resp.strip()


def _api_supplement_missing(raw_content: str, report_text: str, step_desc: str = "") -> str:
    """分章并行：对比原始语料与各章，补充缺失内容后合并。"""
    from src.utils.markdown_utils import parse_report_chapters
    from src.utils.parallel import parallel_map

    if step_desc:
        _log(step_desc)
    t0 = time.time()

    header, chapters = parse_report_chapters(report_text)
    if not chapters:
        _log("[警告] 无法拆分章节，回退到单次补充")
        return report_text

    num_chapters = len(chapters)
    raw_len = len(raw_content)

    def _supplement_one(idx, chapter):
        ch_title, ch_body = chapter
        # 按章节比例分配语料片段
        start = idx * raw_len // num_chapters
        end = (idx + 1) * raw_len // num_chapters
        raw_chunk = raw_content[start:end]
        _log(f"[补充] 第 {idx+1}/{num_chapters} 章: {ch_title[:30]}...")
        result = _api_supplement_chapter(
            ch_title, ch_body, raw_chunk, idx + 1, num_chapters,
        )
        _log(f"[补充] 第 {idx+1} 章完成，{len(ch_body)}→{len(result)} 字")
        return result

    revised_parts = parallel_map(_supplement_one, chapters)
    report_text = f"{header}\n\n" + "\n\n".join(revised_parts)

    if step_desc:
        _log(f"完成，耗时 {time.time()-t0:.1f}s，补充后约 {len(report_text)} 字")
    return report_text


def _api_deduplicate(report_text: str, step_desc: str = "") -> str:
    """分章并行：逐章去重后合并。"""
    from src.utils.markdown_utils import parse_report_chapters
    from src.utils.parallel import parallel_map

    if step_desc:
        _log(step_desc)
    t0 = time.time()

    header, chapters = parse_report_chapters(report_text)
    if not chapters:
        _log("[警告] 无法拆分章节，回退到原文")
        return report_text

    num_chapters = len(chapters)

    def _dedup_one(idx, chapter):
        ch_title, ch_body = chapter
        _log(f"[去重] 第 {idx+1}/{num_chapters} 章: {ch_title[:30]}...")
        result = _api_deduplicate_chapter(
            ch_title, ch_body, idx + 1, num_chapters,
        )
        _log(f"[去重] 第 {idx+1} 章完成，{len(ch_body)}→{len(result)} 字")
        return result

    revised_parts = parallel_map(_dedup_one, chapters)
    report_text = f"{header}\n\n" + "\n\n".join(revised_parts)

    if step_desc:
        _log(f"完成，耗时 {time.time()-t0:.1f}s，去重后约 {len(report_text)} 字")
    return report_text


def _assemble_chapter(
    content: str,
    chapter_title: str,
    level2_list: list,
    chunk_size: int = ASSEMBLE_CHUNK_SIZE,
    chapter_idx: int = 0,
) -> str:
    """
    装配单章内容。若二级目录较多或语料较长，按二级目录或语料块分批次装配后合并。
    返回装配结果文本。
    """
    section_titles = [s.get("title", str(s)) for s in level2_list if s]
    raw_len = len(content)
    ch_tag = f"Ch{chapter_idx+1}"

    if raw_len <= chunk_size and len(level2_list) <= 4:
        part = _api_assemble_section(
            content, chapter_title, section_titles,
            step_desc=f"[{ch_tag}] 装配章节「{chapter_title}」（整章一次）"
        )
        return part

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
                step_desc=f"[{ch_tag}] 装配「{chapter_title}」→ 小节 {j+1}/{len(level2_list)}「{sec_title}」"
            )
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
                step_desc=f"[{ch_tag}] 装配「{chapter_title}」→ 语料段 {idx}（{start}-{start+len(raw_chunk)} 字）"
            )
            if part.strip():
                parts.append(part)
            start += chunk_size

    return "\n\n".join(parts) if parts else ""


def run_meta_and_report_v1(raw_path: Path, output_basename: str = None, report_type: str = None) -> dict:
    """
    读取原始语料 → 构建大纲 → 并行装配各章 → 并行添加章首章末 → 补充缺失 → 去重 → 输出 1.0。
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
    # 加载模板约束（如有）
    template_constraints = ""
    if report_type:
        try:
            from src.report_type_profiles import load_report_type_profile
            profile = load_report_type_profile(report_type)
            parts = []
            min_ch = profile.get("min_chapters", 3)
            max_ch = profile.get("max_chapters", 7)
            parts.append(f"- 章节数量：{min_ch}~{max_ch} 章")
            min_chars = profile.get("min_total_chars", 10000)
            parts.append(f"- 最低总字数目标：{min_chars} 字")
            # 从 sections 中提取大纲约束
            outline_constraint = profile.get("sections", {}).get("大纲约束", "")
            if outline_constraint:
                parts.append(f"- 大纲约束：\n{outline_constraint}")
            template_constraints = "\n".join(parts)
        except Exception:
            pass

    meta = _api_build_outline(content, template_constraints)
    meta = _api_review_outline(meta, content)
    outline = meta.get("outline", [])
    if not outline:
        outline = [{"level1": "一、概述", "level2": [{"title": "1.1 主要内容", "level3": []}]}]

    meta_path = REPORT_DIR / f"{base}_meta.json"
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    _log(f"大纲已保存: {meta_path.name}，共 {len(outline)} 章")

    # --- 2. 并行装配各章节
    total_chapters = len(outline)
    _log(f"Step2 并行装配：共 {total_chapters} 章，{MAX_WORKERS} 线程并发，原始语料 {len(content)} 字")
    t_assemble = time.time()

    chapter_bodies = [None] * total_chapters  # 按索引保持顺序

    def _do_assemble(i, ch):
        level1 = ch.get("level1", f"第{i+1}章")
        level2_list = ch.get("level2", [])
        _log(f"--- [并行] 开始装配章节 {i+1}/{total_chapters}: {level1} ---")
        body = _assemble_chapter(content, level1, level2_list, chapter_idx=i)
        return i, level1, body

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(_do_assemble, i, ch): i for i, ch in enumerate(outline)}
        for future in as_completed(futures):
            i, level1, body = future.result()
            chapter_bodies[i] = {"title": level1, "body": body}
            _log(f"--- [并行] 章节 {i+1}/{total_chapters}「{level1}」装配完成，约 {len(body)} 字 ---")

    _log(f"Step2 全部章节装配完成，耗时 {time.time()-t_assemble:.1f}s")

    # --- 3. 并行为每章添加章首描述、章末总结（承上启下）
    _log(f"Step2 并行添加章首章末（{MAX_WORKERS} 线程）...")
    t_intro = time.time()
    final_chapters = [None] * total_chapters

    def _do_intro_summary(i, cb):
        prev_title = chapter_bodies[i - 1]["title"] if i > 0 else ""
        next_title = chapter_bodies[i + 1]["title"] if i < len(chapter_bodies) - 1 else ""
        enhanced = _api_add_chapter_intro_summary(
            cb["title"], cb["body"], prev_title, next_title,
            step_desc=f"[Ch{i+1}] 章首章末「{cb['title']}」"
        )
        return i, enhanced

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(_do_intro_summary, i, cb): i for i, cb in enumerate(chapter_bodies)}
        for future in as_completed(futures):
            i, enhanced = future.result()
            final_chapters[i] = enhanced

    _log(f"Step2 章首章末全部完成，耗时 {time.time()-t_intro:.1f}s")

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
        step_desc="对比原始语料与报告 1.0，补充缺失内容"
    )

    # --- 6. 重复内容去重
    _log("Step2 对报告 1.0 进行重复内容去重...")
    report_v1_text = _api_deduplicate(
        report_v1_text,
        step_desc="去重：合并重复表述、案例、数据"
    )

    # --- 7. 合并同名章节（补充/去重可能产生重复 ## 标题）
    report_v1_text = _merge_duplicate_chapters(report_v1_text)

    report_v1_path = REPORT_DIR / f"{base}_report_v1.md"
    report_v1_path.write_text(report_v1_text, encoding="utf-8")
    _log(f"Step2 报告 1.0 定稿：约 {len(report_v1_text)} 字，已保存 {report_v1_path.name}")

    from src.utils.docx_utils import save_docx_safe
    _log("Step2 导出 Word：报告 1.0 → .docx（格式同 2.0）")
    docx_path = save_docx_safe(report_v1_text, REPORT_DIR / f"{base}_report_v1.docx")
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
