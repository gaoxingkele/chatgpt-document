# -*- coding: utf-8 -*-
"""
多轮对话报告流水线：在单次 Kimi 会话中保持原始语料记忆，依次生成元数据、报告 1.0、专家评审、报告 2.0。
重点：报告 2.0 总体字数不得比原始语料低太多，扣除重复后尽量保持原文，采用重写使每章顺畅。
"""
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config import REPORT_DIR, EXPERT_DIR
from src.kimi_client import chat, chat_append


SYSTEM_PROMPT = """你是一位专业的研究报告撰写专家。用户将提供一份「原始对话语料」，你必须**在整次对话中全程保持对该语料的记忆**，并基于该记忆完成后续所有任务。

核心原则：
1. **保留论述逻辑**：完整还原原始对话中的论证结构、递进关系、因果关系。
2. **忠于原文**：所有论点、案例、表格须来自原始语料，不得编造。
3. **重写而非压缩**：用专业语言重写、去重，但不过度精简，保持论证完整性与丰富度。"""


def _load_raw_content(raw_path: Path, max_chars: int = 130000) -> str:
    text = raw_path.read_text(encoding="utf-8", errors="replace")
    if len(text) > max_chars:
        text = text[:max_chars] + "\n\n[内容已截断，仅保留前 {} 字]".format(max_chars)
    return text


def run_pipeline(raw_path: Path, output_basename: str = None) -> dict:
    """
    多轮对话流水线：原始语料 → 元数据 → 报告 1.0 → 三位专家 → 报告 2.0（保持篇幅）。
    """
    raw_path = Path(raw_path)
    if not raw_path.is_file():
        raise FileNotFoundError(f"原始文件不存在: {raw_path}")
    content = _load_raw_content(raw_path)
    base = output_basename or raw_path.stem
    raw_char_count = len(content)

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"""以下为「原始对话语料」，请务必在后续所有回复中保持对它的记忆。

---
【原始语料】
{content}
---

请先完成第一项任务：根据上述语料，**仅**输出一个 JSON 对象（不要其他说明），格式如下：
{{
  "title": "简洁专业的标题",
  "summary": "200字以内的内容摘要",
  "keywords": ["关键词1", "关键词2", "关键词3", "关键词4", "关键词5"]
}}

直接输出 JSON，不要 markdown 代码块包裹。"""},
    ]

    # Round 1: 元数据（首轮已有 user 消息，直接调用）
    meta_str = chat(messages, max_tokens=2048, temperature=0.3)
    messages.append({"role": "assistant", "content": meta_str})
    meta_str_clean = meta_str.strip()
    for start in ("```json", "```"):
        if meta_str_clean.startswith(start):
            meta_str_clean = meta_str_clean[len(start):].strip()
        if meta_str_clean.endswith("```"):
            meta_str_clean = meta_str_clean[:-3].strip()
    try:
        meta = json.loads(meta_str_clean)
    except json.JSONDecodeError:
        meta = {"title": "未命名报告", "summary": meta_str[:500], "keywords": []}

    meta_path = REPORT_DIR / f"{base}_meta.json"
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[流水线] 元数据已保存: {meta_path}")

    # Round 2: 报告 1.0
    report_v1_prompt = """请基于你已记忆的原始语料，撰写「深度调查报告 1.0」。

【硬性要求】
1. 严格 5~7 章，不得超过 7 章。
2. 完整保留原始对话的论证结构、递进关系、案例与推演。
3. 表格、案例、分层设计必须完整纳入。
4. 合并重复观点，用严谨专业语言重写，但不要将丰富论述压缩成寡淡要点。

【输出格式】直接输出报告正文，使用 Markdown（# ## ###），表格用 | 呈现。不要 JSON 或多余说明。"""

    report_v1_text, messages = chat_append(
        messages, report_v1_prompt, max_tokens=16384, temperature=0.5
    )
    report_v1_path = REPORT_DIR / f"{base}_report_v1.md"
    report_v1_path.write_text(report_v1_text, encoding="utf-8")
    print(f"[流水线] 报告 1.0 已保存: {report_v1_path}")

    # Round 3–5: 三位专家
    expert_systems = [
        ("专家1_事实与逻辑", "关注内容事实、论据细节、局部逻辑、专业常识。修改意见应具体可执行，分点列出。"),
        ("专家2_结构与深度", "关注文档架构完整性、重点观点递进、章节是否控制在7章内。分点列出，标注优先级（高/中/低）。"),
        ("专家3_可行性与合规", "关注可行性、合规性、安全性、合理性；对文档内观点做横向纵向比较。分点列出，注明类别。"),
    ]

    expert_contents = []
    for name, focus in expert_systems:
        user_msg = f"""请以「{name}」身份，对你已阅读的《深度调查报告 1.0》进行评审。评审重点：{focus}

仅输出**可直接执行的修改意见**（分点列出），不要复述报告内容。不要建议过度学术化或编造数据。"""
        opinion, messages = chat_append(messages, user_msg, max_tokens=4096, temperature=0.4)
        out_path = EXPERT_DIR / f"{base}_{name}.md"
        out_path.write_text(f"# {name} 评审意见\n\n{opinion}", encoding="utf-8")
        expert_contents.append((name, opinion))
        print(f"[流水线] {name} 已保存: {out_path}")

    combined = "# 深度调查报告 1.0 — 专家评审意见汇总\n\n"
    for name, op in expert_contents:
        combined += f"## {name}\n\n{op}\n\n---\n\n"
    combined_path = EXPERT_DIR / f"{base}_专家意见汇总.md"
    combined_path.write_text(combined, encoding="utf-8")
    print(f"[流水线] 专家意见汇总已保存: {combined_path}")

    # Round 6: 报告 2.0（重点：保持篇幅、重写而非压缩）
    report_v2_prompt = f"""请根据你已记忆的**原始语料**、已生成的《报告 1.0》以及《专家评审意见汇总》，撰写「深度调查报告 2.0」。

【极其重要的篇幅要求】
1. **总体字数不得比原始语料低太多**：原始语料约 {raw_char_count} 字，报告 2.0 的正文字数应尽量接近，扣除重复表述后至少保留约 70% 以上的篇幅。禁止过度压缩、提炼成寡淡要点。
2. **尽量保持原始语料**：在扣除重复表述之外，尽可能保留原始语料中的论证、案例、表格、分层设计、具体数据。
3. **重写机制**：采用重写使每章顺畅连贯，用专业语言去重、理顺逻辑，而非删减压缩。每章应充实饱满，论证完整。

【其他要求】
1. 严格 5~7 章，不得超过 7 章。
2. 保留论述逻辑与递进关系，吸收专家意见中可执行的改进，但不过度学术化。
3. 论点、案例、表格须来自原始语料，不得虚构。
4. 直接输出完整报告正文，使用 Markdown（# ## ###），表格用 | 呈现。不要 JSON 或多余说明。"""

    report_v2_text, _ = chat_append(
        messages, report_v2_prompt, max_tokens=32768, temperature=0.4
    )

    report_v2_path = REPORT_DIR / f"{base}_report_v2.md"
    report_v2_path.write_text(report_v2_text, encoding="utf-8")
    print(f"[流水线] 报告 2.0 (Markdown) 已保存: {report_v2_path}")

    # 转为 Word
    from src.step4_report_v2 import md_to_docx
    docx_path = REPORT_DIR / f"{base}_report_v2.docx"
    try:
        md_to_docx(report_v2_text, docx_path)
    except PermissionError:
        alt_path = REPORT_DIR / f"{base}_report_v2_new.docx"
        md_to_docx(report_v2_text, alt_path)
        docx_path = alt_path
        print(f"[提示] 原文件可能被占用，已保存为: {docx_path}")
    print(f"[流水线] 报告 2.0 (Word) 已保存: {docx_path}")

    return {
        "meta": meta,
        "meta_path": str(meta_path),
        "report_v1_path": str(report_v1_path),
        "report_v2_path": str(report_v2_path),
        "docx_path": str(docx_path),
    }


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="多轮对话流水线：原始语料 → 报告1.0 → 专家 → 报告2.0（保持篇幅）")
    parser.add_argument("raw_file", type=Path, help="原始文本路径")
    parser.add_argument("-o", "--output-base", default=None, help="输出文件名前缀")
    args = parser.parse_args()
    run_pipeline(args.raw_file, args.output_base)
