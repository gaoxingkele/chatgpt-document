# -*- coding: utf-8 -*-
"""
Step1: 使用 Pyppeteer 抓取 ChatGPT 分享链接的完整对话内容。
页面默认滚动到最新对话，需先回溯到开头，再逐条复制到本地；
若内容低于 1000 字节则等待 15 秒后重试。
"""
import asyncio
import re
import sys
from pathlib import Path

# 项目根目录
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config import RAW_DIR, MIN_CONTENT_BYTES, RETRY_WAIT_SECONDS, CRAWL_MAX_RETRIES


def _slug_from_url(url: str) -> str:
    """从分享链接提取简短标识用于文件名。"""
    m = re.search(r"share/([a-zA-Z0-9_-]+)", url)
    return m.group(1) if m else "chatgpt_share"


async def scroll_to_top_and_collect(page):
    """将分享页滚动到最顶部，并收集全部可见对话文本。"""
    await page.evaluate("""async () => {
        const el = document.documentElement || document.body;
        let lastScroll = -1;
        let sameCount = 0;
        while (sameCount < 3) {
            el.scrollTop = 0;
            await new Promise(r => setTimeout(r, 300));
            const now = el.scrollTop;
            if (now === lastScroll) sameCount++; else sameCount = 0;
            lastScroll = now;
        }
    }""")
    await asyncio.sleep(1.0)

    # 尝试多种常见选择器以兼容不同时期的 ChatGPT 分享页
    selectors = [
        "[data-message-author-role]",
        "[class*='message']",
        "article",
        "main [class*='markdown']",
        ".prose",
        "[class*='Conversation'] div",
    ]

    all_text_parts = []
    for sel in selectors:
        try:
            elements = await page.querySelectorAll(sel)
            for el in elements:
                text = await page.evaluate("(e) => e.innerText || e.textContent || ''", el)
                if text and len(text.strip()) > 2:
                    all_text_parts.append(text.strip())
        except Exception:
            continue

    # 若上述选择器未取到足够内容，回退：取整页主要文本
    if not all_text_parts:
        body_text = await page.evaluate("""() => {
            const main = document.querySelector('main') || document.body;
            return main ? main.innerText || main.textContent || '' : '';
        }""")
        if body_text and body_text.strip():
            all_text_parts = [body_text.strip()]

    # 去重并保持顺序（简单按出现顺序合并）
    seen = set()
    ordered = []
    for t in all_text_parts:
        if t not in seen:
            seen.add(t)
            ordered.append(t)
    return "\n\n".join(ordered)


def _find_chrome_executable() -> str:
    """优先使用本机 Chrome，避免 Pyppeteer 自带的 Chromium 下载失效。"""
    import os
    candidates = [
        os.environ.get("PUPPETEER_EXECUTABLE_PATH"),
        os.environ.get("CHROME_PATH"),
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    ]
    for path in candidates:
        if path and Path(path).exists():
            return path
    return ""


async def crawl_share_url(share_url: str, output_path: Path) -> bool:
    """
    爬取单个分享链接，内容写入 output_path。
    若内容长度 < MIN_CONTENT_BYTES，等待 RETRY_WAIT_SECONDS 后重试，最多 CRAWL_MAX_RETRIES 次。
    返回是否成功获取到足够内容。
    """
    from pyppeteer import launch

    browser = None
    launch_options = {
        "headless": True,
        "args": ["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"],
    }
    chrome_path = _find_chrome_executable()
    if chrome_path:
        launch_options["executablePath"] = chrome_path
    try:
        browser = await launch(**launch_options)
        page = await browser.newPage()
        await page.setViewport({"width": 1280, "height": 800})
        await page.setUserAgent(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )

        for attempt in range(1, CRAWL_MAX_RETRIES + 1):
            await page.goto(share_url, waitUntil="networkidle2", timeout=60000)
            await asyncio.sleep(2.0)

            content = await scroll_to_top_and_collect(page)
            raw_bytes = content.encode("utf-8")
            size = len(raw_bytes)

            if size >= MIN_CONTENT_BYTES:
                output_path.write_bytes(raw_bytes)
                return True

            if attempt < CRAWL_MAX_RETRIES:
                await asyncio.sleep(RETRY_WAIT_SECONDS)

        # 最后一次仍不足也写入，便于排查
        output_path.write_bytes(raw_bytes)
        return False

    finally:
        if browser:
            await browser.close()


def run_crawl(share_url: str, output_name: str = None) -> Path:
    """
    同步入口：爬取 share_url，保存到 output/raw/{output_name}.txt。
    URL 由命令行参数传入，不从文件读取。若未指定 output_name，则从 URL 中解析。
    返回输出文件路径。
    """
    from src.ingest.sources import run_ingest, detect_source
    if detect_source(share_url) == "file":
        raise ValueError("crawl 命令仅支持 URL，请使用 import 或 fetch 处理文件。")
    return run_ingest(share_url, output_name)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="抓取 ChatGPT 分享链接内容")
    parser.add_argument("url", help="ChatGPT 分享链接，如 https://chatgpt.com/share/xxx")
    parser.add_argument("-o", "--output", default=None, help="输出文件名（不含扩展名）")
    args = parser.parse_args()
    run_crawl(args.url, args.output)
