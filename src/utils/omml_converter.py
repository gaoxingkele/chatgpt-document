# -*- coding: utf-8 -*-
"""
OMML (Office Math Markup Language) → LaTeX 转换器。
支持 Word 文档中 <m:oMath> / <m:oMathPara> 元素的递归转换。
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
