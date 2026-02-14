# -*- coding: utf-8 -*-
"""
AI 对话记录整理：支持 ChatGPT、Gemini、Perplexity 的分享链接或导出文件。
抓取/导入 → Kimi 分类与报告 1.0/3.0 → 专家评审 → Word 导出。
"""
import argparse
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

from config import RAW_DIR, REPORT_DIR


def cmd_install_browser(args):
    """安装 Playwright Chromium（无需 Chrome，推荐用于爬虫）"""
    import subprocess
    subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], check=True)
    print("Playwright Chromium 已安装完成。")

def cmd_crawl(args):
    """抓取分享链接，URL 仅从命令行参数传入，不从文件读取。"""
    from src.step1_crawler import run_crawl
    url = args.url.strip()
    if not url.startswith(("http://", "https://")):
        raise ValueError("抓取 URL 须以 http:// 或 https:// 开头，请通过命令行参数传入")
    return run_crawl(url, args.output)


def cmd_import(args):
    """从本地文件导入对话（如 Perplexity 下载的 .md），文件路径由命令行传入。"""
    from src.ingest.sources import run_ingest
    return run_ingest(str(args.file).strip(), args.output)


def cmd_fetch(args):
    """统一入口：URL 或本地文件路径。抓取页面的 URL 由命令行参数传入，不从文件读取。"""
    from src.ingest.sources import run_ingest
    return run_ingest(args.input, args.output)


def cmd_merge(args):
    """Step0: 读取目录下所有语料，经 API 去重排序后合成为本地语料文件。"""
    from src.step0_corpus_merge import run_corpus_merge
    dir_path = Path(args.dir)
    if not dir_path.is_absolute():
        dir_path = Path.cwd() / dir_path
    run_corpus_merge(dir_path, args.output, getattr(args, "recursive", False))


def _apply_provider(provider: str):
    """命令行指定 Provider 时覆盖环境变量。"""
    if provider:
        os.environ["LLM_PROVIDER"] = provider


def cmd_batch(args):
    """Step0 语料重整 + 全流程：读取目录语料 → 去重排序 → 1.0 → 专家 → 2.0 → 3.0"""
    import time
    _apply_provider(getattr(args, "provider", None))
    from src.step0_corpus_merge import run_corpus_merge
    dir_path = Path(args.dir)
    if not dir_path.is_absolute():
        dir_path = Path.cwd() / dir_path
    base = args.output or dir_path.name
    style = getattr(args, "final_style", "A")

    ts = time.strftime("%H:%M:%S", time.localtime())
    print(f"\n[{ts}] ========== 批量语料流程开始 ==========", flush=True)
    print(f"[{ts}] 目录: {dir_path}", flush=True)
    print(f"[{ts}] ======================================\n", flush=True)

    ts = time.strftime("%H:%M:%S", time.localtime())
    print(f"\n[{ts}] ---------- Step0 语料重整 ----------\n", flush=True)
    raw_path = run_corpus_merge(dir_path, base, getattr(args, "recursive", False))

    ts = time.strftime("%H:%M:%S", time.localtime())
    print(f"\n[{ts}] ---------- Step2 报告 1.0 ----------\n", flush=True)
    from src.step2_report_v1 import run_meta_and_report_v1
    r1 = run_meta_and_report_v1(raw_path, base)
    report_v1_path = Path(r1["report_v1_path"])

    ts = time.strftime("%H:%M:%S", time.localtime())
    print(f"\n[{ts}] ---------- Step3 专家评审 ----------\n", flush=True)
    cmd_experts(argparse.Namespace(report_v1=report_v1_path, output_base=base))

    ts = time.strftime("%H:%M:%S", time.localtime())
    print(f"\n[{ts}] ---------- Step4 报告 2.0 ----------\n", flush=True)
    cmd_report_v2(argparse.Namespace(report_v1=report_v1_path, expert_file=None, output_base=base, raw_file=raw_path))

    report_v2_path = REPORT_DIR / f"{base}_report_v2.md"
    if not report_v2_path.is_file():
        report_v2_path = REPORT_DIR / f"{base}_report_v2_new.md"
    ts = time.strftime("%H:%M:%S", time.localtime())
    print(f"\n[{ts}] ---------- Step5 报告 3.0 最终版 ----------\n", flush=True)
    cmd_report_final(argparse.Namespace(report_v2=report_v2_path, output_base=base, style=style, raw_file=raw_path))

    ts = time.strftime("%H:%M:%S", time.localtime())
    print(f"\n[{ts}] ========== 批量语料流程完成 ==========\n", flush=True)


def cmd_report_v1(args):
    from src.step2_report_v1 import run_meta_and_report_v1
    raw_path = Path(args.raw_file)
    if not raw_path.is_absolute():
        raw_path = RAW_DIR / raw_path.name
    run_meta_and_report_v1(raw_path, args.output_base)
    base = args.output_base or raw_path.stem
    return REPORT_DIR / f"{base}_report_v1.md"


def cmd_experts(args):
    from src.step3_experts import run_experts
    report_v1 = Path(args.report_v1)
    if not report_v1.is_absolute():
        report_v1 = REPORT_DIR / report_v1.name
    run_experts(report_v1, args.output_base)


def cmd_report_v3(args):
    """报告 3.0：先规划结构，再逐章分段生成，篇幅充足、不丢失信息。"""
    from src.step2_report_v3 import run_report_v3
    raw_path = Path(args.raw_file)
    if not raw_path.is_absolute():
        raw_path = RAW_DIR / raw_path.name
    run_report_v3(raw_path, args.output_base)


def cmd_report_v2(args):
    from src.step4_report_v2 import run_report_v2_and_docx
    report_v1 = Path(args.report_v1)
    if not report_v1.is_absolute():
        report_v1 = REPORT_DIR / report_v1.name
    expert = Path(args.expert_file) if args.expert_file else None
    raw_path = Path(args.raw_file) if getattr(args, "raw_file", None) else None
    if raw_path and not raw_path.is_absolute():
        raw_path = RAW_DIR / raw_path.name
    run_report_v2_and_docx(report_v1, expert, args.output_base, raw_path)


def cmd_report_v4(args):
    """报告 4.0：对 3.0 做事实核查与出处标注，调用 Perplexity 获取引用，在正文插入 [n] 标记并生成 References。"""
    from src.step6_report_v4 import run_report_v4
    report_v3 = Path(args.report_v3)
    if not report_v3.is_absolute():
        report_v3 = REPORT_DIR / report_v3.name
    run_report_v4(report_v3, args.output_base)


def cmd_report_final(args):
    """报告 3.0 最终版：在 2.0 基础上改写，列表→自然叙述，支持风格 A/B/C；须传入原始语料用于幻觉校验。"""
    from src.step5_report_final import run_report_final
    report_v2 = Path(args.report_v2)
    if not report_v2.is_absolute():
        report_v2 = REPORT_DIR / report_v2.name
    raw_path = Path(args.raw_file) if getattr(args, "raw_file", None) else None
    if raw_path and not raw_path.is_absolute():
        raw_path = RAW_DIR / raw_path.name
    run_report_final(report_v2, args.output_base, args.style, raw_path)


def cmd_all_v3(args):
    """全流程：抓取/导入 → 报告 3.0"""
    from src.ingest.sources import run_ingest, detect_source
    raw_path = run_ingest(args.input, args.output)
    base = args.output or (raw_path.stem if raw_path else "share")
    from src.step2_report_v3 import run_report_v3
    run_report_v3(raw_path, base)


def cmd_all(args):
    """全流程：抓取/导入 → 报告1.0 → 专家 → 报告2.0 → 报告3.0 最终版+Word"""
    import time
    _apply_provider(getattr(args, "provider", None))
    t_start = time.time()
    ts = time.strftime("%H:%M:%S", time.localtime())
    print(f"\n[{ts}] ========== 全流程开始 ==========", flush=True)
    print(f"[{ts}] 输入: {args.input}", flush=True)
    print(f"[{ts}] ======================================\n", flush=True)

    from src.step2_report_v1 import run_meta_and_report_v1
    from src.ingest.sources import run_ingest
    raw_path = run_ingest(args.input, args.output)
    base = args.output or (raw_path.stem if raw_path else "share")
    style = getattr(args, "final_style", "A")

    ts = time.strftime("%H:%M:%S", time.localtime())
    print(f"\n[{ts}] ---------- Step2 报告 1.0 ----------\n", flush=True)
    r1 = run_meta_and_report_v1(raw_path, base)
    report_v1_path = Path(r1["report_v1_path"])
    ts = time.strftime("%H:%M:%S", time.localtime())
    print(f"\n[{ts}] ---------- Step3 专家评审 ----------\n", flush=True)
    cmd_experts(argparse.Namespace(report_v1=report_v1_path, output_base=base))
    ts = time.strftime("%H:%M:%S", time.localtime())
    print(f"\n[{ts}] ---------- Step4 报告 2.0 ----------\n", flush=True)
    cmd_report_v2(argparse.Namespace(report_v1=report_v1_path, expert_file=None, output_base=base, raw_file=raw_path))
    report_v2_path = REPORT_DIR / f"{base}_report_v2.md"
    if not report_v2_path.is_file():
        report_v2_path = REPORT_DIR / f"{base}_report_v2_new.md"
    ts = time.strftime("%H:%M:%S", time.localtime())
    print(f"\n[{ts}] ---------- Step5 报告 3.0 最终版 ----------\n", flush=True)
    cmd_report_final(argparse.Namespace(report_v2=report_v2_path, output_base=base, style=style, raw_file=raw_path))

    ts = time.strftime("%H:%M:%S", time.localtime())
    elapsed = time.time() - t_start
    print(f"\n[{ts}] ========== 全流程完成，总耗时 {elapsed/60:.1f} 分钟 ==========\n", flush=True)


def cmd_all_context(args):
    """全流程（多轮对话）：抓取/导入 → 多轮 Kimi 会话（保持原始语料记忆）→ 报告1.0 → 专家 → 报告2.0，报告2.0 篇幅接近原始语料"""
    from src.ingest.sources import run_ingest
    from src.step_report_pipeline import run_pipeline
    raw_path = run_ingest(args.input, args.output)
    base = args.output or (raw_path.stem if raw_path else "share")
    run_pipeline(raw_path, base)


def main():
    parser = argparse.ArgumentParser(description="ChatGPT 分享链接 → 深度报告 2.0 + Word")
    sub = parser.add_subparsers(dest="command", help="子命令")

    # 安装浏览器（Playwright Chromium，Pyppeteer 失败时备用）
    p0a = sub.add_parser("install-browser", help="安装 Playwright Chromium（Pyppeteer 不可用时的备用）")
    p0a.set_defaults(func=cmd_install_browser)

    # step1 - 抓取分享链接（URL 由命令行传入，不从文件读取）
    p1 = sub.add_parser("crawl", help="抓取分享链接，URL 由命令行参数传入（ChatGPT/Gemini/Perplexity）")
    p1.add_argument("url", help="要抓取的页面 URL（仅命令行传入）")
    p1.add_argument("-o", "--output", default=None, help="输出文件名（不含扩展名）")
    p1.set_defaults(func=cmd_crawl)

    # 导入本地文件（如 Perplexity 页面下载的 .md）
    p1b = sub.add_parser("import", help="从本地文件导入对话（.txt/.json/.md），文件名由命令行传入")
    p1b.add_argument("file", help="本地文件路径（由命令行传入）")
    p1b.add_argument("-o", "--output", default=None, help="输出文件名（不含扩展名）")
    p1b.set_defaults(func=cmd_import)

    # 统一入口（URL 或文件；抓取时 URL 由命令行传入）
    p1c = sub.add_parser("fetch", help="统一入口：URL 或本地文件路径（抓取 URL 由命令行传入）")
    p1c.add_argument("input", help="分享链接或本地文件路径")
    p1c.add_argument("-o", "--output", default=None, help="输出文件名（不含扩展名）")
    p1c.set_defaults(func=cmd_fetch)

    # step0 - 目录语料重整（新增功能，不影响原流程）
    p0m = sub.add_parser("merge", help="Step0: 读取目录下所有语料，经 API 去重排序后合成为 output/raw/xxx.txt")
    p0m.add_argument("dir", type=Path, help="语料目录路径")
    p0m.add_argument("-o", "--output", default=None, help="输出文件名（不含扩展名），默认用目录名")
    p0m.add_argument("-r", "--recursive", action="store_true", help="递归读取子目录")
    p0m.set_defaults(func=cmd_merge)

    p0b2 = sub.add_parser("batch", help="批量流程：目录语料重整 → 1.0 → 专家 → 2.0 → 3.0 最终版")
    p0b2.add_argument("dir", type=Path, help="语料目录路径")
    p0b2.add_argument("-o", "--output", default=None, help="输出文件名前缀")
    p0b2.add_argument("-r", "--recursive", action="store_true", help="递归读取子目录")
    p0b2.add_argument("-s", "--final-style", default="A", choices=["A", "B", "C"],
                      help="报告3.0风格: A=商业模式设计报告, B=可行性研究报告, C=学术综述")
    p0b2.add_argument("-p", "--provider", choices=["kimi", "openai", "grok", "perplexity", "claude", "gemini"],
                      help="指定 LLM Provider（覆盖 .env 中的 LLM_PROVIDER）")
    p0b2.set_defaults(func=cmd_batch)

    # step2
    p2 = sub.add_parser("report-v1", help="Step2: 生成标题/摘要/关键词与深度报告 1.0")
    p2.add_argument("raw_file", type=Path, help="原始文本，如 output/raw/xxx.txt")
    p2.add_argument("-o", "--output-base", default=None, help="输出文件名前缀")
    p2.set_defaults(func=lambda a: cmd_report_v1(a) or None)

    # step3
    p3 = sub.add_parser("experts", help="Step3: 三位专家评审，生成意见文档")
    p3.add_argument("report_v1", help="报告 1.0 路径，如 output/reports/xxx_report_v1.md")
    p3.add_argument("-o", "--output-base", default=None, help="输出文件名前缀")
    p3.set_defaults(func=cmd_experts)

    # report-v3（按章节分段生成，篇幅充足）
    p3b = sub.add_parser("report-v3", help="报告 3.0: 先规划结构，再逐章分段生成，篇幅充足")
    p3b.add_argument("raw_file", type=Path, help="原始文本，如 output/raw/xxx.txt")
    p3b.add_argument("-o", "--output-base", default=None, help="输出文件名前缀")
    p3b.set_defaults(func=cmd_report_v3)

    # step4
    p4 = sub.add_parser("report-v2", help="Step4: 根据专家意见生成报告 2.0 并导出 Word")
    p4.add_argument("report_v1", help="报告 1.0 路径")
    p4.add_argument("-e", "--expert-file", default=None, help="专家意见汇总路径（可选）")
    p4.add_argument("-r", "--raw-file", default=None, help="原始语料路径（可选，用于补充 ChatGPT 论述逻辑）")
    p4.add_argument("-o", "--output-base", default=None, help="输出文件名前缀")
    p4.set_defaults(func=cmd_report_v2)

    # step5
    p5 = sub.add_parser("report-final", help="Step5: 在报告 2.0 基础上生成 3.0 最终版（列表→自然叙述，可指定风格，须传入原始语料用于幻觉校验）")
    # step6
    p6 = sub.add_parser("report-v4", help="Step6: 对报告 3.0 做事实核查与出处标注，调用 Perplexity 获取引用，生成 4.0（含 References）")
    p6.add_argument("report_v3", help="报告 3.0 路径，如 output/reports/xxx_report_v3.md")
    p6.add_argument("-o", "--output-base", default=None, help="输出文件名前缀")
    p6.set_defaults(func=cmd_report_v4)
    p5.add_argument("report_v2", help="报告 2.0 路径，如 output/reports/xxx_report_v2.md")
    p5.add_argument("-r", "--raw-file", required=True, help="原始语料路径（必填，用于幻觉校验）")
    p5.add_argument("-o", "--output-base", default=None, help="输出文件名前缀")
    p5.add_argument("-s", "--style", default="A", choices=["A", "B", "C"],
                    help="文档风格: A=商业模式设计报告, B=可行性研究报告, C=学术综述")
    p5.set_defaults(func=cmd_report_final)

    # all（含 Perplexity 本地 .md：下载页面后，文件路径由命令行传入）
    p0 = sub.add_parser("all", help="全流程：导入/抓取 → 报告1.0 → 专家 → 报告2.0 → 报告3.0 最终版+Word")
    p0.add_argument("input", help="本地文件路径（如 Perplexity 下载的 .md）或分享链接，由命令行传入")
    p0.add_argument("-o", "--output", default=None, help="各步骤输出文件名前缀")
    p0.add_argument("-s", "--final-style", default="A", choices=["A", "B", "C"],
                    help="报告3.0风格: A=商业模式设计报告, B=可行性研究报告, C=学术综述")
    p0.add_argument("-p", "--provider", choices=["kimi", "openai", "grok", "perplexity", "claude", "gemini"],
                    help="指定 LLM Provider（覆盖 .env 中的 LLM_PROVIDER）")
    p0.set_defaults(func=cmd_all)

    # all-v3
    p0b = sub.add_parser("all-v3", help="全流程：fetch → report-v3（按章节分段，篇幅充足）")
    p0b.add_argument("input", help="分享链接或本地文件路径（抓取 URL 由命令行传入）")
    p0b.add_argument("-o", "--output", default=None, help="各步骤输出文件名前缀")
    p0b.set_defaults(func=cmd_all_v3)

    # all-context（多轮对话，保持原始语料记忆，报告2.0 篇幅接近原文）
    p0c = sub.add_parser("all-context", help="全流程（多轮对话）：fetch → Kimi 多轮会话（保持记忆）→ 报告1.0 → 专家 → 报告2.0，2.0 篇幅接近原文")
    p0c.add_argument("input", help="本地文件或分享链接，由命令行传入")
    p0c.add_argument("-o", "--output", default=None, help="各步骤输出文件名前缀")
    p0c.set_defaults(func=cmd_all_context)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        return
    args.func(args)


if __name__ == "__main__":
    main()
