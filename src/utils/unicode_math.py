# -*- coding: utf-8 -*-
"""
Unicode 数学字符 → LaTeX 转换工具。

ChatGPT 分享页面等场景中，公式不以 KaTeX/MathJax HTML 呈现，
而是直接使用 Unicode 数学字符（U+1D400-1D7FF 等）。
本模块检测这些字符序列并还原为 LaTeX $...$ 标记。
"""
import re
import unicodedata

# ── Unicode 数学字母 → ASCII 映射 ──────────────────────────────────
# 覆盖 Mathematical Italic, Bold, Bold Italic, Script, Fraktur, etc.

_MATH_CHAR_MAP: dict[int, str] = {}


def _register_range(start_cp: int, ascii_start: str, count: int):
    """注册一段连续的 Unicode 数学字符映射。"""
    base = ord(ascii_start)
    for i in range(count):
        _MATH_CHAR_MAP[start_cp + i] = chr(base + i)


# Mathematical Italic Capital A-Z (U+1D434-1D44D), Small a-z (U+1D44E-1D467)
# 注意: h 在 U+210E (ℎ) 而非连续区段
_register_range(0x1D434, "A", 26)
_register_range(0x1D44E, "a", 26)
_MATH_CHAR_MAP[0x210E] = "h"  # PLANCK CONSTANT = italic h

# Mathematical Bold Capital/Small
_register_range(0x1D400, "A", 26)
_register_range(0x1D41A, "a", 26)

# Mathematical Bold Italic Capital/Small
_register_range(0x1D468, "A", 26)
_register_range(0x1D482, "a", 26)

# Mathematical Sans-Serif Capital/Small
_register_range(0x1D5A0, "A", 26)
_register_range(0x1D5BA, "a", 26)

# Mathematical Sans-Serif Bold Capital/Small
_register_range(0x1D5D4, "A", 26)
_register_range(0x1D5EE, "a", 26)

# Mathematical Sans-Serif Italic Capital/Small
_register_range(0x1D608, "A", 26)
_register_range(0x1D622, "a", 26)

# Mathematical Monospace Capital/Small
_register_range(0x1D670, "A", 26)
_register_range(0x1D68A, "a", 26)

# Mathematical Script Capital/Small
_register_range(0x1D49C, "A", 26)
_register_range(0x1D4B6, "a", 26)

# Mathematical Fraktur Capital/Small
_register_range(0x1D504, "A", 26)
_register_range(0x1D51E, "a", 26)

# Mathematical Double-Struck Capital/Small
_register_range(0x1D538, "A", 26)
_register_range(0x1D552, "a", 26)

# Mathematical Bold/Italic digits 0-9
_register_range(0x1D7CE, "0", 10)  # Bold
_register_range(0x1D7D8, "0", 10)  # Double-struck
_register_range(0x1D7E2, "0", 10)  # Sans-serif
_register_range(0x1D7EC, "0", 10)  # Sans-serif bold
_register_range(0x1D7F6, "0", 10)  # Monospace

# Greek letters (Mathematical Italic)
_GREEK_ITALIC_MAP = {
    0x1D6E2: r"\Alpha", 0x1D6E3: r"\Beta", 0x1D6E4: r"\Gamma",
    0x1D6E5: r"\Delta", 0x1D6E6: r"\Epsilon", 0x1D6E7: r"\Zeta",
    0x1D6E8: r"\Eta", 0x1D6E9: r"\Theta", 0x1D6EA: r"\Iota",
    0x1D6EB: r"\Kappa", 0x1D6EC: r"\Lambda", 0x1D6ED: r"\Mu",
    0x1D6EE: r"\Nu", 0x1D6EF: r"\Xi", 0x1D6F0: r"\Omicron",
    0x1D6F1: r"\Pi", 0x1D6F2: r"\Rho", 0x1D6F4: r"\Sigma",
    0x1D6F5: r"\Tau", 0x1D6F6: r"\Upsilon", 0x1D6F7: r"\Phi",
    0x1D6F8: r"\Chi", 0x1D6F9: r"\Psi", 0x1D6FA: r"\Omega",
    # Lowercase
    0x1D6FC: r"\alpha", 0x1D6FD: r"\beta", 0x1D6FE: r"\gamma",
    0x1D6FF: r"\delta", 0x1D700: r"\epsilon", 0x1D701: r"\zeta",
    0x1D702: r"\eta", 0x1D703: r"\theta", 0x1D704: r"\iota",
    0x1D705: r"\kappa", 0x1D706: r"\lambda", 0x1D707: r"\mu",
    0x1D708: r"\nu", 0x1D709: r"\xi", 0x1D70A: r"o",
    0x1D70B: r"\pi", 0x1D70C: r"\rho", 0x1D70E: r"\sigma",
    0x1D70F: r"\tau", 0x1D710: r"\upsilon", 0x1D711: r"\phi",
    0x1D712: r"\chi", 0x1D713: r"\psi", 0x1D714: r"\omega",
}
_MATH_CHAR_MAP.update(_GREEK_ITALIC_MAP)

# Common Unicode symbols → LaTeX
_SYMBOL_MAP = {
    "×": r"\times",
    "÷": r"\div",
    "±": r"\pm",
    "∓": r"\mp",
    "·": r"\cdot",
    "∞": r"\infty",
    "≈": r"\approx",
    "≠": r"\neq",
    "≤": r"\leq",
    "≥": r"\geq",
    "∈": r"\in",
    "∉": r"\notin",
    "⊂": r"\subset",
    "⊃": r"\supset",
    "⊆": r"\subseteq",
    "⊇": r"\supseteq",
    "∪": r"\cup",
    "∩": r"\cap",
    "∅": r"\emptyset",
    "∀": r"\forall",
    "∃": r"\exists",
    "∄": r"\nexists",
    "→": r"\to",
    "←": r"\leftarrow",
    "↔": r"\leftrightarrow",
    "⇒": r"\Rightarrow",
    "⇐": r"\Leftarrow",
    "⇔": r"\Leftrightarrow",
    "∑": r"\sum",
    "∏": r"\prod",
    "∫": r"\int",
    "∂": r"\partial",
    "∇": r"\nabla",
    "√": r"\sqrt",
    "∝": r"\propto",
    "∧": r"\wedge",
    "∨": r"\vee",
    "¬": r"\neg",
    "∣": r"\mid",
    "⟨": r"\langle",
    "⟩": r"\rangle",
    "⌊": r"\lfloor",
    "⌋": r"\rfloor",
    "⌈": r"\lceil",
    "⌉": r"\rceil",
    "ℝ": r"\mathbb{R}",
    "ℕ": r"\mathbb{N}",
    "ℤ": r"\mathbb{Z}",
    "ℚ": r"\mathbb{Q}",
    "ℂ": r"\mathbb{C}",
    "′": "'",
    "″": "''",
    "‴": "'''",
    # Subscript/superscript digits
    "⁰": "^{0}", "¹": "^{1}", "²": "^{2}", "³": "^{3}",
    "⁴": "^{4}", "⁵": "^{5}", "⁶": "^{6}", "⁷": "^{7}",
    "⁸": "^{8}", "⁹": "^{9}",
    "₀": "_{0}", "₁": "_{1}", "₂": "_{2}", "₃": "_{3}",
    "₄": "_{4}", "₅": "_{5}", "₆": "_{6}", "₇": "_{7}",
    "₈": "_{8}", "₉": "_{9}",
    "ₐ": "_{a}", "ₑ": "_{e}", "ₕ": "_{h}", "ᵢ": "_{i}",
    "ⱼ": "_{j}", "ₖ": "_{k}", "ₗ": "_{l}", "ₘ": "_{m}",
    "ₙ": "_{n}", "ₒ": "_{o}", "ₚ": "_{p}", "ᵣ": "_{r}",
    "ₛ": "_{s}", "ₜ": "_{t}", "ᵤ": "_{u}", "ᵥ": "_{v}",
    "ₓ": "_{x}",
}

# Build code-point based symbol map for faster lookup
_SYMBOL_CP_MAP: dict[int, str] = {ord(k): v for k, v in _SYMBOL_MAP.items()}


def is_math_unicode(ch: str) -> bool:
    """判断单个字符是否为 Unicode 数学字符。"""
    cp = ord(ch)
    if cp in _MATH_CHAR_MAP:
        return True
    if cp in _SYMBOL_CP_MAP:
        return True
    # 检查是否在数学字母数字块 (U+1D400-1D7FF)
    if 0x1D400 <= cp <= 0x1D7FF:
        return True
    return False


def _char_to_latex(ch: str) -> str:
    """将单个 Unicode 数学字符转为 LaTeX 片段。"""
    cp = ord(ch)
    if cp in _MATH_CHAR_MAP:
        return _MATH_CHAR_MAP[cp]
    if cp in _SYMBOL_CP_MAP:
        return _SYMBOL_CP_MAP[cp]
    # 未映射的数学块字符，尝试 unicodedata
    name = unicodedata.name(ch, "")
    if name:
        # 提取字母部分
        for prefix in ("MATHEMATICAL ITALIC SMALL ", "MATHEMATICAL ITALIC CAPITAL ",
                        "MATHEMATICAL BOLD SMALL ", "MATHEMATICAL BOLD CAPITAL "):
            if name.startswith(prefix):
                letter = name[len(prefix):]
                if len(letter) == 1:
                    return letter
    return ch


def count_math_unicode(text: str) -> int:
    """统计文本中 Unicode 数学字符数量。"""
    return sum(1 for ch in text if is_math_unicode(ch))


def _is_math_context_char(ch: str) -> bool:
    """判断字符是否属于数学上下文（数学 Unicode、运算符、数字、括号等）。"""
    if is_math_unicode(ch):
        return True
    # 普通 ASCII 数字和运算符
    if ch in "0123456789+-*/=()[]{}^_.,;:<>!|&~":
        return True
    # 普通 ASCII 字母在数学上下文中的空格分隔
    if ch == " ":
        return False  # 空格需要特殊处理
    return False


def _extract_math_spans(text: str) -> list[tuple[int, int]]:
    """
    找出文本中包含 Unicode 数学字符的连续片段的起止位置。
    策略：找到数学字符，向两侧扩展到包含相邻的运算符、数字、括号、空格、换行。
    ChatGPT 分享页面中，每个数学符号可能独占一行（如 𝑃\\n(\\n𝑌\\n∣\\n...），
    因此需要跨换行符扩展。合并相邻片段。
    """
    # 可在数学上下文中出现的 ASCII 字符
    _MATH_CTX = set("0123456789+-*/=()[]{}^_.,;:<>!|&~\\≤≥≠≈≪≫∣")

    n = len(text)
    if n == 0:
        return []

    # 标记包含数学字符的位置
    math_positions = set()
    for i, ch in enumerate(text):
        if is_math_unicode(ch):
            math_positions.add(i)

    if not math_positions:
        return []

    def _is_ctx(ch: str) -> bool:
        return is_math_unicode(ch) or ch in _MATH_CTX

    def _peek_forward(idx: int, limit: int = 3) -> bool:
        """从 idx 往后最多看 limit 个空白字符，判断之后是否有数学上下文。"""
        j = idx
        while j < n and j - idx < limit and text[j] in " \n\r\t":
            j += 1
        return j < n and _is_ctx(text[j])

    def _peek_backward(idx: int, limit: int = 3) -> bool:
        """从 idx 往前最多看 limit 个空白字符，判断之前是否有数学上下文。"""
        j = idx
        while j >= 0 and idx - j < limit and text[j] in " \n\r\t":
            j -= 1
        return j >= 0 and _is_ctx(text[j])

    # 从每个数学字符位置扩展到上下文边界
    spans = []
    visited = set()

    for pos in sorted(math_positions):
        if pos in visited:
            continue

        start = pos
        end = pos

        # 向左扩展
        i = pos - 1
        while i >= 0:
            ch = text[i]
            if _is_ctx(ch):
                start = i
                i -= 1
            elif ch in " \n\r\t" and _peek_backward(i - 1):
                start = i
                i -= 1
            elif ch in " \n\r\t" and i > 0 and _is_ctx(text[i - 1]):
                start = i
                i -= 1
            else:
                break

        # 向右扩展
        i = pos + 1
        while i < n:
            ch = text[i]
            if _is_ctx(ch):
                end = i
                i += 1
            elif ch in " \n\r\t" and _peek_forward(i + 1):
                end = i
                i += 1
            elif ch in " \n\r\t" and i + 1 < n and _is_ctx(text[i + 1]):
                end = i
                i += 1
            else:
                break

        for j in range(start, end + 1):
            visited.add(j)
        spans.append((start, end + 1))

    # 合并重叠/相邻的 span
    if not spans:
        return []
    spans.sort()
    merged = [spans[0]]
    for s, e in spans[1:]:
        ps, pe = merged[-1]
        if s <= pe + 1:  # 相邻或重叠
            merged[-1] = (ps, max(pe, e))
        else:
            merged.append((s, e))

    return merged


def _span_to_latex(text: str) -> str:
    """将一段包含 Unicode 数学字符的文本转换为 LaTeX 表达式。"""
    # 先将换行和多余空白折叠为单空格
    collapsed = re.sub(r"[\n\r\t ]+", " ", text).strip()

    parts = []
    i = 0
    while i < len(collapsed):
        ch = collapsed[i]

        # Unicode 数学字符
        if ord(ch) in _MATH_CHAR_MAP:
            parts.append(_MATH_CHAR_MAP[ord(ch)])
        elif ord(ch) in _SYMBOL_CP_MAP:
            latex_sym = _SYMBOL_CP_MAP[ord(ch)]
            # 运算符加空格
            if latex_sym.startswith("\\") and not latex_sym.startswith("\\mathbb"):
                parts.append(f" {latex_sym} ")
            else:
                parts.append(latex_sym)
        elif is_math_unicode(ch):
            parts.append(_char_to_latex(ch))
        else:
            # 普通字符直接保留
            parts.append(ch)
        i += 1

    result = "".join(parts)
    # 清理多余空格
    result = re.sub(r"  +", " ", result).strip()
    return result


def convert_unicode_math_to_latex(text: str, min_math_chars: int = 2) -> tuple[str, int]:
    """
    扫描文本，将 Unicode 数学字符序列替换为 $...$ 或 $$...$$ LaTeX 标记。

    参数:
        text: 输入文本
        min_math_chars: 一个 span 中至少包含多少个数学字符才转换（避免误识别）

    返回:
        (转换后的文本, 转换的公式数量)
    """
    spans = _extract_math_spans(text)
    if not spans:
        return text, 0

    formula_count = 0
    result_parts = []
    last_end = 0

    for start, end in spans:
        span_text = text[start:end]
        # 统计此 span 中的数学字符数
        math_count = sum(1 for ch in span_text if is_math_unicode(ch))
        if math_count < min_math_chars:
            # 太少，可能是误识别，保持原样
            result_parts.append(text[last_end:end])
            last_end = end
            continue

        # 前缀（非数学部分）
        result_parts.append(text[last_end:start])

        # 转换
        latex = _span_to_latex(span_text)

        # 判断是 inline 还是 display：如果整行只有这个公式，用 display
        line_start = text.rfind("\n", 0, start) + 1
        line_end = text.find("\n", end)
        if line_end < 0:
            line_end = len(text)
        line_text = text[line_start:line_end].strip()
        is_display = (line_text == span_text.strip())

        if is_display and len(latex) > 10:
            result_parts.append(f"\n$$\n{latex}\n$$\n")
        else:
            result_parts.append(f"${latex}$")

        formula_count += 1
        last_end = end

    result_parts.append(text[last_end:])
    return "".join(result_parts), formula_count
