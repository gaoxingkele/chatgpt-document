# -*- coding: utf-8 -*-
"""统一时间戳日志：替代各 step 文件中重复定义的 _log()。"""
import time


def log(msg: str, api_call: str = ""):
    """带时间戳的控制台日志。api_call 非空时额外标注 API 调用编号。"""
    ts = time.strftime("%H:%M:%S", time.localtime())
    prefix = f"[{ts}] [API#{api_call}] " if api_call else f"[{ts}] "
    print(prefix + msg, flush=True)
