# -*- coding: utf-8 -*-
"""
Step0: 批量语料重整。
读取指定目录下所有语料文件，调用云端大模型 API 进行去重、排序，输出合成本地语料文件。
供后续 1.0、2.0、3.0 文档流程使用。
支持从 DOCX/PDF 提取嵌入图片，有图片时输出语料包目录格式。
"""
import time
from pathlib import Path
from typing import List, Tuple

import src  # noqa: F401  — 确保 PROJECT_ROOT 加入 sys.path

from config import RAW_DIR, CORPUS_EXTENSIONS
from src.llm_client import chat
from src.ingest.file_importer import import_from_file
from src.corpus_extractors import (
    extract_from_docx_rich, extract_from_pdf_rich, extract_from_image,
)
# 单次 API 传入最大字符数（超长则分批处理）
MAX_CHARS_PER_CALL = 100000


from src.utils.log import log as _log


def _read_file_content(f: Path, _log_fn) -> Tuple[str, List[dict]]:
    """
    根据文件类型读取内容，返回 (text, images)。
    Word/PDF 返回富提取结果（含图片），其他格式返回 (text, [])。
    """
    suffix = f.suffix.lower()
    if suffix in {".txt", ".md", ".json", ".html"}:
        return import_from_file(f), []
    if suffix == ".docx":
        result = extract_from_docx_rich(f)
        return result.text, result.images
    if suffix == ".pdf":
        result = extract_from_pdf_rich(f)
        return result.text, result.images
    if suffix in {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}:
        _log_fn(f"  [Vision API] 提交图片 {f.name} 至云端处理...")
        return extract_from_image(f), []
    return import_from_file(f), []


def _read_corpus_from_dir(
    dir_path: Path, recursive: bool = False, _log_fn=None
) -> List[Tuple[str, str, List[dict]]]:
    """
    读取目录下所有语料文件，返回 [(文件名, 内容, 图片列表), ...]。
    recursive: 是否递归子目录。
    """
    _log_fn = _log_fn or _log
    dir_path = Path(dir_path)
    if not dir_path.is_dir():
        raise NotADirectoryError(f"目录不存在或不是目录: {dir_path}")

    files: List[Path] = []
    if recursive:
        for ext in CORPUS_EXTENSIONS:
            files.extend(dir_path.rglob(f"*{ext}"))
    else:
        for ext in CORPUS_EXTENSIONS:
            files.extend(dir_path.glob(f"*{ext}"))
    files = sorted(set(files), key=lambda p: p.name)

    results: List[Tuple[str, str, List[dict]]] = []
    for f in files:
        if not f.is_file():
            continue
        try:
            content, images = _read_file_content(f, _log_fn)
            if content and content.strip():
                results.append((f.name, content, images))
        except Exception as e:
            _log_fn(f"[警告] 跳过 {f.name}: {e}")
    return results


def _api_reorganize_corpus(combined: str, total_chars: int) -> str:
    """调用 API 对语料进行去重、排序。"""
    prompt = f"""请对以下多份语料进行**重整**，输出整理后的完整语料文本。

【任务】
1. **去重**：删除重复表述、重复案例、重复数据、重复观点。同一内容多处出现时保留一处最完整的表述。
2. **排序**：按逻辑顺序、主题顺序或时间顺序合理组织，使阅读连贯、结构清晰。
3. **保留**：所有有效信息须保留，仅做去重与重组，不得删减有价值内容。

【要求】
- 直接输出重整后的完整语料，不要 JSON 或多余说明。
- 若原文有对话格式（用户/助手），可保留或合并为连贯叙述，视内容而定。
- 保持专业、可读。
- 保留图片占位符 ![image](assets/...) 和公式标记 $...$、$$...$$，不要修改或删除。

【语料原文】（共约 {total_chars} 字）
---
{combined[:MAX_CHARS_PER_CALL]}
---
请输出重整后的完整语料。"""

    if len(combined) > MAX_CHARS_PER_CALL:
        prompt += f"\n\n（注：原文已截断至前 {MAX_CHARS_PER_CALL} 字，请对截断部分进行重整；超出部分将在后续步骤中保留。）"

    resp = chat(
        [
            {
                "role": "system",
                "content": "你是专业的语料整理专家。任务：对多份语料进行去重与排序，输出结构清晰、无重复的完整语料。直接输出正文，不要 JSON 或说明。",
            },
            {"role": "user", "content": prompt},
        ],
        max_tokens=32768,
        temperature=0.3,
    )
    return resp.strip()


def _remap_image_filenames(items: List[Tuple[str, str, List[dict]]]) -> Tuple[List[Tuple[str, str, List[dict]]], int]:
    """
    重新编号所有文件的图片，避免跨文件文件名冲突。
    返回更新后的 items 和总图片数。
    """
    global_counter = 0
    remapped = []
    for name, content, images in items:
        new_images = []
        new_content = content
        for img in images:
            global_counter += 1
            old_filename = img["filename"]
            ext = Path(old_filename).suffix
            new_filename = f"img_{global_counter:03d}{ext}"
            new_content = new_content.replace(
                f"assets/{old_filename}", f"assets/{new_filename}"
            )
            new_images.append({**img, "filename": new_filename})
        remapped.append((name, new_content, new_images))
    return remapped, global_counter


def run_corpus_merge(
    dir_path: Path,
    output_name: str,
    recursive: bool = False,
) -> Path:
    """
    读取目录下所有语料文件，经 API 去重排序后，合成为本地语料文件。
    有图片时输出语料包目录 output/raw/{output_name}/，否则输出 .txt。
    返回保存路径。
    """
    dir_path = Path(dir_path)
    output_name = output_name or dir_path.name
    if not output_name:
        output_name = "merged"

    _log("=" * 60)
    _log("Step0 语料重整：开始")
    _log(f"目录: {dir_path}")
    _log(f"递归: {recursive}")
    _log("=" * 60)

    items = _read_corpus_from_dir(dir_path, recursive)
    if not items:
        raise ValueError(
            "目录下未找到可读的语料文件。支持格式: "
            "文本(.txt .md .json .html)、Word(.docx)、PDF(.pdf)、图片(.jpg .png .gif .webp .bmp)"
        )

    _log(f"共读取 {len(items)} 个文件")
    for name, content, images in items:
        img_info = f"，{len(images)} 张图片" if images else ""
        _log(f"  - {name}: 约 {len(content)} 字{img_info}")

    # 重新编号图片
    all_images_exist = any(imgs for _, _, imgs in items)
    if all_images_exist:
        items, total_images = _remap_image_filenames(items)
        _log(f"共检测到 {total_images} 张嵌入图片")

    # 拼接：文件之间加分隔
    text_parts: List[str] = []
    for name, content, _ in items:
        text_parts.append(f"--- 来自文件: {name} ---\n\n{content}")
    combined = "\n\n".join(text_parts)
    total_chars = len(combined)

    _log(f"合并后约 {total_chars} 字，调用 API 进行去重与排序...")
    t0 = time.time()

    reorganized = _api_reorganize_corpus(combined, total_chars)

    if total_chars > MAX_CHARS_PER_CALL:
        reorganized += "\n\n[以下为超出 API 单次处理上限的原文，未参与去重排序]\n\n"
        reorganized += combined[MAX_CHARS_PER_CALL:]

    _log(f"API 完成，耗时 {time.time()-t0:.1f}s，重整后约 {len(reorganized)} 字")

    # 收集所有图片数据
    all_images = []
    for _, _, images in items:
        all_images.extend(images)

    if all_images:
        # 输出语料包
        from src.corpus_package import CorpusPackage
        pkg_dir = RAW_DIR / output_name
        pkg = CorpusPackage.create(pkg_dir, reorganized, source=str(dir_path))
        for img in all_images:
            if img.get("data"):
                pkg.add_asset(img["data"], img["filename"])
        out_path = pkg_dir
        _log(f"已保存语料包: {out_path}（含 {len(all_images)} 张图片）")
    else:
        out_path = RAW_DIR / f"{output_name}.txt"
        out_path.write_text(reorganized, encoding="utf-8")
        _log(f"已保存: {out_path}")

    _log("=" * 60)
    return out_path
