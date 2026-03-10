# -*- coding: utf-8 -*-
"""语义漂移检测：比较报告不同版本间的核心论点变化。"""
import json
import time
from pathlib import Path

import src  # noqa: F401

from config import REPORT_DIR
from src.llm_client import chat
from src.utils.log import log as _log
from src.utils.file_utils import clean_json as _clean_json
from src.utils.markdown_utils import read_report_text as _read_report_text

DRIFT_REPORT_LIMIT = 50_000


def extract_core_claims(report_text: str, version_label: str = "v1") -> list[str]:
    """从报告中提取 5-10 条核心论点。"""
    prompt = f"""请从以下报告（{version_label}）中提取 **5-10 条核心论点/关键结论**。

要求：
1. 每条论点为一句完整的陈述，包含具体的观点或结论
2. 优先提取有数据支撑、有明确结论的论点
3. 覆盖报告的主要章节

【报告】
---
{report_text[:DRIFT_REPORT_LIMIT]}
---

输出 JSON 数组，每个元素为一条论点字符串：
["论点1", "论点2", ...]

直接输出 JSON，不要 markdown 代码块。"""

    _log(f"提取核心论点（{version_label}）...", "drift")
    t0 = time.time()
    resp = chat(
        [
            {"role": "system", "content": "你是专业的文档分析专家，擅长提取核心论点。输出严格 JSON。"},
            {"role": "user", "content": prompt},
        ],
        max_tokens=4096,
        temperature=0.3,
    )
    _log(f"论点提取完成（{version_label}），耗时 {time.time()-t0:.1f}s", "drift")
    cleaned = _clean_json(resp)
    try:
        claims = json.loads(cleaned)
        if isinstance(claims, list):
            return claims
    except json.JSONDecodeError:
        pass
    return []


def compare_claims(baseline: list[str], current: list[str]) -> dict:
    """比较基线版本与当前版本的核心论点变化。"""
    baseline_str = "\n".join(f"- {c}" for c in baseline)
    current_str = "\n".join(f"- {c}" for c in current)

    prompt = f"""请比较以下两个版本的核心论点，分析语义漂移情况。

【基线版本论点】
{baseline_str}

【当前版本论点】
{current_str}

请输出 JSON 对象：
{{
  "retained": ["保留的论点（基线中有且当前仍存在）"],
  "lost": ["丢失的论点（基线中有但当前不存在）"],
  "added": ["新增的论点（当前有但基线中没有）"],
  "modified": [
    {{"original": "原论点", "modified": "修改后的论点", "change": "变化说明"}}
  ],
  "drift_score": 0.0,
  "summary": "整体漂移情况总结（1-2句）"
}}

drift_score: 0.0=完全一致, 1.0=完全不同。直接输出 JSON。"""

    _log("比较核心论点变化...", "drift")
    t0 = time.time()
    resp = chat(
        [
            {"role": "system", "content": "你是专业的文档比较专家，擅长分析语义漂移。输出严格 JSON。"},
            {"role": "user", "content": prompt},
        ],
        max_tokens=4096,
        temperature=0.3,
    )
    _log(f"论点比较完成，耗时 {time.time()-t0:.1f}s", "drift")
    cleaned = _clean_json(resp)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        return {"retained": [], "lost": [], "added": [], "modified": [], "drift_score": -1, "summary": cleaned}


def run_drift_check(
    baseline_path: Path,
    current_path: Path,
    output_basename: str = None,
) -> dict:
    """
    对比两个版本的报告，检测语义漂移。

    返回: {"drift_score": float, "result_path": str, ...}
    """
    baseline_path = Path(baseline_path)
    current_path = Path(current_path)
    if not baseline_path.is_file():
        raise FileNotFoundError(f"基线报告不存在: {baseline_path}")
    if not current_path.is_file():
        raise FileNotFoundError(f"当前报告不存在: {current_path}")

    base = output_basename or current_path.stem
    baseline_text = _read_report_text(baseline_path)
    current_text = _read_report_text(current_path)

    _log("=" * 60)
    _log("语义漂移检测：开始")
    _log(f"基线: {baseline_path.name} | 当前: {current_path.name}")
    _log("=" * 60)

    baseline_claims = extract_core_claims(baseline_text, "基线版")
    current_claims = extract_core_claims(current_text, "当前版")

    if not baseline_claims or not current_claims:
        _log("[警告] 论点提取失败，无法进行漂移检测")
        return {"drift_score": -1, "error": "论点提取失败"}

    result = compare_claims(baseline_claims, current_claims)
    result["baseline_claims"] = baseline_claims
    result["current_claims"] = current_claims

    # 保存结果
    result_path = REPORT_DIR / f"{base}_drift_check.json"
    result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    drift_score = result.get("drift_score", -1)
    _log(f"语义漂移检测完成：drift_score={drift_score}")
    _log(f"  保留: {len(result.get('retained', []))} | 丢失: {len(result.get('lost', []))} | 新增: {len(result.get('added', []))}")
    _log(f"  结果已保存: {result_path.name}")

    result["result_path"] = str(result_path)
    return result
