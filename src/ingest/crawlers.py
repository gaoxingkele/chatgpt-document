# -*- coding: utf-8 -*-
"""
多平台网页爬虫：首选 Pyppeteer（需 Chrome/Edge 或 pyppeteer-install），
备用 Playwright + Chromium（可运行 install-browser 单独安装）。
支持提取图片（<img>）和公式（KaTeX/MathJax）。
"""
import asyncio
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List
from urllib.parse import urljoin, urlparse

import src  # noqa: F401  — 确保 PROJECT_ROOT 加入 sys.path

from config import MIN_CONTENT_BYTES, RETRY_WAIT_SECONDS, CRAWL_MAX_RETRIES


@dataclass
class CrawlResult:
    """爬取结果：文本 + 图片列表 + 公式计数。"""
    text: str = ""
    images: List[dict] = field(default_factory=list)
    formula_count: int = 0


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

# DOM 遍历 JS：提取文本节点、图片和公式，保持顺序
_DOM_WALKER_JS = """
(elements) => {
    const results = [];
    for (const el of elements) {
        const parts = [];
        const walk = (node) => {
            if (node.nodeType === 3) {
                const t = node.textContent.trim();
                if (t) parts.push({type: 'text', value: t});
                return;
            }
            if (node.nodeType !== 1) return;

            // KaTeX 公式
            if (node.classList && (node.classList.contains('katex') || node.classList.contains('katex-display'))) {
                const ann = node.querySelector('annotation[encoding="application/x-tex"]');
                if (ann && ann.textContent.trim()) {
                    const isDisplay = node.classList.contains('katex-display')
                        || (node.parentElement && node.parentElement.classList.contains('katex-display'));
                    parts.push({type: 'formula', latex: ann.textContent.trim(), display: isDisplay});
                    return;
                }
            }

            // MathJax 公式
            if (node.classList && (node.classList.contains('MathJax') || node.classList.contains('MathJax_Display'))) {
                const script = node.parentElement
                    ? node.parentElement.querySelector('script[type="math/tex"]')
                    : null;
                if (script && script.textContent.trim()) {
                    const isDisplay = node.classList.contains('MathJax_Display')
                        || (script.type && script.type.includes('display'));
                    parts.push({type: 'formula', latex: script.textContent.trim(), display: isDisplay});
                    return;
                }
            }

            // MathJax v3 (mjx-container)
            if (node.tagName && node.tagName.toLowerCase() === 'mjx-container') {
                const ann = node.querySelector('annotation[encoding="application/x-tex"]');
                if (ann && ann.textContent.trim()) {
                    const isDisplay = node.hasAttribute('display')
                        || (node.getAttribute('display') === 'true');
                    parts.push({type: 'formula', latex: ann.textContent.trim(), display: isDisplay});
                    return;
                }
            }

            // 图片
            if (node.nodeName === 'IMG') {
                const src = node.src || node.getAttribute('data-src') || '';
                const alt = node.alt || '';
                if (src && !src.startsWith('data:image/svg'))
                    parts.push({type: 'image', src: src, alt: alt});
                return;
            }

            for (const child of node.childNodes) walk(child);
        };
        walk(el);
        results.push(parts);
    }
    return results;
}
"""

# 不含公式的纯图片 DOM 遍历（后备）
_DOM_WALKER_SIMPLE_JS = """
(elements) => {
    const results = [];
    for (const el of elements) {
        const parts = [];
        const walk = (node) => {
            if (node.nodeType === 3) {
                const t = node.textContent.trim();
                if (t) parts.push({type: 'text', value: t});
                return;
            }
            if (node.nodeType !== 1) return;
            if (node.nodeName === 'IMG') {
                const src = node.src || node.getAttribute('data-src') || '';
                const alt = node.alt || '';
                if (src && !src.startsWith('data:image/svg'))
                    parts.push({type: 'image', src: src, alt: alt});
                return;
            }
            for (const child of node.childNodes) walk(child);
        };
        walk(el);
        results.push(parts);
    }
    return results;
}
"""


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


def _ext_from_url(url: str) -> str:
    """从 URL 路径推断图片扩展名。"""
    path = urlparse(url).path.lower()
    for ext in (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".svg"):
        if path.endswith(ext):
            return ext
    return ".png"


def _process_dom_parts(all_element_parts: list, base_url: str = "") -> CrawlResult:
    """
    将 DOM walker 返回的 parts 列表处理为 CrawlResult。
    图片 URL 会解析为绝对地址；文本中插入 Markdown 图片/公式占位符。
    如果 DOM 未检测到公式（KaTeX/MathJax），则由 crawl_url() 统一做 Unicode 数学字符检测。
    """
    img_counter = 0
    formula_count = 0
    images = []
    text_segments = []
    seen_texts = set()

    for element_parts in all_element_parts:
        seg_parts = []
        for p in element_parts:
            if p["type"] == "text":
                seg_parts.append(p["value"])
            elif p["type"] == "image":
                img_counter += 1
                url = p["src"]
                if base_url and not url.startswith(("http://", "https://")):
                    url = urljoin(base_url, url)
                ext = _ext_from_url(url)
                filename = f"img_{img_counter:03d}{ext}"
                alt = p.get("alt", "")
                images.append({"url": url, "alt": alt, "filename": filename})
                seg_parts.append(f"![{alt}](assets/{filename})")
            elif p["type"] == "formula":
                formula_count += 1
                latex = p["latex"]
                if p.get("display"):
                    seg_parts.append(f"\n$$\n{latex}\n$$\n")
                else:
                    seg_parts.append(f"${latex}$")

        segment = " ".join(seg_parts).strip()
        if segment and len(segment) > 2 and segment not in seen_texts:
            seen_texts.add(segment)
            text_segments.append(segment)

    full_text = "\n\n".join(text_segments)

    return CrawlResult(
        text=full_text,
        images=images,
        formula_count=formula_count,
    )


async def _scroll_page(page, engine: str = "pyppeteer"):
    """滚动到底部以触发懒加载，两个引擎共用。"""
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


async def _scroll_and_collect_rich_pyppeteer(page, selectors: list, base_url: str = "") -> CrawlResult:
    """Pyppeteer 版：滚动并收集富内容（文本+图片+公式）。"""
    await _scroll_page(page, "pyppeteer")

    for sel in selectors:
        try:
            elements = await page.querySelectorAll(sel)
            if not elements:
                continue
            all_parts = await page.evaluate(_DOM_WALKER_JS, elements)
            if all_parts and any(all_parts):
                result = _process_dom_parts(all_parts, base_url)
                if result.text.strip():
                    return result
        except Exception:
            continue

    # 回退：body 纯文本
    body_text = await page.evaluate("""() => {
        const main = document.querySelector('main') || document.body;
        return main ? main.innerText || main.textContent || '' : '';
    }""")
    return CrawlResult(text=(body_text or "").strip())


async def _scroll_and_collect_rich_playwright(page, selectors: list, base_url: str = "") -> CrawlResult:
    """Playwright 版：滚动并收集富内容（文本+图片+公式）。"""
    await _scroll_page(page, "playwright")

    for sel in selectors:
        try:
            elements = await page.query_selector_all(sel)
            if not elements:
                continue
            # Playwright evaluate 需用 evaluate_handle 传递 ElementHandle 列表
            all_parts = await page.evaluate(
                _DOM_WALKER_JS,
                elements,
            )
            if all_parts and any(all_parts):
                result = _process_dom_parts(all_parts, base_url)
                if result.text.strip():
                    return result
        except Exception:
            continue

    body_text = await page.evaluate("""() => {
        const main = document.querySelector('main') || document.body;
        return main ? main.innerText || main.textContent || '' : '';
    }""")
    return CrawlResult(text=(body_text or "").strip())


async def _download_images_pyppeteer(page, images: list) -> list:
    """在 Pyppeteer 浏览器上下文中下载图片（保留 cookies/CORS）。"""
    downloaded = []
    for img in images:
        url = img["url"]
        try:
            data = await page.evaluate("""async (url) => {
                try {
                    const resp = await fetch(url);
                    if (!resp.ok) return null;
                    const buf = await resp.arrayBuffer();
                    const bytes = new Uint8Array(buf);
                    let binary = '';
                    for (let i = 0; i < bytes.length; i++) binary += String.fromCharCode(bytes[i]);
                    return btoa(binary);
                } catch(e) { return null; }
            }""", url)
            if data:
                import base64
                downloaded.append({**img, "data": base64.b64decode(data)})
            else:
                downloaded.append({**img, "data": None})
        except Exception:
            downloaded.append({**img, "data": None})
    return downloaded


async def _download_images_playwright(page, images: list) -> list:
    """在 Playwright 浏览器上下文中下载图片。"""
    downloaded = []
    for img in images:
        url = img["url"]
        try:
            data = await page.evaluate("""async (url) => {
                try {
                    const resp = await fetch(url);
                    if (!resp.ok) return null;
                    const buf = await resp.arrayBuffer();
                    const bytes = new Uint8Array(buf);
                    let binary = '';
                    for (let i = 0; i < bytes.length; i++) binary += String.fromCharCode(bytes[i]);
                    return btoa(binary);
                } catch(e) { return null; }
            }""", url)
            if data:
                import base64
                downloaded.append({**img, "data": base64.b64decode(data)})
            else:
                downloaded.append({**img, "data": None})
        except Exception:
            downloaded.append({**img, "data": None})
    return downloaded


async def _crawl_playwright(url: str, selectors: list) -> CrawlResult:
    """备用：使用 Playwright + Chromium（通过 install-browser 安装）。"""
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            page = await browser.new_page()
            await page.set_viewport_size({"width": 1280, "height": 800})
            await page.set_extra_http_headers({"User-Agent": _USER_AGENT})

            result = CrawlResult()
            for attempt in range(1, CRAWL_MAX_RETRIES + 1):
                await page.goto(url, wait_until="networkidle", timeout=60000)
                await asyncio.sleep(2.5)

                result = await _scroll_and_collect_rich_playwright(page, selectors, url)
                if len(result.text.encode("utf-8")) >= MIN_CONTENT_BYTES:
                    break
                if attempt < CRAWL_MAX_RETRIES:
                    await asyncio.sleep(RETRY_WAIT_SECONDS)

            # 下载图片
            if result.images:
                result.images = await _download_images_playwright(page, result.images)

            return result
        finally:
            await browser.close()


async def _crawl_pyppeteer(url: str, selectors: list) -> CrawlResult:
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

        result = CrawlResult()
        for attempt in range(1, CRAWL_MAX_RETRIES + 1):
            await page.goto(url, waitUntil="networkidle2", timeout=60000)
            await asyncio.sleep(2.5)

            result = await _scroll_and_collect_rich_pyppeteer(page, selectors, url)
            if len(result.text.encode("utf-8")) >= MIN_CONTENT_BYTES:
                break
            if attempt < CRAWL_MAX_RETRIES:
                await asyncio.sleep(RETRY_WAIT_SECONDS)

        # 下载图片
        if result.images:
            result.images = await _download_images_pyppeteer(page, result.images)

        return result
    finally:
        await browser.close()


def crawl_url(url: str, platform: str = "chatgpt") -> CrawlResult:
    """
    同步入口：抓取 URL，返回 CrawlResult（文本 + 图片 + 公式计数）。
    首选 Pyppeteer（需 Chrome/Edge 或 pyppeteer-install），
    失败时回退到 Playwright（需运行 install-browser）。
    """
    selectors = _CHATGPT_SELECTORS if platform == "chatgpt" else _GENERIC_SELECTORS

    try:
        result = asyncio.run(_crawl_pyppeteer(url, selectors))
    except ImportError:
        print("[提示] Pyppeteer 未安装，尝试使用 Playwright 备用...")
        result = asyncio.run(_crawl_playwright(url, selectors))
    except Exception as e:
        err_str = str(e).lower()
        if "executable" in err_str or "browser" in err_str or "chrome" in err_str:
            print("[提示] 未找到 Chrome/Edge，尝试 Playwright Chromium...")
        try:
            result = asyncio.run(_crawl_playwright(url, selectors))
        except Exception as e2:
            raise RuntimeError(
                f"爬虫失败。请安装浏览器：\n"
                f"  1. 首选: 安装 Chrome/Edge 或运行 pyppeteer-install\n"
                f"  2. 备用: python main.py install-browser（Playwright Chromium）\n"
                f"错误: {e2}"
            ) from e2

    # 后处理：如果 DOM 未检测到公式，尝试 Unicode 数学字符 → LaTeX 转换
    # 覆盖所有代码路径（DOM walker、fallback innerText、Pyppeteer/Playwright）
    if result.formula_count == 0 and result.text:
        from src.utils.unicode_math import convert_unicode_math_to_latex, count_math_unicode
        if count_math_unicode(result.text) >= 3:
            new_text, fc = convert_unicode_math_to_latex(result.text)
            result = CrawlResult(text=new_text, images=result.images, formula_count=fc)

    return result
