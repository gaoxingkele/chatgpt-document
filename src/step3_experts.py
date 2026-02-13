# -*- coding: utf-8 -*-
"""
Step3: 多次调用 Kimi API 生成 3 个评审专家 Agent，风格截然不同：
- 专家1：关注内容事实、论据细节与局部观点逻辑、专业领域常识。
- 专家2：关注整体文档架构完整性、重点观点递进、深度报告价值、观点与主题是否鲜明突出。
- 专家3：从可行性、合规性、安全性、合理性评估，并对文档内不同观点与事实做横向、纵向比较分析。
将三位专家的修改意见保存到专家意见文档。
"""
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config import REPORT_DIR, EXPERT_DIR
from src.kimi_client import chat


EXPERT_1_SYSTEM = """你是一位严谨的「事实与逻辑」评审专家。你的评审重点：
- 内容事实与论据的细节是否可靠、是否有据可查；
- 局部观点与论证逻辑是否自洽、是否合理；
- 表述是否符合该专业领域的常识与惯例。

约束：修改意见应具体、可执行，但**不要建议过度学术化或泛化**，应保留原文的论述逻辑与案例丰富度。请用分点、可直接执行的方式输出修改意见。"""

EXPERT_2_SYSTEM = """你是一位「结构与深度」评审专家。你的评审重点：
- 整体文档架构是否完整、层次是否清晰，**章节是否控制在 7 章以内**；
- 重点观点的递进顺序是否合理，论述逻辑是否连贯；
- 表达的观点和主题是否鲜明，能否让读者快速把握核心结论。

约束：**不要建议将丰富论述压缩成空洞要点**，应保留论证的完整性与说服力。请用分点方式写出修改意见，标注优先级（高/中/低）。"""

EXPERT_3_SYSTEM = """你是一位「可行性与合规」评审专家。你的评审重点：
- 内容在现实中的可行性、合规性、安全性、合理性；
- 对文档内出现的不同观点、事实进行必要的横向/纵向比较分析；
- 指出可能存在的风险、矛盾或需要补充证据的地方。

约束：修改意见应务实，**不要建议过度规范化或虚构数据**。请用分点方式写出修改意见，注明类别（可行性/合规性/安全性/比较分析等）。"""


def run_experts(report_v1_path: Path, output_basename: str = None) -> dict:
    """
    对报告 1.0 的 Markdown 内容分别调用三位专家，生成三份意见并合并保存。
    返回各专家意见路径及合并文档路径。
    """
    report_v1_path = Path(report_v1_path)
    if not report_v1_path.is_file():
        raise FileNotFoundError(f"报告 1.0 不存在: {report_v1_path}")
    report_text = report_v1_path.read_text(encoding="utf-8", errors="replace")
    base = output_basename or report_v1_path.stem.replace("_report_v1", "")

    user_template = """请对以下《深度调查报告 1.0》进行评审，仅输出**可直接执行的修改意见**（分点列出），不要复述报告内容。

要求：修改意见应有助于提升严谨性与可读性，但**不要建议过度学术化、泛化或编造数据**，应保留原文的论述逻辑与案例丰富度。

---
{}
"""
    content_preview = report_text[:60000] if len(report_text) > 60000 else report_text
    user_msg = user_template.format(content_preview)

    results = {}
    for name, system in [
        ("专家1_事实与逻辑", EXPERT_1_SYSTEM),
        ("专家2_结构与深度", EXPERT_2_SYSTEM),
        ("专家3_可行性与合规", EXPERT_3_SYSTEM),
    ]:
        opinion = chat(
            [
                {"role": "system", "content": system},
                {"role": "user", "content": user_msg},
            ],
            max_tokens=4096,
            temperature=0.4,
        )
        out_path = EXPERT_DIR / f"{base}_{name}.md"
        out_path.write_text(f"# {name} 评审意见\n\n{opinion}", encoding="utf-8")
        results[name] = {"path": str(out_path), "content": opinion}
        print(f"[Step3] {name} 已保存: {out_path}")

    # 合并为一份「专家意见汇总」
    combined = f"# 深度调查报告 1.0 — 专家评审意见汇总\n\n"
    for name, data in results.items():
        combined += f"## {name}\n\n{data['content']}\n\n---\n\n"
    combined_path = EXPERT_DIR / f"{base}_专家意见汇总.md"
    combined_path.write_text(combined, encoding="utf-8")
    results["_combined_path"] = str(combined_path)
    print(f"[Step3] 专家意见汇总已保存: {combined_path}")
    return results


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="对报告1.0生成三位专家评审意见")
    parser.add_argument("report_v1", type=Path, help="报告 1.0 路径，如 output/reports/xxx_report_v1.md")
    parser.add_argument("-o", "--output-base", default=None, help="输出文件名前缀")
    args = parser.parse_args()
    run_experts(args.report_v1, args.output_base)
