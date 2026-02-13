# -*- coding: utf-8 -*-
"""
Step2: 根据本地已下载的 ChatGPT 内容，调用 Kimi API：
- 分类整理，生成标题、摘要、关键词
- 按 5~7 章生成「深度调查报告 1.0」，完整保留原始论述逻辑，去重、简练、严谨。
"""
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config import RAW_DIR, REPORT_DIR
from src.kimi_client import chat


SYSTEM_PROMPT = """你是一位专业的研究报告撰写专家，擅长将 ChatGPT 对话语料转化为高质量报告。

核心原则：
1. **保留论述逻辑**：完整还原原始对话中的论证结构、递进关系、因果关系，不得将丰富论述压缩成空洞要点；
2. **简练严谨**：用专业、简洁的语言重写，去除口语化表述，但保持论证的完整与说服力；
3. **去重不丢信息**：合并、归纳多处重复的观点，避免同一内容反复出现，但核心论证必须保留；
4. **忠于原文**：所有论点、案例、表格须来自原始语料，不得编造数据或虚构来源。

输出格式：严格按用户要求的 JSON 或 Markdown。"""


def _load_raw_content(raw_path: Path) -> str:
    text = raw_path.read_text(encoding="utf-8", errors="replace")
    # 若内容过长，可截断前 N 字符以适配上下文（Kimi 支持长上下文，此处仅做安全截断）
    max_chars = 120000
    if len(text) > max_chars:
        text = text[:max_chars] + "\n\n[内容已截断，仅保留前 {} 字供分析]".format(max_chars)
    return text


def run_meta_and_report_v1(raw_path: Path, output_basename: str = None) -> dict:
    """
    读取 raw_path 的原始文本，先让 Kimi 生成元数据（标题、摘要、关键词）和报告 1.0 的章节结构，
    再生成完整报告 1.0。结果写入 output/reports，并返回包含路径和元数据的 dict。
    """
    raw_path = Path(raw_path)
    if not raw_path.is_file():
        raise FileNotFoundError(f"原始文件不存在: {raw_path}")
    content = _load_raw_content(raw_path)
    base = output_basename or raw_path.stem

    # --- 2.1 元数据：标题、摘要、关键词
    meta_prompt = f"""请根据以下「ChatGPT 对话原始语料」完成分类整理，并**仅**输出一个 JSON 对象（不要其他说明），格式如下：
{{
  "title": "一个简洁专业的标题",
  "summary": "200字以内的内容摘要",
  "keywords": ["关键词1", "关键词2", "关键词3", "关键词4", "关键词5"]
}}

原始语料：
---
{content[:40000]}
---
请直接输出上述 JSON，不要 markdown 代码块包裹。"""

    meta_str = chat(
        [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": meta_prompt}],
        max_tokens=2048,
    )
    # 尝试解析 JSON（可能被 markdown 包裹）
    meta_str_clean = meta_str.strip()
    for start in ("```json", "```"):
        if meta_str_clean.startswith(start):
            meta_str_clean = meta_str_clean[len(start) :].strip()
        if meta_str_clean.endswith("```"):
            meta_str_clean = meta_str_clean[:-3].strip()
    try:
        meta = json.loads(meta_str_clean)
    except json.JSONDecodeError:
        meta = {"title": "未命名报告", "summary": meta_str[:500], "keywords": []}

    # --- 2.2 深度调查报告 1.0（5~7 章，保留论述逻辑）
    report_prompt = f"""基于以下「ChatGPT 对话原始语料」，撰写一份**深度调查报告 1.0**。

【硬性要求】
1. **章节数量**：严格 5~7 章，不得超过 7 章。按主题合并，避免碎片化。
2. **保留论述逻辑**：完整还原原始对话中的论证结构——如「先给结论→分级评价→优缺点→解决方案」的递进、各维度对比、案例与推演的因果关系。不得将丰富论述压缩成寡淡的要点罗列。
3. **保留关键内容**：表格、案例（如厦门朝宗宫、潮汕大佬、莆田本地人等）、公式、分层设计必须完整纳入。
4. **去重与简练**：合并多处重复的观点，用严谨、简练的专业语言重写，去除口语化与冗余表述。
5. **忠于原文**：所有论点、数据、案例须来自原始语料，不得编造。

【输出格式】
- 直接输出报告正文，使用 Markdown（一级标题 #，二级 ##，三级 ###）；
- 可横向/纵向对比的内容用 | 表格 | 呈现；
- 不要输出 JSON 或多余说明。

原始语料：
---
{content[:100000]}
---

请从第一章开始输出完整报告正文。"""

    report_v1_text = chat(
        [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": report_prompt},
        ],
        max_tokens=8192,
        temperature=0.5,
    )

    # 保存
    meta_path = REPORT_DIR / f"{base}_meta.json"
    report_v1_path = REPORT_DIR / f"{base}_report_v1.md"
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    report_v1_path.write_text(report_v1_text, encoding="utf-8")

    result = {
        "meta": meta,
        "meta_path": str(meta_path),
        "report_v1_path": str(report_v1_path),
        "report_v1_text": report_v1_text,
    }
    print(f"[Step2] 元数据已保存: {meta_path}")
    print(f"[Step2] 深度调查报告 1.0 已保存: {report_v1_path}")
    return result


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="根据原始语料生成标题/摘要/关键词与报告1.0")
    parser.add_argument("raw_file", type=Path, help="原始文本路径，如 output/raw/xxx.txt")
    parser.add_argument("-o", "--output-base", default=None, help="输出文件名前缀")
    args = parser.parse_args()
    run_meta_and_report_v1(args.raw_file, args.output_base)
