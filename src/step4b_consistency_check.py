# -*- coding: utf-8 -*-
"""
Step4b: 全文一致性校验——检查跨章节重复、矛盾、缺失过渡、篇幅失衡。
单次 LLM 调用，输出结构化问题清单与改进建议。
"""
import json
import time
from pathlib import Path

import src  # noqa: F401

from config import REPORT_DIR, CONSISTENCY_REPORT_LIMIT, CONSISTENCY_RAW_LIMIT
from src.llm_client import chat
from src.utils.log import log as _log
from src.utils.file_utils import load_raw_content as _load_raw_content, clean_json as _clean_json


def _api_check_consistency(report_text: str, raw_summary: str) -> str:
    """单次 LLM 调用，检查全文一致性问题。返回 JSON 字符串。"""
    raw_section = ""
    if raw_summary:
        raw_section = f"""
【原始语料摘要】（供交叉比对）
---
{raw_summary}
---
"""
    prompt = f"""请对以下报告进行**全文一致性校验**，从四个维度检查问题：

1. **跨章节重复**：同一观点、数据、案例在不同章节中重复出现
2. **内容矛盾**：不同章节中对同一事实的描述不一致或相互矛盾
3. **缺失过渡**：章节之间缺乏逻辑衔接，话题跳跃突兀
4. **篇幅失衡**：各章节篇幅差异过大（某章过长或过短）

{raw_section}

【报告全文】
---
{report_text[:CONSISTENCY_REPORT_LIMIT]}
---

请输出一个 JSON 数组，每个元素为一个问题：
[
  {{
    "type": "重复|矛盾|缺失过渡|篇幅失衡",
    "severity": "高|中|低",
    "location": "涉及的章节名称或编号",
    "description": "问题描述",
    "suggestion": "具体修改建议"
  }}
]

若无明显问题，输出空数组 []。直接输出 JSON，不要 markdown 代码块。"""

    _log("调用 API：全文一致性校验...", "consistency")
    t0 = time.time()
    resp = chat(
        [
            {"role": "system", "content": "你是专业的文档质量审核专家，擅长发现跨章节的一致性问题。输出严格 JSON。"},
            {"role": "user", "content": prompt},
        ],
        max_tokens=8192,
        temperature=0.3,
        reasoning=True,
    )
    _log(f"一致性校验完成，耗时 {time.time()-t0:.1f}s", "consistency")
    return resp


def run_consistency_check(
    report_path: Path,
    raw_path: Path = None,
    output_basename: str = None,
) -> dict:
    """
    对报告进行全文一致性校验。

    参数:
        report_path: 报告文件路径（.md 或 .docx）
        raw_path: 原始语料路径（可选，用于交叉比对）
        output_basename: 输出文件名前缀

    返回:
        {"suggestions_path": str, "issues_count": int}
    """
    report_path = Path(report_path)
    if not report_path.is_file():
        raise FileNotFoundError(f"报告不存在: {report_path}")

    from src.utils.markdown_utils import read_report_text
    report_text = read_report_text(report_path)
    base = output_basename or report_path.stem.replace("_report_v3", "").replace("_report_v2", "").replace("_report_v1", "")

    raw_summary = _load_raw_content(raw_path, CONSISTENCY_RAW_LIMIT) if raw_path else ""

    _log("=" * 60)
    _log("Step4b 全文一致性校验：开始")
    _log(f"报告: {report_path.name}, 约 {len(report_text)} 字")
    _log("=" * 60)

    resp = _api_check_consistency(report_text, raw_summary)
    cleaned = _clean_json(resp)

    # 解析 JSON
    try:
        issues = json.loads(cleaned)
    except json.JSONDecodeError:
        _log("[警告] LLM 返回非标准 JSON，将原文保存为建议")
        issues = []

    issues_count = len(issues) if isinstance(issues, list) else 0

    # 保存 JSON
    json_path = REPORT_DIR / f"{base}_consistency_suggestions.json"
    json_path.write_text(
        json.dumps(issues, ensure_ascii=False, indent=2) if isinstance(issues, list) else cleaned,
        encoding="utf-8",
    )

    # 保存可读 Markdown
    md_lines = ["# 全文一致性校验报告\n", f"共发现 {issues_count} 个问题\n"]
    if isinstance(issues, list):
        for i, item in enumerate(issues, 1):
            md_lines.append(f"## 问题 {i}")
            md_lines.append(f"- **类型**: {item.get('type', '未知')}")
            md_lines.append(f"- **严重程度**: {item.get('severity', '未知')}")
            md_lines.append(f"- **位置**: {item.get('location', '未知')}")
            md_lines.append(f"- **描述**: {item.get('description', '')}")
            md_lines.append(f"- **建议**: {item.get('suggestion', '')}")
            md_lines.append("")
    else:
        md_lines.append(cleaned)

    md_path = REPORT_DIR / f"{base}_consistency_suggestions.md"
    md_path.write_text("\n".join(md_lines), encoding="utf-8")

    _log(f"一致性校验完成：发现 {issues_count} 个问题")
    _log(f"已保存: {md_path.name}, {json_path.name}")

    return {
        "suggestions_path": str(md_path),
        "issues_count": issues_count,
    }
