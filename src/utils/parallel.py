# -*- coding: utf-8 -*-
"""轻量并行执行工具。"""
from concurrent.futures import ThreadPoolExecutor, as_completed


def parallel_map(fn, items, max_workers=4):
    """
    并行处理 items 列表，按原始顺序返回结果。
    fn(idx, item) → result，idx 为在 items 中的下标。
    """
    n = len(items)
    results = [None] * n
    with ThreadPoolExecutor(max_workers=min(n, max_workers)) as executor:
        futures = {executor.submit(fn, i, item): i for i, item in enumerate(items)}
        for future in as_completed(futures):
            i = futures[future]
            results[i] = future.result()
    return results
