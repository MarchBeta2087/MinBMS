"""``ordinal_notation`` 的离线单测（不需要 Docker）：

    python tools/test_ordinal_notation.py

分两层：

1. **记法机制**：两边文本 → 同一棵树 → 相等；
2. **真实对拍**：用 ``fixtures/`` 里打到的 basmat 原文，对上 ``Explore.exe`` 打出的
   本仓库序数（这两组值都来自实测，不是想象的）。
"""

from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from ordinal_notation import (  # noqa: E402
    cnf_int,
    cnf_one,
    cnf_zero,
    comparable,
    format_cnf,
    merge_terms,
    ordinals_agree,
    parse_basmat_cnf,
    parse_minbms_cnf,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures"
_ORD_RE = re.compile(r"^Ord = (.*)$", re.MULTILINE)


def basmat_ord_text(fixture: str) -> str:
    """从 capture 下来的原始输出里取第一行 `Ord = ...`。"""
    text = (FIXTURES / f"{fixture}.txt").read_text(encoding="utf-8")
    m = _ORD_RE.search(text)
    if not m:
        raise AssertionError(f"{fixture}.txt 里没有 Ord 行")
    return m.group(1).strip()


class MinBmsParsingTests(unittest.TestCase):
    def test_atoms(self) -> None:
        self.assertEqual(parse_minbms_cnf("0"), ())
        self.assertEqual(parse_minbms_cnf("1"), cnf_int(1))
        self.assertEqual(parse_minbms_cnf("7"), cnf_int(7))
        # ω = ω^1·1；注意它与「1」（= ω^0·1 = cnf_one()）是两棵不同的树。
        self.assertEqual(parse_minbms_cnf("ω"), ((cnf_one(), 1),))
        self.assertNotEqual(parse_minbms_cnf("ω"), cnf_one())

    def test_omega_squared_two_ways(self) -> None:
        # oShow 对 ω^1 会打成 "ω"（不写 ^(1)），但对 ω^2 会打 "ω^(2)"
        self.assertEqual(parse_minbms_cnf("ω^(2)"), ((cnf_int(2), 1),))
        self.assertNotEqual(parse_minbms_cnf("ω^(2)"), parse_minbms_cnf("ω"))

    def test_coefficient_and_sum(self) -> None:
        self.assertEqual(
            parse_minbms_cnf("ω^(3)·2 + ω·5 + 7"),
            parse_minbms_cnf("ω^(3) + ω^(3) + ω + ω + ω + ω + ω + 1 + 1 + 1 + 1 + 1 + 1 + 1"),
        )

    def test_nested_exponent(self) -> None:
        """ω^(ω+1) 的树：指数位置上是「ω+1」这棵子树。"""
        omega = parse_minbms_cnf("ω")
        omega_plus_1 = parse_minbms_cnf("ω + 1")
        self.assertEqual(omega_plus_1, merge_terms([(cnf_one(), 1), (cnf_zero(), 1)]))
        self.assertEqual(parse_minbms_cnf("ω^(ω + 1)"), ((omega_plus_1, 1),))

    def test_rejects_garbage(self) -> None:
        for bad in ["", "abc", "ω^", "ω^(", "w", "ω·", "ω^(2)·x"]:
            with self.subTest(bad=bad):
                self.assertIsNone(parse_minbms_cnf(bad))


class BasmatParsingTests(unittest.TestCase):
    def test_basic_forms(self) -> None:
        self.assertEqual(parse_basmat_cnf("w"), parse_minbms_cnf("ω"))
        self.assertEqual(parse_basmat_cnf("w^2"), parse_minbms_cnf("ω^(2)"))
        self.assertEqual(parse_basmat_cnf("w^w"), parse_minbms_cnf("ω^(ω)"))
        self.assertEqual(parse_basmat_cnf("w^(w+1)"), parse_minbms_cnf("ω^(ω + 1)"))

    def test_coefficients_are_repeated_sums(self) -> None:
        """basmat 把系数写成「重复相加」—— 归一化必须把它合回系数。"""
        self.assertEqual(parse_basmat_cnf("w+w"), parse_minbms_cnf("ω·2"))
        self.assertEqual(parse_basmat_cnf("w+w+w"), parse_minbms_cnf("ω·3"))
        self.assertEqual(parse_basmat_cnf("w^3+w^3"), parse_minbms_cnf("ω^(3)·2"))

    def test_out_of_range_returns_none(self) -> None:
        """e / p 是超出康托范式的构造：**不可比**，必须返回 None 而不是硬解析。"""
        for beyond in ["e_0", "e_1", "(e_0)w", "p0(p1(0))", "p0(p1(p2(p3(0)+p2(0))))"]:
            with self.subTest(text=beyond):
                self.assertIsNone(parse_basmat_cnf(beyond))

    def test_rejects_garbage(self) -> None:
        for bad in ["", "2 3", "w+", "+w", "w^", "(", "w)" ]:
            with self.subTest(bad=bad):
                self.assertIsNone(parse_basmat_cnf(bad))


class AgreementTests(unittest.TestCase):
    def test_agree_and_disagree(self) -> None:
        self.assertTrue(ordinals_agree("w^w", "ω^(ω)"))
        self.assertTrue(ordinals_agree("w+w", "ω·2"))
        self.assertFalse(ordinals_agree("w^w", "ω^(2)"))
        self.assertFalse(ordinals_agree("w", "ω·2"))

    def test_incomparable_gives_none_not_false(self) -> None:
        """不可比 ≠ 不一致 —— 必须返回 None，否则就把「不知道」谎报成「不一致」。"""
        self.assertIsNone(ordinals_agree("e_0", "ω"))
        self.assertIsNone(ordinals_agree("w", "not-a-number"))
        self.assertFalse(comparable("e_0", "ω"))
        self.assertTrue(comparable("w^w", "ω^(ω)"))

    def test_format_is_stable(self) -> None:
        for text in ["ω", "ω^(2)", "ω·2", "ω^(ω + 1)", "ω^(ω^(ω))"]:
            cnf = parse_minbms_cnf(text)
            self.assertIsNotNone(cnf)
            self.assertEqual(parse_minbms_cnf(format_cnf(cnf)), cnf, text)


class RealCrossCheckTests(unittest.TestCase):
    """用 fixtures 里的 basmat 原文 vs Explore.exe 打出的本仓库序数（两边都是实测值）。"""

    CASES = [
        ("copy-1row-omega", "ω"),  # (0)(1)
        ("notation-w-squared", "ω^(2)"),  # (0)(1)(1)
        ("notation-w-times-2", "ω·2"),  # (0)(1)(0)(1)
        ("notation-w-pow-w-plus-1", "ω^(ω + 1)"),  # (0)(1)(2)(1)
        ("copy-1row-ww", "ω^(ω)"),  # (0)(1)(2)
    ]

    def test_basmat_fixture_agrees_with_minbms(self) -> None:
        for fixture, minbms_text in self.CASES:
            with self.subTest(fixture=fixture):
                got = basmat_ord_text(fixture)
                self.assertTrue(
                    ordinals_agree(got, minbms_text),
                    f"basmat 说 {got!r}，本仓库说 {minbms_text!r} —— 两边应当一致",
                )

    def test_beyond_epsilon0_is_not_compared(self) -> None:
        """ε₀ 及以上：本仓库表示不出来，就**不比**（返回 None）。"""
        self.assertIsNone(ordinals_agree(basmat_ord_text("ord-epsilon0"), "ω"))
        self.assertIsNone(ordinals_agree(basmat_ord_text("psi-2row"), "ω"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
