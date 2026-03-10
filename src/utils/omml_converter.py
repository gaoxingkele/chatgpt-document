# -*- coding: utf-8 -*-
"""
OMML ↔ LaTeX 双向转换器。
- omml_to_latex(): Word 文档中 <m:oMath> → LaTeX 字符串
- latex_to_omml(): LaTeX 字符串 → <m:oMath> XML 元素（用于写入 DOCX）
"""
from lxml import etree

OMML_NS = "http://schemas.openxmlformats.org/officeDocument/2006/math"
_ns = {"m": OMML_NS}


def _text(el) -> str:
    """提取 m:t 文本节点内容。"""
    parts = []
    for t in el.iter(f"{{{OMML_NS}}}t"):
        if t.text:
            parts.append(t.text)
    return "".join(parts)


def _child(el, local_name: str):
    """查找直接子元素。"""
    return el.find(f"m:{local_name}", _ns)


def _convert(el) -> str:
    """递归将 OMML 元素转换为 LaTeX。"""
    if el is None:
        return ""

    tag = etree.QName(el.tag).localname if isinstance(el.tag, str) else ""

    # 文本 run
    if tag == "r":
        return _text(el)

    # m:t 直接文本
    if tag == "t":
        return el.text or ""

    # 分数 m:f → \frac{num}{den}
    if tag == "f":
        num = _convert_children(_child(el, "num"))
        den = _convert_children(_child(el, "den"))
        return f"\\frac{{{num}}}{{{den}}}"

    # 上标 m:sSup → base^{sup}
    if tag == "sSup":
        base = _convert_children(_child(el, "e"))
        sup = _convert_children(_child(el, "sup"))
        return f"{base}^{{{sup}}}"

    # 下标 m:sSub → base_{sub}
    if tag == "sSub":
        base = _convert_children(_child(el, "e"))
        sub = _convert_children(_child(el, "sub"))
        return f"{base}_{{{sub}}}"

    # 上下标 m:sSubSup → base_{sub}^{sup}
    if tag == "sSubSup":
        base = _convert_children(_child(el, "e"))
        sub = _convert_children(_child(el, "sub"))
        sup = _convert_children(_child(el, "sup"))
        return f"{base}_{{{sub}}}^{{{sup}}}"

    # 根号 m:rad → \sqrt[deg]{body} 或 \sqrt{body}
    if tag == "rad":
        deg = _convert_children(_child(el, "deg"))
        body = _convert_children(_child(el, "e"))
        if deg.strip():
            return f"\\sqrt[{deg}]{{{body}}}"
        return f"\\sqrt{{{body}}}"

    # 括号 m:d → \left( body \right)
    if tag == "d":
        # 获取括号字符
        dPr = _child(el, "dPr")
        beg_chr, end_chr = "(", ")"
        if dPr is not None:
            bc = dPr.find("m:begChr", _ns)
            ec = dPr.find("m:endChr", _ns)
            if bc is not None:
                beg_chr = bc.get(f"{{{OMML_NS}}}val", "(")
            if ec is not None:
                end_chr = ec.get(f"{{{OMML_NS}}}val", ")")
        body = _convert_children(_child(el, "e"))
        return f"\\left{beg_chr}{body}\\right{end_chr}"

    # N-ary 运算 m:nary → \sum, \int, \prod 等
    if tag == "nary":
        naryPr = _child(el, "naryPr")
        op = "\\int"
        if naryPr is not None:
            chr_el = naryPr.find("m:chr", _ns)
            if chr_el is not None:
                val = chr_el.get(f"{{{OMML_NS}}}val", "")
                op_map = {
                    "\u2211": "\\sum", "\u220f": "\\prod", "\u222b": "\\int",
                    "\u222c": "\\iint", "\u222d": "\\iiint", "\u222e": "\\oint",
                    "\u22c0": "\\bigwedge", "\u22c1": "\\bigvee",
                    "\u22c2": "\\bigcap", "\u22c3": "\\bigcup",
                }
                op = op_map.get(val, f"\\operatorname{{{val}}}" if val else "\\int")
        sub = _convert_children(_child(el, "sub"))
        sup = _convert_children(_child(el, "sup"))
        body = _convert_children(_child(el, "e"))
        result = op
        if sub:
            result += f"_{{{sub}}}"
        if sup:
            result += f"^{{{sup}}}"
        result += f" {body}"
        return result

    # 重音 m:acc → \hat, \tilde 等
    if tag == "acc":
        accPr = _child(el, "accPr")
        accent = "\\hat"
        if accPr is not None:
            chr_el = accPr.find("m:chr", _ns)
            if chr_el is not None:
                val = chr_el.get(f"{{{OMML_NS}}}val", "")
                acc_map = {
                    "\u0302": "\\hat", "\u0303": "\\tilde", "\u0304": "\\bar",
                    "\u0307": "\\dot", "\u0308": "\\ddot", "\u20d7": "\\vec",
                    "\u0305": "\\overline",
                }
                accent = acc_map.get(val, "\\hat")
        body = _convert_children(_child(el, "e"))
        return f"{accent}{{{body}}}"

    # 上划线 m:bar → \overline
    if tag == "bar":
        body = _convert_children(_child(el, "e"))
        return f"\\overline{{{body}}}"

    # 等式数组 m:eqArr
    if tag == "eqArr":
        rows = el.findall("m:e", _ns)
        inner = " \\\\ ".join(_convert_children(r) for r in rows)
        return f"\\begin{{aligned}} {inner} \\end{{aligned}}"

    # 矩阵 m:m
    if tag == "m" and el.tag == f"{{{OMML_NS}}}m":
        rows = el.findall("m:mr", _ns)
        row_strs = []
        for mr in rows:
            cells = mr.findall("m:e", _ns)
            row_strs.append(" & ".join(_convert_children(c) for c in cells))
        inner = " \\\\ ".join(row_strs)
        return f"\\begin{{matrix}} {inner} \\end{{matrix}}"

    # oMath 根元素
    if tag in ("oMath", "oMathPara"):
        return _convert_children(el)

    # 通用子元素：e, num, den, sub, sup, deg 等容器
    if tag in ("e", "num", "den", "sub", "sup", "deg", "lim"):
        return _convert_children(el)

    # 未知元素：递归子节点
    return _convert_children(el)


def _convert_children(el) -> str:
    """转换元素的所有子节点。"""
    if el is None:
        return ""
    return "".join(_convert(child) for child in el)


def omml_to_latex(omml_element) -> str:
    """
    将 OMML 元素（m:oMath 或 m:oMathPara）转换为 LaTeX 字符串。
    主入口函数。
    """
    return _convert(omml_element).strip()


# ============================================================
# LaTeX → OMML 反向转换器
# ============================================================

_M = OMML_NS  # 简写


def _omml_el(tag: str, **attribs) -> etree._Element:
    """创建 OMML 命名空间元素。"""
    el = etree.SubElement(etree.Element("_dummy"), f"{{{_M}}}{tag}")
    for k, v in attribs.items():
        el.set(f"{{{_M}}}{k}", v)
    return el


def _make_el(tag: str) -> etree._Element:
    """创建独立 OMML 元素。"""
    return etree.Element(f"{{{_M}}}{tag}")


def _make_run(text: str) -> etree._Element:
    """创建 m:r > m:t 文本 run。"""
    r = _make_el("r")
    t = etree.SubElement(r, f"{{{_M}}}t")
    # 过滤掉 XML 不兼容的控制字符（保留 tab/newline/cr）
    cleaned = "".join(
        ch for ch in text
        if ch in ("\t", "\n", "\r") or (ord(ch) >= 0x20)
    )
    t.text = cleaned
    return r


def _wrap_in_e(child) -> etree._Element:
    """用 m:e 包裹子元素。"""
    e = _make_el("e")
    if isinstance(child, str):
        e.append(_make_run(child))
    elif child is not None:
        e.append(child)
    return e


# LaTeX 命令 → Unicode 符号（用于 N-ary 等）
_LATEX_TO_UNICODE = {
    "sum": "\u2211", "prod": "\u220f", "int": "\u222b",
    "iint": "\u222c", "iiint": "\u222d", "oint": "\u222e",
    "bigcap": "\u22c2", "bigcup": "\u22c3",
    "bigwedge": "\u22c0", "bigvee": "\u22c1",
    "alpha": "\u03b1", "beta": "\u03b2", "gamma": "\u03b3",
    "delta": "\u03b4", "epsilon": "\u03b5", "zeta": "\u03b6",
    "eta": "\u03b7", "theta": "\u03b8", "iota": "\u03b9",
    "kappa": "\u03ba", "lambda": "\u03bb", "mu": "\u03bc",
    "nu": "\u03bd", "xi": "\u03be", "pi": "\u03c0",
    "rho": "\u03c1", "sigma": "\u03c3", "tau": "\u03c4",
    "upsilon": "\u03c5", "phi": "\u03c6", "chi": "\u03c7",
    "psi": "\u03c8", "omega": "\u03c9",
    "Alpha": "\u0391", "Beta": "\u0392", "Gamma": "\u0393",
    "Delta": "\u0394", "Theta": "\u0398", "Lambda": "\u039b",
    "Xi": "\u039e", "Pi": "\u03a0", "Sigma": "\u03a3",
    "Phi": "\u03a6", "Psi": "\u03a8", "Omega": "\u03a9",
    "infty": "\u221e", "partial": "\u2202", "nabla": "\u2207",
    "forall": "\u2200", "exists": "\u2203", "emptyset": "\u2205",
    "in": "\u2208", "notin": "\u2209", "subset": "\u2282",
    "supset": "\u2283", "cup": "\u222a", "cap": "\u2229",
    "pm": "\u00b1", "mp": "\u2213", "times": "\u00d7",
    "div": "\u00f7", "cdot": "\u22c5", "circ": "\u2218",
    "leq": "\u2264", "geq": "\u2265", "neq": "\u2260",
    "approx": "\u2248", "equiv": "\u2261", "sim": "\u223c",
    "to": "\u2192", "rightarrow": "\u2192", "leftarrow": "\u2190",
    "Rightarrow": "\u21d2", "Leftarrow": "\u21d0",
    "leftrightarrow": "\u2194", "Leftrightarrow": "\u21d4",
    "ldots": "\u2026", "cdots": "\u22ef", "vdots": "\u22ee",
    "ddots": "\u22f1",
}

# 重音命令 → Unicode 组合字符
_ACCENT_MAP = {
    "hat": "\u0302", "tilde": "\u0303", "bar": "\u0304",
    "overline": "\u0305", "dot": "\u0307", "ddot": "\u0308",
    "vec": "\u20d7",
}

# N-ary 运算集合
_NARY_OPS = {"sum", "prod", "int", "iint", "iiint", "oint",
             "bigcap", "bigcup", "bigwedge", "bigvee"}


class _LaTeXParser:
    """简单的 LaTeX 递归下降解析器 → OMML 元素。"""

    def __init__(self, latex: str):
        self.s = latex.strip()
        self.pos = 0

    def peek(self) -> str:
        if self.pos < len(self.s):
            return self.s[self.pos]
        return ""

    def advance(self) -> str:
        ch = self.s[self.pos]
        self.pos += 1
        return ch

    def skip_ws(self):
        while self.pos < len(self.s) and self.s[self.pos] in " \t\n\r":
            self.pos += 1

    def parse_group(self) -> str:
        """解析 {内容}，返回内容字符串。"""
        self.skip_ws()
        if self.peek() == "{":
            self.advance()
            depth = 1
            start = self.pos
            while self.pos < len(self.s) and depth > 0:
                ch = self.s[self.pos]
                if ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                self.pos += 1
            return self.s[start:self.pos - 1]
        # 单个 token
        if self.peek() == "\\":
            return self.parse_command_str()
        if self.pos < len(self.s):
            return self.advance()
        return ""

    def parse_command_str(self) -> str:
        """解析 \\command 返回原始字符串（含反斜杠）。"""
        start = self.pos
        self.advance()  # skip \\
        while self.pos < len(self.s) and self.s[self.pos].isalpha():
            self.pos += 1
        return self.s[start:self.pos]

    def parse_optional(self) -> str:
        """解析 [内容]，返回内容字符串或空串。"""
        self.skip_ws()
        if self.peek() == "[":
            self.advance()
            start = self.pos
            depth = 1
            while self.pos < len(self.s) and depth > 0:
                if self.s[self.pos] == "[":
                    depth += 1
                elif self.s[self.pos] == "]":
                    depth -= 1
                self.pos += 1
            return self.s[start:self.pos - 1]
        return ""

    def at_end(self) -> bool:
        self.skip_ws()
        return self.pos >= len(self.s)

    def parse(self) -> etree._Element:
        """解析完整 LaTeX 表达式，返回 m:oMath 元素。"""
        omath = _make_el("oMath")
        while not self.at_end():
            el = self.parse_expr()
            if el is not None:
                omath.append(el)
        return omath

    def parse_expr(self) -> etree._Element:
        """解析单个表达式单元。"""
        self.skip_ws()
        if self.at_end():
            return None

        ch = self.peek()

        # LaTeX 命令
        if ch == "\\":
            return self.parse_command()

        # 上标/下标
        if ch == "^":
            self.advance()
            sup = self.parse_group()
            return self._make_sup(None, sup)
        if ch == "_":
            self.advance()
            sub = self.parse_group()
            return self._make_sub(None, sub)

        # 组
        if ch == "{":
            content = self.parse_group()
            return _latex_to_omml_inner(content)

        # 普通字符
        self.advance()
        # 检查后续是否有上下标
        return self._check_scripts(_make_run(ch))

    def parse_command(self) -> etree._Element:
        """解析 \\command{args} 并返回对应 OMML 元素。"""
        self.advance()  # skip \\
        cmd = ""
        while self.pos < len(self.s) and self.s[self.pos].isalpha():
            cmd += self.advance()

        if not cmd:
            # \\ 或 \special_char
            if self.pos < len(self.s):
                ch = self.advance()
                return _make_run(ch)
            return _make_run("\\")

        # frac
        if cmd == "frac":
            num = self.parse_group()
            den = self.parse_group()
            f = _make_el("f")
            num_el = _make_el("num")
            num_el.append(_latex_to_omml_inner(num))
            den_el = _make_el("den")
            den_el.append(_latex_to_omml_inner(den))
            f.append(num_el)
            f.append(den_el)
            return self._check_scripts(f)

        # sqrt
        if cmd == "sqrt":
            opt = self.parse_optional()
            body = self.parse_group()
            rad = _make_el("rad")
            deg_el = _make_el("deg")
            if opt:
                deg_el.append(_latex_to_omml_inner(opt))
            rad.append(deg_el)
            e = _wrap_in_e(_latex_to_omml_inner(body))
            rad.append(e)
            return self._check_scripts(rad)

        # overline / bar
        if cmd in ("overline", "bar"):
            body = self.parse_group()
            bar_el = _make_el("bar")
            bar_el.append(_wrap_in_e(_latex_to_omml_inner(body)))
            return self._check_scripts(bar_el)

        # 重音
        if cmd in _ACCENT_MAP:
            body = self.parse_group()
            acc = _make_el("acc")
            accPr = _make_el("accPr")
            chr_el = _make_el("chr")
            chr_el.set(f"{{{_M}}}val", _ACCENT_MAP[cmd])
            accPr.append(chr_el)
            acc.append(accPr)
            acc.append(_wrap_in_e(_latex_to_omml_inner(body)))
            return self._check_scripts(acc)

        # N-ary 运算
        if cmd in _NARY_OPS:
            nary = _make_el("nary")
            naryPr = _make_el("naryPr")
            chr_el = _make_el("chr")
            chr_el.set(f"{{{_M}}}val", _LATEX_TO_UNICODE.get(cmd, cmd))
            naryPr.append(chr_el)
            nary.append(naryPr)
            # 解析下标和上标
            sub_text, sup_text = "", ""
            self.skip_ws()
            if self.peek() == "_":
                self.advance()
                sub_text = self.parse_group()
            self.skip_ws()
            if self.peek() == "^":
                self.advance()
                sup_text = self.parse_group()
            self.skip_ws()
            # 也处理上标在前的情况
            if self.peek() == "_" and not sub_text:
                self.advance()
                sub_text = self.parse_group()
            sub_el = _make_el("sub")
            if sub_text:
                sub_el.append(_latex_to_omml_inner(sub_text))
            sup_el = _make_el("sup")
            if sup_text:
                sup_el.append(_latex_to_omml_inner(sup_text))
            nary.append(sub_el)
            nary.append(sup_el)
            # 剩余部分作为 body（取一个表达式）
            body_el = _make_el("e")
            self.skip_ws()
            if not self.at_end():
                next_expr = self.parse_expr()
                if next_expr is not None:
                    body_el.append(next_expr)
            nary.append(body_el)
            return nary

        # left/right 括号
        if cmd == "left":
            self.skip_ws()
            beg_chr = self.advance() if not self.at_end() else "("
            # 收集 \right 前的内容
            inner_start = self.pos
            depth = 1
            while self.pos < len(self.s) and depth > 0:
                if self.s[self.pos:self.pos + 6] == "\\left":
                    depth += 1
                    self.pos += 5
                elif self.s[self.pos:self.pos + 7] == "\\right":
                    depth -= 1
                    if depth == 0:
                        break
                    self.pos += 6
                else:
                    self.pos += 1
            inner = self.s[inner_start:self.pos]
            # skip \right and its char
            if self.s[self.pos:self.pos + 6] == "\\right":
                self.pos += 6
            self.skip_ws()
            end_chr = self.advance() if not self.at_end() else ")"
            d = _make_el("d")
            dPr = _make_el("dPr")
            bc = _make_el("begChr")
            bc.set(f"{{{_M}}}val", beg_chr)
            ec = _make_el("endChr")
            ec.set(f"{{{_M}}}val", end_chr)
            dPr.append(bc)
            dPr.append(ec)
            d.append(dPr)
            d.append(_wrap_in_e(_latex_to_omml_inner(inner)))
            return self._check_scripts(d)

        if cmd == "right":
            # 不应单独出现，已在 \left 中处理
            return None

        # begin/end 环境
        if cmd == "begin":
            env = self.parse_group()
            # 查找 \end{env}
            end_marker = f"\\end{{{env}}}"
            idx = self.s.find(end_marker, self.pos)
            if idx < 0:
                inner = self.s[self.pos:]
                self.pos = len(self.s)
            else:
                inner = self.s[self.pos:idx]
                self.pos = idx + len(end_marker)

            if env in ("matrix", "pmatrix", "bmatrix", "vmatrix", "Vmatrix", "Bmatrix"):
                return self._make_matrix(inner, env)
            if env in ("aligned", "align", "align*"):
                return self._make_eqarr(inner)
            # 未知环境：作为文本
            return _make_run(f"\\begin{{{env}}}{inner}\\end{{{env}}}")

        if cmd == "end":
            self.parse_group()  # consume
            return None

        # 已知符号
        if cmd in _LATEX_TO_UNICODE:
            run = _make_run(_LATEX_TO_UNICODE[cmd])
            return self._check_scripts(run)

        # text / mathrm 等
        if cmd in ("text", "mathrm", "textrm", "operatorname"):
            body = self.parse_group()
            return self._check_scripts(_make_run(body))

        # 未知命令：作为文本
        return self._check_scripts(_make_run(f"\\{cmd}"))

    def _check_scripts(self, base) -> etree._Element:
        """检查后续是否有 ^/_ 上下标。"""
        self.skip_ws()
        has_sub, has_sup = False, False
        sub_text, sup_text = "", ""

        if self.peek() == "_":
            self.advance()
            sub_text = self.parse_group()
            has_sub = True
        self.skip_ws()
        if self.peek() == "^":
            self.advance()
            sup_text = self.parse_group()
            has_sup = True
        self.skip_ws()
        if self.peek() == "_" and not has_sub:
            self.advance()
            sub_text = self.parse_group()
            has_sub = True

        if has_sub and has_sup:
            el = _make_el("sSubSup")
            el.append(_wrap_in_e(base))
            sub_el = _make_el("sub")
            sub_el.append(_latex_to_omml_inner(sub_text))
            sup_el = _make_el("sup")
            sup_el.append(_latex_to_omml_inner(sup_text))
            el.append(sub_el)
            el.append(sup_el)
            return el
        if has_sup:
            el = _make_el("sSup")
            el.append(_wrap_in_e(base))
            sup_el = _make_el("sup")
            sup_el.append(_latex_to_omml_inner(sup_text))
            el.append(sup_el)
            return el
        if has_sub:
            el = _make_el("sSub")
            el.append(_wrap_in_e(base))
            sub_el = _make_el("sub")
            sub_el.append(_latex_to_omml_inner(sub_text))
            el.append(sub_el)
            return el
        return base

    def _make_sup(self, base, sup_text: str) -> etree._Element:
        el = _make_el("sSup")
        el.append(_wrap_in_e(base))
        sup_el = _make_el("sup")
        sup_el.append(_latex_to_omml_inner(sup_text))
        el.append(sup_el)
        return el

    def _make_sub(self, base, sub_text: str) -> etree._Element:
        el = _make_el("sSub")
        el.append(_wrap_in_e(base))
        sub_el = _make_el("sub")
        sub_el.append(_latex_to_omml_inner(sub_text))
        el.append(sub_el)
        return el

    def _make_matrix(self, inner: str, env: str) -> etree._Element:
        m = _make_el("m")
        rows = inner.split("\\\\")
        for row in rows:
            row = row.strip()
            if not row:
                continue
            mr = _make_el("mr")
            cells = row.split("&")
            for cell in cells:
                e = _make_el("e")
                e.append(_latex_to_omml_inner(cell.strip()))
                mr.append(e)
            m.append(mr)
        # 括号包裹
        if env in ("pmatrix", "bmatrix", "vmatrix", "Vmatrix", "Bmatrix"):
            d = _make_el("d")
            dPr = _make_el("dPr")
            chr_map = {"pmatrix": ("(", ")"), "bmatrix": ("[", "]"),
                       "vmatrix": ("|", "|"), "Vmatrix": ("\u2016", "\u2016"),
                       "Bmatrix": ("{", "}")}
            beg, end = chr_map.get(env, ("(", ")"))
            bc = _make_el("begChr")
            bc.set(f"{{{_M}}}val", beg)
            ec = _make_el("endChr")
            ec.set(f"{{{_M}}}val", end)
            dPr.append(bc)
            dPr.append(ec)
            d.append(dPr)
            d.append(_wrap_in_e(m))
            return d
        return m

    def _make_eqarr(self, inner: str) -> etree._Element:
        eqArr = _make_el("eqArr")
        rows = inner.split("\\\\")
        for row in rows:
            row = row.strip()
            if not row:
                continue
            e = _make_el("e")
            e.append(_latex_to_omml_inner(row))
            eqArr.append(e)
        return eqArr


def _latex_to_omml_inner(latex: str) -> etree._Element:
    """解析 LaTeX 片段并返回 OMML 元素（内部递归调用）。"""
    parser = _LaTeXParser(latex)
    omath = parser.parse()
    # 如果只有一个子元素，直接返回子元素
    children = list(omath)
    if len(children) == 1:
        return children[0]
    return omath


def latex_to_omml(latex: str) -> etree._Element:
    """
    将 LaTeX 字符串转换为 m:oMath XML 元素。
    主入口函数。用于在 DOCX 中插入数学公式。
    """
    parser = _LaTeXParser(latex)
    return parser.parse()


def latex_to_omml_xml(latex: str) -> str:
    """
    将 LaTeX 字符串转换为 OMML XML 字符串。
    用于调试和测试。
    """
    el = latex_to_omml(latex)
    return etree.tostring(el, encoding="unicode")
