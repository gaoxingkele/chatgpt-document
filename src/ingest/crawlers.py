# -*- coding: utf-8 -*-
"""
多平台网页爬虫：首选 Pyppeteer（需 Chrome/Edge 或 pyppeteer-install），
备用 Playwright + Chromium（可运行 install-browser 单独安装）。
"""
import asyncio
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
import sys
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config import MIN_CONTENT_BYTES, RETRY_WAIT_SECONDS, CRAWL_MAX_RETRIES


_CHATGPT_SELECTORS = [
    "[data-message-author-role]",
    "[class*='message']",
    "article",
    "main [class*='markdown']",
    ".prose",
    "[class*='Conversation'] div",
]

_GENERIC_SELECTORS = [
    "article",
    "[role='article']",
    "main [class*='message']",
    "main [class*='conversation']",
    "[class*='message']",
    "[class*='chat']",
    "[class*='response']",
    ".prose",
    "main .markdown",
    "[class*='markdown']",
    "main",
]

_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"


def _find_chrome_executable() -> str:
    """Chrome / Edge 等 Chromium 内核浏览器路径，供 Pyppeteer 使用。"""
    candidates = [
        os.environ.get("PUPPETEER_EXECUTABLE_PATH"),
        os.environ.get("CHROME_PATH"),
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    ]
    for p in candidates:
        if p and Path(p).exists():
            return p
    return ""


async def _scroll_and_collect_playwright(page, selectors: list) -> str:
    """Playwright 版：滚动并收集内容。"""
    await page.evaluate("""async () => {
        const el = document.documentElement || document.body;
        let lastScroll = -1, sameCount = 0;
        while (sameCount < 3) {
            el.scrollTop = 0;
            await new Promise(r => setTimeout(r, 300));
            const now = el.scrollTop;
            if (now === lastScroll) sameCount++; else sameCount = 0;
            lastScroll = now;
        }
    }""")
    await asyncio.sleep(1.5)

    all_parts = []
    for sel in selectors:
        try:
            elements = await page.query_selector_all(sel)
            for el in elements:
                text = (await el.inner_text()) or (await el.text_content()) or ""
                if text and len(text.strip()) > 2:
                    all_parts.append(text.strip())
        except Exception:
            continue

    if not all_parts:
        body_text = await page.evaluate("""() => {
            const main = document.querySelector('main') || document.body;
            return main ? main.innerText || main.textContent || '' : '';
        }""")
        if body_text and body_text.strip():
            all_parts = [body_text.strip()]

    seen = set()
    ordered = [t for t in all_parts if t not in seen and not seen.add(t)]
    return "\n\n".join(ordered)


async def _scroll_and_collect_pyppeteer(page, selectors: list) -> str:
    """Pyppeteer 版：滚动并收集内容。"""
    await page.evaluate("""async () => {
        const el = document.documentElement || document.body;
        let lastScroll = -1, sameCount = 0;
        while (sameCount < 3) {
            el.scrollTop = 0;
            await new Promise(r => setTimeout(r, 300));
            const now = el.scrollTop;
            if (now === lastScroll) sameCount++; else sameCount = 0;
            lastScroll = now;
        }
    }""")
    await asyncio.sleep(1.5)

    all_parts = []
    for sel in selectors:
        try:
            elements = await page.querySelectorAll(sel)
            for el in elements:
                text = await page.evaluate("(e) => e.innerText || e.textContent || ''", el)
                if text and len(text.strip()) > 2:
                    all_parts.append(text.strip())
        except Exception:
            continue

    if not all_parts:
        body_text = await page.evaluate("""() => {
            const main = document.querySelector('main') || document.body;
            return main ? main.innerText || main.textContent || '' : '';
        }""")
        if body_text and body_text.strip():
            all_parts = [body_text.strip()]

    seen = set()
    ordered = [t for t in all_parts if t not in seen and not seen.add(t)]
    return "\n\n".join(ordered)


async def _crawl_playwright(url: str, selectors: list) -> str:
    """备用：使用 Playwright + Chromium（通过 install-browser 安装）。"""
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            page = await browser.new_page()
            await page.set_viewport_size({"width": 1280, "height": 800})
            await page.set_extra_http_headers({"User-Agent": _USER_AGENT})

            for attempt in range(1, CRAWL_MAX_RETRIES + 1):
                await page.goto(url, wait_until="networkidle", timeout=60000)
                await asyncio.sleep(2.5)

                content = await _scroll_and_collect_playwright(page, selectors)
                if len(content.encode("utf-8")) >= MIN_CONTENT_BYTES:
                    return content
                if attempt < CRAWL_MAX_RETRIES:
                    await asyncio.sleep(RETRY_WAIT_SECONDS)

            return content
        finally:
            await browser.close()


async def _crawl_pyppeteer(url: str, selectors: list) -> str:
    """首选：使用 Pyppeteer（需 Chrome/Edge 或 pyppeteer-install）。"""
    from pyppeteer import launch

    opts = {
        "headless": True,
        "args": ["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"],
    }
    chrome = _find_chrome_executable()
    if chrome:
        opts["executablePath"] = chrome

    browser = await launch(**opts)
    try:
        page = await browser.newPage()
        await page.setViewport({"width": 1280, "height": 800})
        await page.setUserAgent(_USER_AGENT)

        content = ""
        for attempt in range(1, CRAWL_MAX_RETRIES + 1):
            await page.goto(url, waitUntil="networkidle2", timeout=60000)
            await asyncio.sleep(2.5)

            content = await _scroll_and_collect_pyppeteer(page, selectors)
            if len(content.encode("utf-8")) >= MIN_CONTENT_BYTES:
                return content
            if attempt < CRAWL_MAX_RETRIES:
                await asyncio.sleep(RETRY_WAIT_SECONDS)

        return content
    finally:
        await browser.close()


def crawl_url(url: str, platform: str = "chatgpt") -> str:
    """
    同步入口：抓取 URL，返回归一化文本。
    首选 Pyppeteer（需 Chrome/Edge 或 pyppeteer-install），
    失败时回退到 Playwright（需运行 install-browser）。
    """
    selectors = _CHATGPT_SELECTORS if platform == "chatgpt" else _GENERIC_SELECTORS

    try:
        return asyncio.run(_crawl_pyppeteer(url, selectors))
    except ImportError:
        print("[提示] Pyppeteer 未安装，尝试使用 Playwright 备用...")
        return asyncio.run(_crawl_playwright(url, selectors))
    except Exception as e:
        err_str = str(e).lower()
        if "executable" in err_str or "browser" in err_str or "chrome" in err_str:
            print("[提示] 未找到 Chrome/Edge，尝试 Playwright Chromium...")
        try:
            return asyncio.run(_crawl_playwright(url, selectors))
        except Exception as e2:
            raise RuntimeError(
                f"爬虫失败。请安装浏览器：\n"
                f"  1. 首选: 安装 Chrome/Edge 或运行 pyppeteer-install\n"
                f"  2. 备用: python main.py install-browser（Playwright Chromium）\n"
                f"错误: {e2}"
            ) from e2
