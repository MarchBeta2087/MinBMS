"""把 basmat 与本仓库（``oShow``）的**序数文本**归一到同一种树，好做交叉验证。

两边的记法不一样（都由实测锁定，见 ``tools/README.md`` 与 ``fixtures/``）：

| 序数 | 本仓库 ``oShow`` | basmat |
|---|---|---|
| 1 | ``1`` | ``1`` |
| ω | ``ω`` | ``w`` |
| ω² | ``ω^(2)`` | ``w^2`` |
| ω^ω | ``ω^(ω)`` | ``w^w`` |
| ω^(ω+1) | ``ω^(ω + 1)`` | ``w^(w+1)`` |
| ω·3 | ``ω·3`` | ``w+w+w`` ← **系数是「重复相加」**，不是乘号 |
| ε₀ | 表示不出来（> ε₀ 天花板） | ``e_0`` |

所以归一化的要点是：**把「重复相加」合并成系数**，再把两边的语法揉成同一棵树。

**只对可比区间（< ε₀、且没有 ``e``/``p`` 记法）下结论**：一旦文本里出现
``e`` / ``p`` 或任何我们不认识的构造，解析返回 ``None``，调用方必须**跳过比较**
（而不是猜一个值）—— 铁律三。
"""

from __future__ import annotations

import re
from functools import cmp_to_key

#: 康托范式的树：``((指数, 系数), ...)``，**指数本身也是 CNF**；``()`` 表示 0。
#: 规范形：系数 > 0、同指数合并、按指数**降序**排列。
Cnf = tuple


def _cmp(a: Cnf, b: Cnf) -> int:
    """CNF 之间的序数比较（先比最高项，逐项递归）。"""
    i = 0
    while i < len(a) or i < len(b):
        if i >= len(a):
            return -1
        if i >= len(b):
            return 1
        ea, ca = a[i]
        eb, cb = b[i]
        c = _cmp(ea, eb)
        if c != 0:
            return c
        if ca != cb:
            return -1 if ca < cb else 1
        i += 1
    return 0


_ZERO: Cnf = ()
_ONE: Cnf = (((), 1),)  # ω^0 · 1 = 1
#: ω = ω^1 · 1 —— 注意它是**一棵 CNF**，不要和 `_ONE`（= 1）混淆：
#: 在 `factor()` 里裸写一个 `w` 是 ω，而在 `term()` 里 `w` 是「指数 1、系数 1」的那一项。
_OMEGA: Cnf = ((_ONE, 1),)


def cnf_zero() -> Cnf:
    return _ZERO


def cnf_one() -> Cnf:
    return _ONE


def cnf_int(n: int) -> Cnf:
    return () if n <= 0 else (((), n),)


def merge_terms(terms: list[tuple[Cnf, int]]) -> Cnf:
    """合并同指数的项、丢掉非正系数、按指数降序排好 —— 得到规范形。"""
    acc: list[list] = []
    for exp, coeff in terms:
        if coeff <= 0:
            continue
        for item in acc:
            if item[0] == exp:
                item[1] += coeff
                break
        else:
            acc.append([exp, coeff])
    acc.sort(key=lambda it: cmp_to_key(_cmp)(it[0]), reverse=True)
    return tuple((exp, coeff) for exp, coeff in acc if coeff > 0)


def format_cnf(cnf: Cnf) -> str:
    """归一化后的 ASCII 写法（本仓库风格），用于报告与比较。"""
    if not cnf:
        return "0"
    parts = []
    for exp, coeff in cnf:
        if not exp:
            parts.append(str(coeff))
        elif exp == _ONE:
            parts.append("ω" if coeff == 1 else f"ω·{coeff}")
        else:
            parts.append(f"ω^({format_cnf(exp)})" + ("" if coeff == 1 else f"·{coeff}"))
    return " + ".join(parts)


# ---------------------------------------------------------------------------
# 本仓库 oShow 的解析
# ---------------------------------------------------------------------------

# oShow 只有三种原子：整数、ω、ω^( expr )，项之间用 " + " 连接，系数用 "·"。
_RE_MB_INT = re.compile(r"\d+")
_RE_MB_TERM = re.compile(r"^(?P<omega>ω)(?:\^\((?P<exp>.+)\))?(?P<coeff>·\d+)?$")


def _split_top_level(s: str, sep: str) -> list[str] | None:
    """只在**括号深度为 0** 处按 ``sep`` 切分；括号不配对返回 ``None``。

    为什么不能直接 ``s.split(" + ")``：oShow 的指数里**也可能带空格**，
    例如 ``ω^(ω + 1)`` —— 裸切会切出 ``['ω^(ω', '1)']``。
    """
    parts: list[str] = []
    depth = 0
    i = 0
    start = 0
    while i < len(s):
        ch = s[i]
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth < 0:
                return None
        elif depth == 0 and s.startswith(sep, i):
            parts.append(s[start:i])
            i += len(sep)
            start = i
            continue
        i += 1
    if depth != 0:
        return None
    parts.append(s[start:])
    return parts


def parse_minbms_cnf(text: str) -> Cnf | None:
    """解析本仓库 ``oShow`` 的输出；认不出来的返回 ``None``。"""
    s = text.strip()
    if not s:
        return None
    if s == "0":
        return _ZERO
    parts = _split_top_level(s, " + ")
    if parts is None:
        return None
    terms: list[tuple[Cnf, int]] = []
    for raw in parts:
        raw = raw.strip()
        if not raw:
            return None
        if _RE_MB_INT.fullmatch(raw):
            terms.append((_ZERO, int(raw)))
            continue
        m = _RE_MB_TERM.match(raw)
        if not m:
            return None
        if m.group("exp") is None:
            exp = _ONE
        else:
            exp = parse_minbms_cnf(m.group("exp"))
            if exp is None:
                return None
        coeff = int(m.group("coeff")[1:]) if m.group("coeff") else 1
        terms.append((exp, coeff))
    return merge_terms(terms)


# ---------------------------------------------------------------------------
# basmat 的解析
# ---------------------------------------------------------------------------
#
# 实测的 basmat 记法（见 fixtures/）：
#   w            = ω
#   w^2          = ω^2        指数是原子时可以省括号
#   w^w          = ω^ω
#   w^(w+1)      = ω^(ω+1)    指数是「式子」时带括号
#   w+w          = ω·2        ★ 系数写成**重复相加**
#   w^3+w^3      = ω^3·2
#   e_0 / p0(…)  超出康托范式范围 → 我们**不比**（返回 None）
#
# 只允许 `w 0-9 + ^ ( )` 这些字符；出现别的（尤其 e / p）就视为不可比。

_BASMAT_CHARS = set("w0123456789+^()")


class _BasmatParser:
    def __init__(self, s: str) -> None:
        self.s = s
        self.i = 0

    def skip_ws(self) -> None:
        """跳过空白。

        为什么必须支持空白：``Ordinal.full_text()`` 补常数项时会产出 ``w + 1`` 这种带空格的
        文本，而我们要能把**自己的输出**再解析回去（对拍就是这么做的）。
        注意 `digits()` 每次都先 `skip_ws()`，所以 ``"1 2"`` 不会被拼成 12，而是解析失败。
        """
        while self.i < len(self.s) and self.s[self.i].isspace():
            self.i += 1

    def peek(self) -> str:
        return self.s[self.i] if self.i < len(self.s) else ""

    def digits(self) -> int | None:
        self.skip_ws()
        start = self.i
        while self.peek().isdigit():
            self.i += 1
        return int(self.s[start : self.i]) if self.i > start else None

    def expr(self) -> Cnf | None:
        """expr := term ('+' term)*"""
        terms: list[tuple[Cnf, int]] = []
        while True:
            t = self.term()
            if t is None:
                return None
            terms.append(t)
            self.skip_ws()
            if self.peek() == "+":
                self.i += 1
                continue
            return merge_terms(terms)

    def term(self) -> tuple[Cnf, int] | None:
        """term := 'w' ('^' factor)? | 整数"""
        self.skip_ws()
        if self.peek() == "w":
            self.i += 1
            self.skip_ws()
            if self.peek() == "^":
                self.i += 1
                e = self.factor()
                return None if e is None else (e, 1)
            return (_ONE, 1)
        n = self.digits()
        return None if n is None else (_ZERO, n)

    def factor(self) -> Cnf | None:
        """factor := '(' expr ')' | 'w' ('^' factor)? | 整数"""
        self.skip_ws()
        if self.peek() == "(":
            self.i += 1
            e = self.expr()
            self.skip_ws()
            if e is None or self.peek() != ")":
                return None
            self.i += 1
            return e
        if self.peek() == "w":
            self.i += 1
            self.skip_ws()
            if self.peek() == "^":
                self.i += 1
                f = self.factor()
                return None if f is None else merge_terms([(f, 1)])
            return _OMEGA  # 裸写一个 w 是 ω（不是 1！）
        n = self.digits()
        return None if n is None else cnf_int(n)


def parse_basmat_cnf(text: str) -> Cnf | None:
    """解析 basmat 的 `Ord = ...` 文本。

    返回 ``None`` 表示**不可比**（出现 ``e`` / ``p`` 等超出康托范式的构造，
    或语法不认识）—— 这时调用方必须跳过比较，不许猜。
    """
    s = text.strip()
    if not s or any(ch not in _BASMAT_CHARS and not ch.isspace() for ch in s):
        return None
    p = _BasmatParser(s)
    cnf = p.expr()
    p.skip_ws()
    if cnf is None or p.i != len(s):
        return None
    return cnf


# ---------------------------------------------------------------------------
# 比对
# ---------------------------------------------------------------------------


def ordinals_agree(basmat_text: str, minbms_text: str) -> bool | None:
    """两边都可比时给 True/False；只要有一边不可比就给 ``None``（= 不下结论）。"""
    b = parse_basmat_cnf(basmat_text)
    m = parse_minbms_cnf(minbms_text)
    if b is None or m is None:
        return None
    return b == m


def comparable(basmat_text: str, minbms_text: str) -> bool:
    """两边是否都落在可比的康托范式区间内。"""
    return (
        parse_basmat_cnf(basmat_text) is not None
        and parse_minbms_cnf(minbms_text) is not None
    )
