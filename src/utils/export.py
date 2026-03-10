# -*- coding: utf-8 -*-
"""多格式导出：Markdown → HTML / PDF / DOCX。"""
from pathlib import Path

from src.utils.log import log as _log


def export_to_html(md_text: str, output_path: Path) -> Path:
    """Markdown → HTML（使用 markdown 库，内嵌 CSS 样式）。"""
    try:
        import markdown
    except ImportError:
        raise ImportError("需要安装 markdown 库: pip install markdown")

    html_body = markdown.markdown(
        md_text,
        extensions=["tables", "fenced_code", "toc"],
    )

    css = """
    <style>
    body { font-family: 'Segoe UI', '宋体', sans-serif; max-width: 900px; margin: 0 auto; padding: 20px; line-height: 1.8; color: #333; }
    h1 { color: #1a1a1a; border-bottom: 2px solid #333; padding-bottom: 8px; }
    h2 { color: #2c3e50; border-bottom: 1px solid #ddd; padding-bottom: 6px; }
    h3 { color: #34495e; }
    table { border-collapse: collapse; width: 100%; margin: 16px 0; }
    th, td { border: 1px solid #ddd; padding: 8px 12px; text-align: left; }
    th { background: #f5f5f5; font-weight: bold; }
    blockquote { border-left: 4px solid #3498db; margin: 16px 0; padding: 8px 16px; background: #f8f9fa; color: #555; }
    code { background: #f0f0f0; padding: 2px 6px; border-radius: 3px; font-size: 0.9em; }
    pre { background: #f0f0f0; padding: 16px; border-radius: 4px; overflow-x: auto; }
    hr { border: none; border-top: 1px solid #ddd; margin: 24px 0; }
    </style>
    """

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Report</title>
{css}
</head>
<body>
{html_body}
</body>
</html>"""

    output_path = Path(output_path)
    output_path.write_text(html, encoding="utf-8")
    _log(f"HTML 导出完成: {output_path.name}")
    return output_path


def export_to_pdf(source_path: Path, output_path: Path, method: str = "auto") -> Path:
    """
    导出 PDF。

    method:
        "docx2pdf" - 通过 Word 转换（仅 Windows/macOS，需安装 Word）
        "weasyprint" - 通过 WeasyPrint（跨平台，需安装 weasyprint）
        "auto" - 自动选择可用方式
    """
    source_path = Path(source_path)
    output_path = Path(output_path)

    if method in ("docx2pdf", "auto"):
        try:
            import docx2pdf
            # 需要 .docx 源文件
            if source_path.suffix.lower() == ".docx":
                docx2pdf.convert(str(source_path), str(output_path))
                _log(f"PDF 导出完成（docx2pdf）: {output_path.name}")
                return output_path
        except (ImportError, Exception) as e:
            if method == "docx2pdf":
                raise
            _log(f"docx2pdf 不可用: {e}")

    if method in ("weasyprint", "auto"):
        try:
            import weasyprint
            # 需要 .html 源文件
            if source_path.suffix.lower() == ".html":
                doc = weasyprint.HTML(filename=str(source_path))
                doc.write_pdf(str(output_path))
                _log(f"PDF 导出完成（weasyprint）: {output_path.name}")
                return output_path
        except (ImportError, Exception) as e:
            if method == "weasyprint":
                raise
            _log(f"weasyprint 不可用: {e}")

    _log("[警告] 无可用 PDF 导出方式，请安装 docx2pdf 或 weasyprint")
    return output_path


def export_report(md_text: str, base_path: Path, formats: list[str]) -> dict[str, Path]:
    """
    统一导出入口。

    参数:
        md_text: Markdown 文本
        base_path: 输出基础路径（不含扩展名），如 output/reports/test
        formats: 格式列表，如 ["md", "docx", "html", "pdf"]

    返回: {"md": Path, "docx": Path, "html": Path, "pdf": Path, ...}
    """
    base_path = Path(base_path)
    results = {}

    if "md" in formats or "all" in formats:
        md_path = base_path.with_suffix(".md")
        md_path.write_text(md_text, encoding="utf-8")
        results["md"] = md_path
        _log(f"Markdown 导出完成: {md_path.name}")

    if "docx" in formats or "all" in formats:
        from src.utils.docx_utils import save_docx_safe
        docx_path = save_docx_safe(md_text, base_path.with_suffix(".docx"))
        results["docx"] = docx_path

    if "html" in formats or "all" in formats:
        html_path = export_to_html(md_text, base_path.with_suffix(".html"))
        results["html"] = html_path

    if "pdf" in formats or "all" in formats:
        pdf_path = base_path.with_suffix(".pdf")
        # 优先从 docx 转，否则从 html 转
        source = results.get("docx", results.get("html"))
        if source and Path(source).is_file():
            try:
                export_to_pdf(source, pdf_path)
                results["pdf"] = pdf_path
            except Exception as e:
                _log(f"[警告] PDF 导出失败: {e}")
        else:
            # 先生成 html 再转 pdf
            html_path = base_path.with_suffix(".html")
            if not html_path.is_file():
                export_to_html(md_text, html_path)
            try:
                export_to_pdf(html_path, pdf_path)
                results["pdf"] = pdf_path
            except Exception as e:
                _log(f"[警告] PDF 导出失败: {e}")

    return results
