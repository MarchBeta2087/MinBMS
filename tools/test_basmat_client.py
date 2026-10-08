"""basmat_client 的**离线**单测（不需要 Docker，一条命令即可跑）：

    python tools/test_basmat_client.py
    # 或在仓库根目录：python -m unittest discover -s tools -t tools

这里只测「我们自己写的纯函数」：矩阵的解析 / 格式化 / 常数项（末尾零括号）计数，
以及 basmat-batch 的框（BEGIN/END/DONE）解析。

**需要 Docker 的**东西（真的去跑 basmat、并与本仓库的展开结果对拍）在
``test_calibration.py`` 里 —— 那个是「实测锁定事实」，与这里的纯逻辑测试分开。
"""

from __future__ import annotations

import unittest

from basmat_client import (
    BasmatError,
    _check_batch_ini,
    _parse_batch_output,
    format_matrix,
    is_zero_column,
    matrix_rows,
    pad_matrix,
    parse_matrix,
    strip_trailing_zero_columns,
    trailing_zero_columns,
)


class ParseMatrixTests(unittest.TestCase):
    def test_column_form(self) -> None:
        self.assertEqual(parse_matrix("(0,0)(1,1)[3]"), (((0, 0), (1, 1)), 3))

    def test_single_row(self) -> None:
        self.assertEqual(parse_matrix("(0)(1)(2)"), (((0,), (1,), (2,)), None))

    def test_empty_matrix(self) -> None:
        # 空矩阵（∅）：空串、纯空白、() 都算 —— 基本列里真的会出现它。
        for text in ["", "   ", "()"]:
            with self.subTest(text=text):
                self.assertEqual(parse_matrix(text), ((), None))

    def test_ragged_columns_allowed(self) -> None:
        # BMS 允许省略各列末尾的 0（与 initBMS 的输入约定一致），这里原样保留。
        self.assertEqual(parse_matrix("(0,1)(0)"), (((0, 1), (0,)), None))

    def test_whitespace_tolerated(self) -> None:
        self.assertEqual(parse_matrix("  (0, 0) (1, 1) [4] "), (((0, 0), (1, 1)), 4))

    def test_rejects_garbage(self) -> None:
        for bad in ["junk", "(0)junk", "(0,)", "(,0)", "(0,-1)", "(0)[x]", "(0)[]", "(a)"]:
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    parse_matrix(bad)

    def test_format_round_trip(self) -> None:
        for text, n in [("(0,0)(1,1)", 3), ("(0)(1)(2)", None), ("", None)]:
            suffix = f"[{n}]" if n is not None else ""
            cols, parsed_n = parse_matrix(text + suffix)
            self.assertEqual(format_matrix(cols, parsed_n), text + suffix)



class MatrixHelperTests(unittest.TestCase):
    def test_zero_columns_counted_by_column_not_by_entry(self) -> None:
        """常数项按「列」数：三个零括号就是 3，不是 6。"""
        cols, _ = parse_matrix("(0,0)(0,0)(0,0)")
        self.assertEqual(trailing_zero_columns(cols), 3)

    def test_trailing_zero_columns_various(self) -> None:
        cases = {
            "()": 0,
            "(0)": 1,
            "(0)(0)": 2,
            "(0,0)(1,1)": 0,
            "(0,0)(1,1)(0,0)": 1,
            "(0)(1)(0)(0)(0)": 3,
        }
        for text, want in cases.items():
            with self.subTest(text=text):
                cols, _ = parse_matrix(text)
                self.assertEqual(trailing_zero_columns(cols), want)

    def test_strip_trailing_zero_columns(self) -> None:
        cols, _ = parse_matrix("(0,0)(1,1)(0,0)(0,0)")
        self.assertEqual(format_matrix(strip_trailing_zero_columns(cols)), "(0,0)(1,1)")

    def test_matrix_rows_and_padding(self) -> None:
        cols, _ = parse_matrix("(0,1)(0)")
        self.assertEqual(matrix_rows(cols), 2)
        self.assertEqual(format_matrix(pad_matrix(cols)), "(0,1)(0,0)")
        self.assertEqual(format_matrix(pad_matrix(cols, 3)), "(0,1,0)(0,0,0)")

    def test_is_zero_column(self) -> None:
        self.assertTrue(is_zero_column((0, 0)))
        self.assertTrue(is_zero_column((0,)))
        self.assertFalse(is_zero_column((0, 1)))


class BatchIniValidationTests(unittest.TestCase):
    def test_accepts_normal_ini(self) -> None:
        for good in ["(0,0)(1,1)[3]", "(0)(1)(2)[3]", "()"]:
            with self.subTest(good=good):
                _check_batch_ini(good)

    def test_rejects_whitespace_or_leading_dash(self) -> None:
        for bad in ["", " (0)[3]", "(0)[3] ", "(0) (1)[3]", "-d(0)[3]"]:
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    _check_batch_ini(bad)


class BatchFramingTests(unittest.TestCase):
    """解析 docker/basmat-batch 的输出框（这是**我们自己**的格式，可以放心断言）。"""

    def test_splits_blocks_in_order(self) -> None:
        text = (
            "=== BEGIN 1 ===\n"
            "(0)(1)(2) is standard.\n"
            "Ord = w^w\n"
            "=== END 1 rc=0 ===\n"
            "=== BEGIN 2 ===\n"
            "Ord = w^4\n"
            "=== END 2 rc=0 ===\n"
            "=== DONE 2 ===\n"
        )
        entries = _parse_batch_output(text, ["(0)(1)(2)[3]", "(0)(1)(1)(1)[3]"])
        self.assertEqual([e.ini for e in entries], ["(0)(1)(2)[3]", "(0)(1)(1)(1)[3]"])
        self.assertEqual(entries[0].stdout, "(0)(1)(2) is standard.\nOrd = w^w")
        self.assertEqual(entries[1].rc, 0)

    def test_nonzero_rc_is_reported_not_fatal(self) -> None:
        text = "=== BEGIN 1 ===\nboom\n=== END 1 rc=2 ===\n=== DONE 1 ===\n"
        entries = _parse_batch_output(text, ["(0)[2]"])
        self.assertEqual(entries[0].rc, 2)

    def test_missing_done_is_an_error(self) -> None:
        text = "=== BEGIN 1 ===\n=== END 1 rc=0 ===\n"
        with self.assertRaises(BasmatError):
            _parse_batch_output(text, ["(0)[2]"])

    def test_block_count_must_match_inputs(self) -> None:
        text = "=== BEGIN 1 ===\n=== END 1 rc=0 ===\n=== DONE 1 ===\n"
        with self.assertRaises(BasmatError):
            _parse_batch_output(text, ["(0)[2]", "(1)[2]"])

    def test_out_of_order_index_is_an_error(self) -> None:
        text = "=== BEGIN 2 ===\nx\n=== END 2 rc=0 ===\n=== DONE 2 ===\n"
        with self.assertRaises(BasmatError):
            _parse_batch_output(text, ["(0)[2]", "(1)[2]"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
