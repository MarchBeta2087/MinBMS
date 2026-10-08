"""standardness.py 的**离线**单测（不需要 Docker）：

    python tools/test_standardness.py
    # 或在仓库根目录：python -m unittest discover -s tools -t tools

只测纯函数：标准性判定的解析、种子的按定义构造、候选枚举。
真正去跑 basmat 的部分在 ``test_calibration.py`` / 手工 `standardness.py sweep` 里。
这里的 fixture 文本全部取自**实测输出**（见 STANDARDNESS.md）。
"""

from __future__ import annotations

import unittest

from standardness import enumerate_candidates, parse_standardness, seed_for

# 实测输出：局部失败（越界）——只有一行理由
_LOCAL = (
    "(0)(1)(3) is not standard because (0)(1)(2) does not decrease to the sequence.\n"
    "--------------------------------------------\n"
    "(0)(1)(3)[3]\n"
)

# 实测输出：全局失败——先检查、再递降、最后给 Z
_GLOBAL = (
    "Checking if (0,0,0)(1,1,1)(2,2,2)(3,2,2)(4,3,0) is standard or not.\n"
    "Decreasing sequence from (0,0,0,0)(1,1,1,1) follows.\n"
    "(0,0,0)(1,1,1)(2,2,2)(3,3,3)\n"
    "(0,0,0)(1,1,1)(2,2,2)(3,3,2)\n"
    "(0,0,0)(1,1,1)(2,2,2)(3,2,2)(4,2,1)\n"
    "Not standard because it is (0,0,0)(1,1,1)(2,2,2)(3,2,2)(4,2,0)...\n"
    "--------------------------------------------\n"
    "(0,0,0)(1,1,1)(2,2,2)(3,2,2)(4,3,0)[3]\n"
)

# 实测输出：命中目标 -> 标准
_STANDARD = (
    "Checking if (0)(1)(1) is standard or not.\n"
    "Decreasing sequence from (0,0)(1,1) follows.\n"
    "(0)(1)(2)\n"
    "(0)(1)(1)\n"
    "Standard.\n"
    "--------------------------------------------\n"
)

# 实测输出：底矩阵直接判标准
_DIRECT = "(0)(1)(2) is standard.\n--------------------------------------------\n"

# 实测输出：首列不是全零
_BADSTART = "(0,1)(0,2) is not standard because not starting from (0,0)\n"


class ParseStandardnessTests(unittest.TestCase):
    def test_global_failure(self) -> None:
        p = parse_standardness(_GLOBAL)
        assert p is not None
        self.assertFalse(p.standard)
        self.assertEqual(p.matrix, "(0,0,0)(1,1,1)(2,2,2)(3,2,2)(4,3,0)")
        self.assertEqual(p.seed, "(0,0,0,0)(1,1,1,1)")
        self.assertEqual(len(p.sequence), 3)
        self.assertEqual(p.sequence[-1], "(0,0,0)(1,1,1)(2,2,2)(3,2,2)(4,2,1)")
        self.assertEqual(
            p.reason, "(0,0,0)(1,1,1)(2,2,2)(3,2,2)(4,2,0)..."
        )

    def test_local_failure(self) -> None:
        p = parse_standardness(_LOCAL)
        assert p is not None
        self.assertFalse(p.standard)
        self.assertEqual(p.matrix, "(0)(1)(3)")
        self.assertIsNone(p.seed)
        self.assertEqual(p.sequence, ())
        self.assertEqual(
            p.reason, "(0)(1)(2) does not decrease to the sequence"
        )

    def test_standard_hit(self) -> None:
        p = parse_standardness(_STANDARD)
        assert p is not None
        self.assertTrue(p.standard)
        self.assertEqual(p.seed, "(0,0)(1,1)")
        self.assertEqual(p.sequence, ("(0)(1)(2)", "(0)(1)(1)"))
        self.assertIsNone(p.reason)

    def test_direct_standard(self) -> None:
        p = parse_standardness(_DIRECT)
        assert p is not None
        self.assertTrue(p.standard)
        self.assertEqual(p.matrix, "(0)(1)(2)")
        self.assertIsNone(p.seed)
        self.assertEqual(p.sequence, ())

    def test_bad_start(self) -> None:
        p = parse_standardness(_BADSTART)
        assert p is not None
        self.assertFalse(p.standard)
        self.assertEqual(p.reason, "not starting from (0,0)")

    def test_no_judgement_returns_none(self) -> None:
        # 没跑 -d 时只有矩阵行，应当解析不到 —— 不猜。
        self.assertIsNone(parse_standardness("(0)(1)(2)[3]\nOrd = w^w\n"))


class SeedForTests(unittest.TestCase):
    def test_seed_is_one_row_taller(self) -> None:
        self.assertEqual(seed_for("(0)(0)(1)"), "(0,0)(1,1)")
        self.assertEqual(seed_for("(0,0)(1,1)(2,0)"), "(0,0,0)(1,1,1)")
        self.assertEqual(seed_for("(0,0,0)(1,1,1)"), "(0,0,0,0)(1,1,1,1)")

    def test_seed_ignores_trailing_n(self) -> None:
        self.assertEqual(seed_for("(0,0)(1,1)[3]"), "(0,0,0)(1,1,1)")

    def test_empty_matrix_has_no_seed(self) -> None:
        with self.assertRaises(ValueError):
            seed_for("")


class EnumerateCandidatesTests(unittest.TestCase):
    def test_first_column_is_zero_and_columns_non_increasing(self) -> None:
        cands = list(enumerate_candidates(rows=1, cols=3, maxval=2))
        self.assertTrue(cands)
        for cols in cands:
            self.assertEqual(cols[0], (0,))
            for col in cols:
                self.assertGreaterEqual(col[0], col[-1])

    def test_two_row_count(self) -> None:
        # 1 列 + 3 列以内：1 + 6 + 36（2 行、值 0..2 的非递增列有 6 个）
        cands = list(enumerate_candidates(rows=2, cols=2, maxval=2))
        self.assertEqual(len(cands), 1 + 6)


if __name__ == "__main__":
    unittest.main()
