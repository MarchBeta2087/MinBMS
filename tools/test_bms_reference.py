"""bms_reference 的**离线**单测（不需要 Docker）：

    python tools/test_bms_reference.py
    # 或在仓库根目录：python -m unittest discover -s tools -t tools

覆盖两件事：

* **展开**（BM4）—— 期望值来自 `VERSIONS.md` 的黄金用法与 README 的单行算例，
  都是本仓库自己的定义，不是从 basmat 抄的；
* **标准性**（种子展开闭包）—— 这里只锁**确定的**几个（空 / 对角 / 明显的非标准），
  更大范围的**与 basmat 对拍**在 `test_calibration.py`（需要 Docker）里做。
"""

from __future__ import annotations

import unittest

from bms_reference import (
    bad_root,
    bottom_most_nonzero_row,
    difference_vector,
    expand,
    is_standard,
    pad,
    seed,
)
from basmat_client import parse_matrix


def M(text: str):
    cols, _ = parse_matrix(text)
    return cols


class ExpandTests(unittest.TestCase):
    def test_single_row_omega(self) -> None:
        # (0)(1) = ω，其基本列 [n] 是 n 个 0（本仓库约定：n 份坏部）
        self.assertEqual(expand(M("(0)(1)"), 3), M("(0)(0)(0)"))

    def test_single_row_omega_pow_omega(self) -> None:
        # (0)(1)(2) = ω^ω，[3] = (0)(1)(1)(1)
        self.assertEqual(expand(M("(0)(1)(2)"), 3), M("(0)(1)(1)(1)"))

    def test_bm4_golden(self) -> None:
        # VERSIONS.md 的 BM4 黄金用例
        self.assertEqual(
            expand(M("(0,0,0)(1,1,1)(2,1,0)(1,1,1)"), 3),
            M("(0,0,0)(1,1,1)(2,1,0)(1,1,0)(2,2,1)(3,2,0)"
              "(2,2,0)(3,3,1)(4,3,0)"),
        )

    def test_two_row_epsilon0(self) -> None:
        # (0,0)(1,1) = ε₀，[3] = (0,0)(1,0)(2,0)
        self.assertEqual(expand(M("(0,0)(1,1)"), 3), M("(0,0)(1,0)(2,0)"))

    def test_successor_drops_zero_column(self) -> None:
        # 末列全零 → 删去末列（与 copies 无关）
        self.assertEqual(expand(M("(0)(1)(0)"), 5), M("(0)(1)"))

    def test_empty(self) -> None:
        self.assertEqual(expand((), 3), ())

    def test_pad_ragged(self) -> None:
        self.assertEqual(pad(((0,), (1, 1))), ((0, 0), (1, 1)))


class StructureTests(unittest.TestCase):
    def test_bad_root(self) -> None:
        # (0)(1)(2)：末列 2，最底非零行 0，其父是列 1
        self.assertEqual(bottom_most_nonzero_row(M("(0)(1)(2)")), 0)
        self.assertEqual(bad_root(M("(0)(1)(2)")), 1)

    def test_difference_vector_single_row_is_zero(self) -> None:
        # 单行：t=0，t 及以下 Δ 恒为 0 ⇒ Δ ≡ 0
        self.assertEqual(difference_vector(M("(0)(1)(2)")), (0,))

    def test_difference_vector_two_row(self) -> None:
        # (0,0)(1,1)(2,1)：末列 (2,1)，t=1，坏根列 0 ⇒ Δ=(2,0)
        # （basmat 也打印 Delta = (2,0)）
        self.assertEqual(difference_vector(M("(0,0)(1,1)(2,1)")), (2, 0))


class StandardnessTests(unittest.TestCase):
    def test_empty_and_principal(self) -> None:
        for t in ["", "(0)", "(0,0)", "(0)(1)", "(0,0)(1,1)", "(0)(1)(2)"]:
            with self.subTest(t=t):
                self.assertTrue(is_standard(M(t)))

    def test_known_nonstandard(self) -> None:
        # README 三条件之外的全局不标准（实测 basmat 也判不标准）
        self.assertFalse(is_standard(M("(0)(0)(1)")))
        self.assertFalse(is_standard(M("(0)(0)(1)(1)")))
        self.assertFalse(is_standard(M("(0)(0)(0)(1)")))

    def test_seed_is_one_row_taller(self) -> None:
        self.assertEqual(seed(2), ((0, 0), (1, 1)))
        self.assertEqual(seed(3), ((0, 0, 0), (1, 1, 1)))

    def test_prefix_closed(self) -> None:
        """标准矩阵的每个前缀都标准（实测不变量，见 STANDARDNESS.md）。"""
        from bms_reference import standard_set

        s = standard_set(2, max_cols=6, max_val=6, max_copies=5)
        self.assertTrue(s, "闭包不应为空")
        for m in s:
            for i in range(len(m) + 1):
                with self.subTest(matrix=m, prefix=m[:i]):
                    self.assertIn(m[:i], s)


if __name__ == "__main__":
    unittest.main()
