# -*- coding: utf-8 -*-
"""src 包初始化：统一设置项目根目录到 sys.path，供所有子模块 import config。"""
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
