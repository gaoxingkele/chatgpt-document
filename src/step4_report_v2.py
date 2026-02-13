# -*- coding: utf-8 -*-
"""
Step4: 根据专家意见与原始语料，对报告 1.0 整改生成报告 2.0；
要求：保留 ChatGPT 论述逻辑、5~7 章、去重简练、专业严谨；输出 Markdown 与 Word。
"""
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config import REPORT_DIR, EXPERT_DIR, RAW_DIR
from src.kimi_client import chat
from docx import Document
from docx.shared import Pt
from docx.enum.text import WD_ALIGN_PARAGRAPH
import re


def _load_expert_combined(base: str) -> str:
    p = EXPERT_DIR / f"{base}_专家意见汇总.md"
    if not p.is_file():
        raise FileNotFoundError(f"专家意见汇总不存在: {p}，请先运行 Step3")
    return p.read_text(encoding="utf-8", errors="replace")


def _load_raw_content(raw_path: Path, max_chars: int = 50000) -> str:
    """加载原始语料（节选），用于补充 ChatGPT 论述逻辑。"""
    if not raw_path or not Path(raw_path).is_file():
        return ""
    text = Path(raw_path).read_text(encoding="utf-8", errors="replace")
    return text[:max_chars] + ("\n\n[已截断]" if len(text) > max_chars else "")


def run_report_v2_and_docx(
    report_v1_path: Path,
    expert_combined_path: Path = None,
    output_basename: str = None,
    raw_path: Path = None,
) -> dict:
    """
    根据报告 1.0、专家意见汇总与（可选）原始语料，生成报告 2.0 的 Markdown，再转为 Word。
    返回 report_v2_path（.md）与 docx_path（.docx）。
    """
    report_v1_path = Path(report_v1_path)
    if not report_v1_path.is_file():
        raise FileNotFoundError(f"报告 1.0 不存在: {report_v1_path}")
    report_v1_text = report_v1_path.read_text(encoding="utf-8", errors="replace")
    base = output_basename or report_v1_path.stem.replace("_report_v1", "")

    if expert_combined_path and Path(expert_combined_path).is_file():
        expert_text = Path(expert_combined_path).read_text(encoding="utf-8", errors="replace")
    else:
        expert_text = _load_expert_combined(base)

    raw_text = _load_raw_content(raw_path, 80000) if raw_path else ""
    raw_full_len = len(Path(raw_path).read_text(encoding="utf-8", errors="replace")) if raw_path and Path(raw_path).is_file() else len(raw_text)

    raw_section = ""
    if raw_text:
        raw_section = f"""

---
【ChatGPT 原始语料节选】供参考，用于补充报告 1.0 中可能遗漏的论述逻辑与案例，整改时务必优先保留其中的论证结构：
{raw_text}
"""

    raw_char_hint = f"原始语料约 {raw_full_len} 字，" if raw_text else ""
    prompt = f"""请根据以下材料，对《深度调查报告 1.0》进行**整改**，输出完整的「深度调查报告 2.0」正文。

【材料】
1）《深度调查报告 1.0》正文
2）《专家评审意见汇总》{raw_section}

【极其重要的篇幅要求】
- **总体字数不得比原始语料低太多**：{raw_char_hint}报告 2.0 正文字数应尽量接近原始篇幅，扣除重复表述后至少保留约 70% 以上。禁止过度压缩、提炼成寡淡要点。
- **尽量保持原始语料**：扣除重复外，尽可能保留论证、案例、表格、具体数据。
- **重写而非压缩**：采用重写使每章顺畅连贯，用专业语言去重、理顺逻辑，而非删减。

【其他硬性要求】
1. **章节数量**：严格 5~7 章，不得超过 7 章。
2. **保留论述逻辑**：完整保留论证结构、递进关系、案例与推演。
3. **吸收专家意见**：采纳可执行的改进，但不过度学术化。
4. **忠于原文**：论点、案例、表格须来自原始语料或报告 1.0，不得虚构。

【输出格式】直接输出完整报告正文，使用 Markdown（# ## ###），表格用 | 呈现。不要 JSON 或多余说明。

---
《深度调查报告 1.0》：
{report_v1_text[:80000]}

---
《专家评审意见汇总》：
{expert_text[:40000]}
"""

    report_v2_text = chat(
        [
            {
                "role": "system",
                "content": """你是专业的研究报告修订专家。核心原则：
1. **篇幅充足**：报告 2.0 字数不得比原始语料低太多，扣除重复后尽量保持 70% 以上篇幅，禁止过度压缩；
2. **保留论述逻辑**：不得丢失论证结构、递进关系与案例丰富度；
3. **重写而非压缩**：用专业语言重写、去重、理顺逻辑，使每章顺畅，而非删减精简；
4. **吸收专家意见**：采纳可执行的改进，但不过度学术化。输出严格为 Markdown。""",
            },
            {"role": "user", "content": prompt},
        ],
        max_tokens=32768,
        temperature=0.4,
    )

    report_v2_path = REPORT_DIR / f"{base}_report_v2.md"
    report_v2_path.write_text(report_v2_text, encoding="utf-8")
    print(f"[Step4] 深度报告 2.0 (Markdown) 已保存: {report_v2_path}")

    # 转为 Word：标题层级字号与粗体，正文段落与列表
    docx_path = REPORT_DIR / f"{base}_report_v2.docx"
    try:
        md_to_docx(report_v2_text, docx_path)
    except PermissionError:
        alt_path = REPORT_DIR / f"{base}_report_v2_new.docx"
        md_to_docx(report_v2_text, alt_path)
        docx_path = alt_path
        print(f"[提示] 原文件可能被占用，已保存为: {docx_path}")
    print(f"[Step4] 深度报告 2.0 (Word) 已保存: {docx_path}")

    return {
        "report_v2_path": str(report_v2_path),
        "docx_path": str(docx_path),
        "report_v2_text": report_v2_text,
    }


def _add_runs_with_bold(paragraph, text: str, font_size) -> None:
    """将文本中的 **xxx** 解析为加粗，其余为普通。"""
    parts = re.split(r"(\*\*[^*]+\*\*)", text)
    for part in parts:
        if part.startswith("**") and part.endswith("**"):
            r = paragraph.add_run(part[2:-2])
            r.bold = True
            r.font.size = font_size
            r.font.name = "宋体"
        elif part:
            r = paragraph.add_run(part)
            r.font.size = font_size
            r.font.name = "宋体"


def md_to_docx(md_text: str, docx_path: Path) -> None:
    """将 Markdown 转为 Word：标题层级字号/粗体，段落/列表/表格，正文内 **加粗**。"""
    doc = Document()
    doc.styles["Normal"].font.size = Pt(12)
    doc.styles["Normal"].font.name = "宋体"

    lines = md_text.replace("\r\n", "\n").split("\n")
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # 一级标题 # -> 18pt 加粗
        if stripped.startswith("# ") and not stripped.startswith("## "):
            p = doc.add_paragraph(stripped[2:].strip())
            p.style = "Heading 1"
            p.runs[0].bold = True
            p.runs[0].font.size = Pt(18)
            p.runs[0].font.name = "黑体"
            i += 1
            continue

        # 二级标题 ## -> 16pt 加粗
        if stripped.startswith("## ") and not stripped.startswith("### "):
            p = doc.add_paragraph(stripped[3:].strip())
            p.style = "Heading 2"
            p.runs[0].bold = True
            p.runs[0].font.size = Pt(16)
            p.runs[0].font.name = "黑体"
            i += 1
            continue

        # 三级标题 ### -> 14pt 加粗
        if stripped.startswith("### "):
            p = doc.add_paragraph(stripped[4:].strip())
            p.runs[0].bold = True
            p.runs[0].font.size = Pt(14)
            p.runs[0].font.name = "黑体"
            i += 1
            continue

        # Markdown 表格：| a | b |
        if stripped.startswith("|") and "|" in stripped[1:]:
            table_lines = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                table_lines.append(lines[i])
                i += 1
            _add_md_table(doc, table_lines)
            continue

        # 无序列表 - 或 *
        if stripped.startswith("- ") or stripped.startswith("* "):
            text = stripped[2:].strip()
            p = doc.add_paragraph(style="List Bullet")
            _add_runs_with_bold(p, text, Pt(12))
            i += 1
            continue

        # 有序列表 1. 2.
        if re.match(r"^\d+\.\s", stripped):
            text = re.sub(r"^\d+\.\s", "", stripped)
            p = doc.add_paragraph(style="List Number")
            _add_runs_with_bold(p, text, Pt(12))
            i += 1
            continue

        # 空行
        if not stripped:
            i += 1
            continue

        # 普通段落（支持 **加粗**）
        p = doc.add_paragraph()
        p.paragraph_format.first_line_indent = Pt(24)
        _add_runs_with_bold(p, stripped, Pt(12))
        i += 1

    doc.save(str(docx_path))


def _add_md_table(doc, table_lines: list) -> None:
    """解析 Markdown 表格行并写入 docx。"""
    if len(table_lines) < 2:
        return
    rows = []
    for ln in table_lines:
        cells = [c.strip() for c in ln.split("|") if c.strip()]
        if cells and not all(re.match(r"^[-:]+$", c) for c in cells):
            rows.append(cells)
    if not rows:
        return
    col_count = max(len(r) for r in rows)
    table = doc.add_table(rows=len(rows), cols=col_count)
    table.style = "Table Grid"
    for ri, row_cells in enumerate(rows):
        for ci, cell_text in enumerate(row_cells):
            if ci < col_count:
                cell = table.rows[ri].cells[ci]
                cell.text = cell_text
                for p in cell.paragraphs:
                    for r in p.runs:
                        r.font.size = Pt(10.5)
                if ri == 0:
                    for p in cell.paragraphs:
                        for r in p.runs:
                            r.bold = True
    doc.add_paragraph()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="根据专家意见生成报告2.0并导出Word")
    parser.add_argument("report_v1", type=Path, help="报告 1.0 路径")
    parser.add_argument("-e", "--expert-file", type=Path, default=None, help="专家意见汇总路径（可选）")
    parser.add_argument("-r", "--raw-file", type=Path, default=None, help="原始语料路径（可选，用于补充论述逻辑）")
    parser.add_argument("-o", "--output-base", default=None, help="输出文件名前缀")
    args = parser.parse_args()
    raw = Path(args.raw_file) if args.raw_file else None
    if raw and not raw.is_absolute():
        raw = RAW_DIR / raw.name
    run_report_v2_and_docx(args.report_v1, args.expert_file, args.output_base, raw)
