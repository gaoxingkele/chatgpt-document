# -*- coding: utf-8 -*-
"""输出质量评分：对报告进行多维度质量评估。"""
import json
import time
from pathlib import Path

import src  # noqa: F401

from config import REPORT_DIR
from src.llm_client import chat
from src.utils.log import log as _log
from src.utils.file_utils import load_raw_content as _load_raw_content, clean_json as _clean_json

QUALITY_EVAL_REPORT_LIMIT = 60_000
QUALITY_EVAL_RAW_LIMIT = 30_000


def evaluate_report_quality(
    report_text: str,
    raw_text: str = "",
    version_label: str = "v1",
    output_path: Path = None,
) -> dict:
    """
    单次 LLM 调用评估报告质量。

    返回:
        {"coverage": 0-100, "structure": 1-5, "language": 1-5,
         "density": 1-5, "overall": float, "commentary": str}
    """
    raw_section = ""
    if raw_text:
        raw_section = f"""
【原始语料】（用于评估覆盖度）
---
{raw_text[:QUALITY_EVAL_RAW_LIMIT]}
---
"""
    prompt = f"""请对以下报告（{version_label}）进行**质量评估**，从五个维度打分：

1. **覆盖度** (coverage, 0-100)：报告是否覆盖了原始语料中的核心主题和关键信息？100=完全覆盖
2. **结构性** (structure, 1-5)：章节组织是否清晰、层次分明、逻辑连贯？5=优秀
3. **语言质量** (language, 1-5)：表述是否专业、流畅、无语法错误？5=优秀
4. **信息密度** (density, 1-5)：是否有冗余、重复或空洞内容？5=密度适中无冗余
5. **综合评分** (overall, 0-10)：整体质量综合评价

{raw_section}

【报告全文】
---
{report_text[:QUALITY_EVAL_REPORT_LIMIT]}
---

请输出一个 JSON 对象：
{{
  "coverage": 85,
  "structure": 4,
  "language": 4,
  "density": 3,
  "overall": 7.5,
  "commentary": "简要评语（2-3句，指出主要优点和不足）"
}}

直接输出 JSON，不要 markdown 代码块。"""

    _log(f"调用 API：报告质量评估（{version_label}）...", "quality")
    t0 = time.time()
    resp = chat(
        [
            {"role": "system", "content": "你是专业的文档质量评审专家，擅长多维度评估报告质量。输出严格 JSON。"},
            {"role": "user", "content": prompt},
        ],
        max_tokens=2048,
        temperature=0.3,
    )
    _log(f"质量评估完成，耗时 {time.time()-t0:.1f}s", "quality")

    cleaned = _clean_json(resp)
    try:
        result = json.loads(cleaned)
    except json.JSONDecodeError:
        _log("[警告] 质量评估返回非标准 JSON")
        result = {"coverage": 0, "structure": 0, "language": 0, "density": 0, "overall": 0, "commentary": cleaned}

    # 保存结果
    if output_path:
        output_path = Path(output_path)
        output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        _log(f"质量评估结果已保存: {output_path.name}")

    return result
