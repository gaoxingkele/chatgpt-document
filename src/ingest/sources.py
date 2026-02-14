# -*- coding: utf-8 -*-
"""
多平台采集入口：根据 URL 或文件路径自动识别来源并分发到对应处理器。
"""
import re
import time
from pathlib import Path

from config import RAW_DIR, PROJECT_ROOT, MIN_CONTENT_BYTES


def _log(msg: str):
    ts = time.strftime("%H:%M:%S", time.localtime())
    print(f"[{ts}] {msg}", flush=True)

# URL 模式 → 平台标识
_URL_PATTERNS = [
    (r"chatgpt\.com/share", "chatgpt"),
    (r"g\.co/gemini|gemini\.google\.com", "gemini"),
    (r"perplexity\.ai|perplexity\.com", "perplexity"),
]


def _resolve_file_path(s: str) -> Path:
    """解析文件路径：支持绝对路径、相对 cwd、相对项目根。"""
    p = Path(s.strip())
    if p.is_absolute() and p.is_file():
        return p
    if p.is_file():
        return p.resolve()
    for base in [Path.cwd(), PROJECT_ROOT]:
        c = base / p
        if c.is_file():
            return c
    return base / p  # 返回期望路径，调用方检查 is_file()


def detect_source(input_str: str) -> str:
    """
    识别输入来源。
    返回: "chatgpt" | "gemini" | "perplexity" | "generic" | "file"
    """
    s = input_str.strip()
    # URL
    if s.startswith("http://") or s.startswith("https://"):
        for pattern, platform in _URL_PATTERNS:
            if re.search(pattern, s, re.I):
                return platform
        return "generic"
    # 文件路径：显式路径或带扩展名（如 Perplexity 下载的 .md）
    if s.endswith((".txt", ".json", ".md", ".html")):
        return "file"
    p = Path(s)
    if p.is_file():
        return "file"
    if ("\\" in s or "/" in s) and not s.startswith("http"):
        return "file"
    return "file"


def run_ingest(input_str: str, output_name: str = None) -> Path:
    """
    统一采集入口：支持 URL 或本地文件路径。
    抓取页面的 URL 仅由调用方通过参数传入，不从文件读取。
    将内容归一化后保存到 output/raw/{output_name}.txt，返回保存路径。
    """
    src = detect_source(input_str)
    path = Path(input_str.strip())
    _log("=" * 60)
    _log("采集阶段：开始")
    _log(f"输入: {input_str[:80]}{'...' if len(input_str) > 80 else ''}")
    _log(f"来源: {'本地文件' if src == 'file' else src}")

    if src == "file":
        from .file_importer import import_from_file
        path = _resolve_file_path(input_str)
        _log("读取本地文件中...")
        if not path.is_file():
            raise FileNotFoundError(f"文件不存在: {path}，请检查路径是否正确")
        content = import_from_file(path)
        name = output_name or path.stem
    else:
        from .crawlers import crawl_url
        _log("API/爬虫: 抓取 URL 中...")
        content = crawl_url(input_str, platform=src)
        name = output_name or _slug_from_input(input_str, src)

    out_path = RAW_DIR / f"{name}.txt"
    size = len(content.encode("utf-8"))
    out_path.write_text(content, encoding="utf-8")
    if src != "file" and size < MIN_CONTENT_BYTES:
        _log(f"[警告] 内容可能未完整（< {MIN_CONTENT_BYTES} 字节）")
    _log(f"采集完成: 已保存 {out_path.name}，{size} 字节（约 {len(content)} 字）")
    return out_path


def _slug_from_input(input_str: str, platform: str) -> str:
    """从 URL 或路径生成简短文件名。"""
    s = input_str.strip()
    # URL 中的 ID
    for pattern in [r"share/([a-zA-Z0-9_-]+)", r"([a-zA-Z0-9]{10,})"]:
        m = re.search(pattern, s)
        if m:
            return f"{platform}_{m.group(1)[:30]}"
    return f"{platform}_import"
