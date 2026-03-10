# -*- coding: utf-8 -*-
"""断点续跑：记录 pipeline 各步骤完成状态，支持中断后恢复。"""
import hashlib
import json
import time
from pathlib import Path


def _compute_config_hash() -> str:
    """计算当前 LLM 配置的哈希值（provider + model + 关键限制参数）。"""
    import os
    provider = os.environ.get("LLM_PROVIDER", "kimi")
    model = os.environ.get("KIMI_MODEL", "")
    key_info = f"{provider}|{model}"
    return hashlib.md5(key_info.encode()).hexdigest()[:12]


def load_progress(base: str, output_dir: Path) -> dict:
    """加载断点续跑进度文件，返回进度字典。"""
    progress_path = Path(output_dir) / f"{base}_progress.json"
    if progress_path.is_file():
        try:
            return json.loads(progress_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, Exception):
            pass
    return {"base": base, "config_hash": "", "completed_steps": [], "timestamps": {}}


def save_progress(base: str, output_dir: Path, step: str, extra: dict = None):
    """记录某步骤已完成。"""
    progress = load_progress(base, output_dir)
    progress["config_hash"] = _compute_config_hash()
    if step not in progress["completed_steps"]:
        progress["completed_steps"].append(step)
    progress["timestamps"][step] = time.strftime("%Y-%m-%d %H:%M:%S")
    if extra:
        progress.setdefault("extra", {}).update(extra)

    progress_path = Path(output_dir) / f"{base}_progress.json"
    progress_path.write_text(json.dumps(progress, ensure_ascii=False, indent=2), encoding="utf-8")


def should_skip_step(progress: dict, step: str) -> bool:
    """判断是否跳过某步骤（已完成且配置哈希匹配）。"""
    if step not in progress.get("completed_steps", []):
        return False
    current_hash = _compute_config_hash()
    stored_hash = progress.get("config_hash", "")
    return current_hash == stored_hash
