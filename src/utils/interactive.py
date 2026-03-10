# -*- coding: utf-8 -*-
"""交互式审阅：在 pipeline 关键节点暂停，等待用户确认或编辑。"""
import sys


def prompt_user_confirmation(
    message: str,
    detail: str = "",
    allow_edit: bool = False,
) -> tuple[bool, str | None]:
    """
    在终端中提示用户确认。

    参数:
        message: 提示信息
        detail: 详细内容（显示在提示前）
        allow_edit: 是否允许用户输入编辑内容

    返回:
        (confirmed: bool, edited_text: str | None)
        - confirmed=True 表示用户确认/通过
        - edited_text 仅在 allow_edit=True 且用户选择编辑时返回新文本
    """
    if not sys.stdin.isatty():
        # 非交互模式，自动通过
        return True, None

    if detail:
        print("\n" + "=" * 60)
        print(detail[:2000])  # 限制显示长度
        print("=" * 60)

    if allow_edit:
        prompt_text = f"\n{message}\n  [y] 确认  [n] 跳过  [e] 编辑  > "
    else:
        prompt_text = f"\n{message}\n  [y] 确认  [n] 跳过  > "

    while True:
        try:
            choice = input(prompt_text).strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            return False, None

        if choice in ("y", "yes", ""):
            return True, None
        if choice in ("n", "no"):
            return False, None
        if allow_edit and choice in ("e", "edit"):
            print("请输入新内容（输入空行结束）：")
            lines = []
            while True:
                try:
                    line = input()
                    if line == "":
                        break
                    lines.append(line)
                except (EOFError, KeyboardInterrupt):
                    break
            edited = "\n".join(lines)
            return True, edited if edited.strip() else None
        print("  无效输入，请输入 y/n" + ("/e" if allow_edit else ""))
