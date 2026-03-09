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

from config import RAW_DIR, REPORT_DIR, FILES_DIR
from src.report_type_profiles import list_supported_report_types, load_report_type_profile

REPORT_TYPE_CHOICES = list_supported_report_types()


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


def _add_report_type_arg(parser: argparse.ArgumentParser):
    parser.add_argument(
        "-t",
        "--report-type",
        default=None,
        choices=REPORT_TYPE_CHOICES,
        help=f"报告类型（可选: {', '.join(REPORT_TYPE_CHOICES)}）",
    )


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
    cmd_experts(
        argparse.Namespace(
            report_v1=report_v1_path,
            output_base=base,
            report_type=getattr(args, "report_type", None),
        )
    )

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
    run_experts(report_v1, args.output_base, getattr(args, "report_type", None))


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


def cmd_report_v5(args):
    """Step8：基于 Step7 输出，Prompt RL 迭代压缩，输出报告 5.0。使用 Gemini API。"""
    from src.step8_report_v5 import run_report_v5
    report_path = Path(args.report)
    if not report_path.is_absolute():
        report_path = REPORT_DIR / report_path.name
    run_report_v5(
        report_path,
        args.output_base,
        getattr(args, "policy", "policy1"),
        getattr(args, "report_type", None),
    )


def cmd_report_policy(args):
    """Step7（可选）：根据原始语料与最新报告，采用 Skill/summary 风格化，输出学术风格分析报告。使用 Gemini API。"""
    from src.step7_report_policy import run_report_policy
    raw_path = Path(args.raw)
    report_path = Path(args.report)
    if not raw_path.is_absolute():
        raw_path = RAW_DIR / raw_path.name
    if not report_path.is_absolute():
        report_path = REPORT_DIR / report_path.name
    run_report_policy(
        raw_path,
        report_path,
        args.output_base,
        getattr(args, "policy", "policy1"),
        getattr(args, "report_type", None),
    )


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
    cmd_experts(
        argparse.Namespace(
            report_v1=report_v1_path,
            output_base=base,
            report_type=getattr(args, "report_type", None),
        )
    )
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


def cmd_full_report(args):
    """全流程 Step0→Step8：语料目录/文件 → 1.0→专家→2.0→3.0→4.0→Step7 学术分析→5.0，使用 Gemini，输出各版本文件。"""
    import time
    _apply_provider(getattr(args, "provider", None))
    input_path = Path(args.input)
    if not input_path.is_absolute():
        input_path = PROJECT_ROOT / input_path
    base = args.output_base or (input_path.name if input_path.is_dir() else input_path.stem)

    if input_path.is_dir():
        from src.step0_corpus_merge import run_corpus_merge
        raw_path = run_corpus_merge(input_path, base, getattr(args, "recursive", True))
    elif input_path.is_file():
        import shutil
        raw_path = RAW_DIR / f"{base}.txt"
        if input_path.suffix.lower() in (".txt", ".md"):
            shutil.copy2(input_path, raw_path)
        else:
            from src.ingest.file_importer import import_from_file
            from src.corpus_extractors import extract_from_docx, extract_from_pdf
            suffix = input_path.suffix.lower()
            if suffix == ".docx":
                text = extract_from_docx(input_path)
            elif suffix == ".pdf":
                text = extract_from_pdf(input_path)
            else:
                text = import_from_file(input_path)
            raw_path.write_text(text, encoding="utf-8", errors="replace")
    else:
        raise FileNotFoundError(f"输入不存在: {input_path}")

    cmd_report_v1(argparse.Namespace(raw_file=raw_path, output_base=base))
    report_v1_path = REPORT_DIR / f"{base}_report_v1.md"

    cmd_experts(
        argparse.Namespace(
            report_v1=report_v1_path,
            output_base=base,
            report_type=getattr(args, "report_type", None),
        )
    )
    cmd_report_v2(argparse.Namespace(report_v1=report_v1_path, expert_file=None, output_base=base, raw_file=raw_path))

    report_v2_path = REPORT_DIR / f"{base}_report_v2.md"
    if not report_v2_path.is_file():
        report_v2_path = REPORT_DIR / f"{base}_report_v2_new.md"
    cmd_report_final(argparse.Namespace(report_v2=report_v2_path, output_base=base, style=getattr(args, "style", "A"), raw_file=raw_path))

    report_v3_path = REPORT_DIR / f"{base}_report_v3.md"
    if not report_v3_path.is_file():
        report_v3_path = REPORT_DIR / f"{base}_report_v3_new.md"
    cmd_report_v4(argparse.Namespace(report_v3=report_v3_path, output_base=base))

    report_v4_path = REPORT_DIR / f"{base}_report_v4.docx"
    if not report_v4_path.is_file():
        report_v4_path = REPORT_DIR / f"{base}_report_v4.md"
    cmd_report_policy(
        argparse.Namespace(
            raw=raw_path,
            report=report_v4_path,
            output_base=base,
            policy=getattr(args, "policy", "policy1"),
            report_type=getattr(args, "report_type", None),
        )
    )

    profile = load_report_type_profile(getattr(args, "report_type", None))
    step7_suffix = profile.get("step7_title_suffix", "学术风格分析报告")
    policy_report = REPORT_DIR / f"{base}_{step7_suffix}.docx"
    if not policy_report.is_file():
        policy_report = REPORT_DIR / f"{base}_{step7_suffix}.md"
    cmd_report_v5(
        argparse.Namespace(
            report=policy_report,
            output_base=base,
            policy=getattr(args, "policy", "policy1"),
            report_type=getattr(args, "report_type", None),
        )
    )

    ts = time.strftime("%H:%M:%S", time.localtime())
    print(f"\n[{ts}] ========== Step1~Step8 完成，1.0~5.0 已输出至 output/reports ==========\n", flush=True)


def cmd_all_context(args):
    """全流程（多轮对话）：抓取/导入 → 多轮 Kimi 会话（保持原始语料记忆）→ 报告1.0 → 专家 → 报告2.0，报告2.0 篇幅接近原始语料"""
    from src.ingest.sources import run_ingest
    from src.step_report_pipeline import run_pipeline
    raw_path = run_ingest(args.input, args.output)
    base = args.output or (raw_path.stem if raw_path else "share")
    run_pipeline(raw_path, base)


def cmd_help_all(args):
    """显示主命令与全部子命令参数。"""
    parser = args._root_parser
    subparsers = args._subparsers_map
    parser.print_help()
    print("\n" + "=" * 80)
    print("子命令参数总览")
    print("=" * 80)
    for name in sorted(subparsers.keys()):
        print(f"\n[ {name} ]")
        subparsers[name].print_help()


def main():
    parser = argparse.ArgumentParser(
        description="ChatGPT 分享链接 → 深度报告 2.0 + Word",
        epilog="提示：可用 `python main.py help-all` 查看所有子命令参数总览。",
    )
    sub = parser.add_subparsers(dest="command", help="子命令")
    subparsers_map = {}

    # help-all：显示全部参数
    ph = sub.add_parser("help-all", help="显示主命令与全部子命令参数")
    subparsers_map["help-all"] = ph
    ph.set_defaults(func=cmd_help_all)

    p0a = sub.add_parser("install-browser", help="安装 Playwright Chromium（Pyppeteer 不可用时的备用）")
    subparsers_map["install-browser"] = p0a
    p0a.set_defaults(func=cmd_install_browser)

    p1 = sub.add_parser("crawl", help="抓取分享链接，URL 由命令行参数传入（ChatGPT/Gemini/Perplexity）")
    subparsers_map["crawl"] = p1
    p1.add_argument("url", help="要抓取的页面 URL（仅命令行传入）")
    p1.add_argument("-o", "--output", default=None, help="输出文件名（不含扩展名）")
    p1.set_defaults(func=cmd_crawl)

    p1b = sub.add_parser("import", help="从本地文件导入对话（.txt/.json/.md），文件名由命令行传入")
    subparsers_map["import"] = p1b
    p1b.add_argument("file", help="本地文件路径（由命令行传入）")
    p1b.add_argument("-o", "--output", default=None, help="输出文件名（不含扩展名）")
    p1b.set_defaults(func=cmd_import)

    p1c = sub.add_parser("fetch", help="统一入口：URL 或本地文件路径（抓取 URL 由命令行传入）")
    subparsers_map["fetch"] = p1c
    p1c.add_argument("input", help="分享链接或本地文件路径")
    p1c.add_argument("-o", "--output", default=None, help="输出文件名（不含扩展名）")
    p1c.set_defaults(func=cmd_fetch)

    p0m = sub.add_parser("merge", help="Step0: 读取目录下所有语料，经 API 去重排序后合成为 output/raw/xxx.txt")
    subparsers_map["merge"] = p0m
    p0m.add_argument("dir", type=Path, help="语料目录路径")
    p0m.add_argument("-o", "--output", default=None, help="输出文件名（不含扩展名），默认用目录名")
    p0m.add_argument("-r", "--recursive", action="store_true", help="递归读取子目录")
    p0m.set_defaults(func=cmd_merge)

    p0b2 = sub.add_parser("batch", help="批量流程：目录语料重整 → 1.0 → 专家 → 2.0 → 3.0 最终版")
    subparsers_map["batch"] = p0b2
    p0b2.add_argument("dir", type=Path, help="语料目录路径")
    p0b2.add_argument("-o", "--output", default=None, help="输出文件名前缀")
    p0b2.add_argument("-r", "--recursive", action="store_true", help="递归读取子目录")
    p0b2.add_argument("-s", "--final-style", default="A", choices=["A", "B", "C"], help="报告3.0风格")
    p0b2.add_argument("-p", "--provider", choices=["kimi", "gemini", "grok", "minimax", "glm", "qwen", "deepseek", "openai", "perplexity", "claude"], help="指定 LLM Provider（覆盖 .env 中的 LLM_PROVIDER）")
    _add_report_type_arg(p0b2)
    p0b2.set_defaults(func=cmd_batch)

    p2 = sub.add_parser("report-v1", help="Step2: 生成标题/摘要/关键词与深度报告 1.0")
    subparsers_map["report-v1"] = p2
    p2.add_argument("raw_file", type=Path, help="原始文本，如 output/raw/xxx.txt")
    p2.add_argument("-o", "--output-base", default=None, help="输出文件名前缀")
    p2.set_defaults(func=lambda a: cmd_report_v1(a) or None)

    p3 = sub.add_parser("experts", help="Step3: 三位专家评审，生成意见文档")
    subparsers_map["experts"] = p3
    p3.add_argument("report_v1", help="报告 1.0 路径，如 output/reports/xxx_report_v1.md")
    p3.add_argument("-o", "--output-base", default=None, help="输出文件名前缀")
    _add_report_type_arg(p3)
    p3.set_defaults(func=cmd_experts)

    p3b = sub.add_parser("report-v3", help="报告 3.0: 先规划结构，再逐章分段生成，篇幅充足")
    subparsers_map["report-v3"] = p3b
    p3b.add_argument("raw_file", type=Path, help="原始文本，如 output/raw/xxx.txt")
    p3b.add_argument("-o", "--output-base", default=None, help="输出文件名前缀")
    p3b.set_defaults(func=cmd_report_v3)

    p4 = sub.add_parser("report-v2", help="Step4: 根据专家意见生成报告 2.0 并导出 Word")
    subparsers_map["report-v2"] = p4
    p4.add_argument("report_v1", help="报告 1.0 路径")
    p4.add_argument("-e", "--expert-file", default=None, help="专家意见汇总路径（可选）")
    p4.add_argument("-r", "--raw-file", default=None, help="原始语料路径（可选，用于补充 ChatGPT 论述逻辑）")
    p4.add_argument("-o", "--output-base", default=None, help="输出文件名前缀")
    p4.set_defaults(func=cmd_report_v2)

    p5 = sub.add_parser("report-final", help="Step5: 在报告 2.0 基础上生成 3.0 最终版（列表→自然叙述，可指定风格）")
    subparsers_map["report-final"] = p5
    p5.add_argument("report_v2", help="报告 2.0 路径，如 output/reports/xxx_report_v2.md")
    p5.add_argument("-r", "--raw-file", required=True, help="原始语料路径（必填，用于幻觉校验）")
    p5.add_argument("-o", "--output-base", default=None, help="输出文件名前缀")
    p5.add_argument("-s", "--style", default="A", choices=["A", "B", "C"], help="文档风格: A/B/C")
    p5.set_defaults(func=cmd_report_final)

    p6 = sub.add_parser("report-v4", help="Step6: 对报告 3.0 做事实核查与出处标注，生成 4.0（含 References）")
    subparsers_map["report-v4"] = p6
    p6.add_argument("report_v3", help="报告 3.0 路径，如 output/reports/xxx_report_v3.md")
    p6.add_argument("-o", "--output-base", default=None, help="输出文件名前缀")
    p6.set_defaults(func=cmd_report_v4)

    p7 = sub.add_parser("report-policy", help="Step7: 采用 policy 风格化重写，输出类型化报告")
    subparsers_map["report-policy"] = p7
    p7.add_argument("raw", help="原始语料路径")
    p7.add_argument("report", help="最新版报告路径")
    p7.add_argument("-o", "--output-base", default=None, help="输出文件名前缀")
    p7.add_argument("-p", "--policy", default="policy1", help="output/skill 下的 policy 子目录名")
    _add_report_type_arg(p7)
    p7.set_defaults(func=cmd_report_policy)

    p8 = sub.add_parser("report-v5", help="Step8: Prompt RL 迭代压缩，输出报告 5.0")
    subparsers_map["report-v5"] = p8
    p8.add_argument("report", help="Step7 输出路径")
    p8.add_argument("-o", "--output-base", default=None, help="输出文件名前缀")
    p8.add_argument("-p", "--policy", default="policy1", help="policy 子目录名")
    _add_report_type_arg(p8)
    p8.set_defaults(func=cmd_report_v5)

    p0 = sub.add_parser("all", help="全流程：导入/抓取 → 报告1.0 → 专家 → 报告2.0 → 报告3.0")
    subparsers_map["all"] = p0
    p0.add_argument("input", help="本地文件路径或分享链接")
    p0.add_argument("-o", "--output", default=None, help="各步骤输出文件名前缀")
    p0.add_argument("-s", "--final-style", default="A", choices=["A", "B", "C"], help="报告3.0风格")
    p0.add_argument("-p", "--provider", choices=["kimi", "gemini", "grok", "minimax", "glm", "qwen", "deepseek", "openai", "perplexity", "claude"], help="指定 LLM Provider（覆盖 .env 中的 LLM_PROVIDER）")
    _add_report_type_arg(p0)
    p0.set_defaults(func=cmd_all)

    p0b = sub.add_parser("all-v3", help="全流程：fetch → report-v3（按章节分段，篇幅充足）")
    subparsers_map["all-v3"] = p0b
    p0b.add_argument("input", help="分享链接或本地文件路径")
    p0b.add_argument("-o", "--output", default=None, help="各步骤输出文件名前缀")
    p0b.set_defaults(func=cmd_all_v3)

    p0c = sub.add_parser("all-context", help="全流程（多轮对话）：fetch → 多轮会话 → 报告1.0 → 专家 → 报告2.0")
    subparsers_map["all-context"] = p0c
    p0c.add_argument("input", help="本地文件或分享链接")
    p0c.add_argument("-o", "--output", default=None, help="各步骤输出文件名前缀")
    p0c.set_defaults(func=cmd_all_context)

    pfr = sub.add_parser("full-report", help="全流程：Step0→Step8，输出 1.0~5.0")
    subparsers_map["full-report"] = pfr
    pfr.add_argument("input", help="语料目录或单文件路径")
    pfr.add_argument("-o", "--output-base", default=None, help="输出文件名前缀")
    pfr.add_argument("-p", "--provider", default=None, choices=["kimi", "gemini", "grok", "minimax", "glm", "qwen", "deepseek", "openai", "perplexity", "claude"], help="指定 LLM Provider（默认跟随 LLM_PROVIDER 环境变量）")
    pfr.add_argument("-r", "--recursive", action="store_true", help="语料目录递归读取")
    pfr.add_argument("--policy", default="policy1", help="Step7/Step8 使用的 skill 子目录")
    _add_report_type_arg(pfr)
    pfr.add_argument("-s", "--style", default="A", choices=["A", "B", "C"], help="报告3.0风格")
    pfr.set_defaults(func=cmd_full_report)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        return
    if args.command == "help-all":
        args._root_parser = parser
        args._subparsers_map = subparsers_map
    args.func(args)


if __name__ == "__main__":
    main()
