# -*- coding: utf-8 -*-
"""
语料包(CorpusPackage)：目录格式的富语料存储。
当爬虫/提取器检测到图片或公式时，用语料包替代单一 .txt 文件，
保留图片资产和 Markdown 格式的正文。

结构:
    output/raw/{name}/
        corpus.md        # 正文，含 ![img](assets/img_001.png) 和 $latex$ 占位符
        manifest.json    # 元数据：来源 URL、时间戳、资产列表
        assets/          # 下载的图片
"""
import json
import time
from pathlib import Path
from typing import List, Optional


class CorpusPackage:
    """目录格式语料包的读写操作。"""

    CORPUS_FILE = "corpus.md"
    MANIFEST_FILE = "manifest.json"
    ASSETS_DIR = "assets"

    def __init__(self, pkg_dir: Path):
        self.pkg_dir = Path(pkg_dir)
        self.assets_dir = self.pkg_dir / self.ASSETS_DIR
        self._asset_counter = 0

    @classmethod
    def create(
        cls,
        pkg_dir: Path,
        content: str,
        source: str = "",
        assets: Optional[List[dict]] = None,
    ) -> "CorpusPackage":
        """创建语料包目录并写入初始内容。"""
        pkg = cls(pkg_dir)
        pkg.pkg_dir.mkdir(parents=True, exist_ok=True)
        pkg.assets_dir.mkdir(exist_ok=True)

        # 写入正文
        (pkg.pkg_dir / cls.CORPUS_FILE).write_text(content, encoding="utf-8")

        # 写入清单
        manifest = {
            "source": source,
            "created": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "assets": assets or [],
        }
        (pkg.pkg_dir / cls.MANIFEST_FILE).write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return pkg

    def read_corpus(self, max_chars: int = 0) -> str:
        """读取正文，可选截断。"""
        corpus_path = self.pkg_dir / self.CORPUS_FILE
        if not corpus_path.is_file():
            return ""
        text = corpus_path.read_text(encoding="utf-8", errors="replace")
        if max_chars and len(text) > max_chars:
            text = text[:max_chars] + f"\n\n[内容已截断，仅保留前 {max_chars} 字]"
        return text

    def add_asset(self, data: bytes, filename: str) -> Path:
        """保存二进制资产到 assets/ 目录，返回保存路径。"""
        self.assets_dir.mkdir(exist_ok=True)
        out = self.assets_dir / filename
        out.write_bytes(data)
        self.update_manifest_assets()
        return out

    def next_asset_name(self, ext: str = ".png") -> str:
        """生成下一个自增资产文件名，如 img_001.png。"""
        self._asset_counter += 1
        return f"img_{self._asset_counter:03d}{ext}"

    def update_manifest_assets(self):
        """根据 assets/ 目录实际文件更新清单中的资产列表。"""
        manifest_path = self.pkg_dir / self.MANIFEST_FILE
        if manifest_path.is_file():
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        else:
            manifest = {"source": "", "created": time.strftime("%Y-%m-%dT%H:%M:%S")}

        asset_files = sorted(self.assets_dir.iterdir()) if self.assets_dir.is_dir() else []
        manifest["assets"] = [f.name for f in asset_files if f.is_file()]
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
        )


def is_corpus_package(path: Path) -> bool:
    """判断路径是否为有效语料包目录（含 corpus.md）。"""
    if path is None:
        return False
    p = Path(path)
    return p.is_dir() and (p / CorpusPackage.CORPUS_FILE).is_file()


def load_corpus_content(raw_path: Path, max_chars: int = 130_000) -> str:
    """
    统一加载语料：自动识别 .txt 文件或语料包目录。
    - raw_path 为 None 或不存在 → 返回空串
    - 是语料包目录 → 读取 corpus.md
    - 是文件 → 读取文本
    """
    if not raw_path:
        return ""
    p = Path(raw_path)

    # 语料包目录
    if is_corpus_package(p):
        return CorpusPackage(p).read_corpus(max_chars)

    # 普通文件
    if p.is_file():
        text = p.read_text(encoding="utf-8", errors="replace")
        if max_chars and len(text) > max_chars:
            text = text[:max_chars] + f"\n\n[内容已截断，仅保留前 {max_chars} 字]"
        return text

    return ""
