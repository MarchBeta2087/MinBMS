"""把 P2 校准的**已锁定事实**写成断言（需要 Docker + 已构建镜像）。

    docker compose -f docker/compose.yaml build      # 先构建
    python tools/test_calibration.py                 # 再跑

没有 Docker / 没有镜像时整个文件 skip（不假失败）。

这里的每一条断言都对应 ``tools/README.md``「已实测锁定的事实」里的一节，
并且尽量**锚在本仓库已有的文档值**上（README / VERSIONS.md），而不是只锚在 basmat 的输出上 ——
这样它同时验证「basmat 的行为」与「两边的对应关系」两件事。

注意：这些断言记录的是 **basmat@f2f0125（tag v4.0）** 的行为。
升级上游版本后请重跑 ``python tools/calibrate.py --capture``；若有变化，本文件会立刻变红。
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import basmat_client as bc  # noqa: E402
from basmat_client import (  # noqa: E402
    BasmatError,
    format_matrix,
    parse_matrix,
    parse_trace,
    trailing_zero_columns,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures"

READY = bc.docker_available() and bc.image_exists()
SKIP_REASON = f"没有可用的 Docker 或镜像 {bc.DEFAULT_IMAGE}（先 docker compose -f docker/compose.yaml build）"

# VERSIONS.md 里**本仓库自己锁死**的黄金值（不是从 basmat 抄的）：
# 同一个矩阵 (0,0,0)(1,1,1)(2,1,0)(1,1,1)[3] 在 BM4 与 BM3.3 下只差一列。
GOLDEN_BM4 = "(0,0,0)(1,1,1)(2,1,0)(1,1,0)(2,2,1)(3,2,0)(2,2,0)(3,3,1)(4,3,0)"
GOLDEN_BM33 = "(0,0,0)(1,1,1)(2,1,0)(1,1,0)(2,2,1)(3,1,0)(2,2,0)(3,3,1)(4,1,0)"
GOLDEN_INI = "(0,0,0)(1,1,1)(2,1,0)(1,1,1)[3]"


def cols_of(text: str) -> tuple[tuple[int, ...], ...]:
    return parse_matrix(text)[0]


def next_state(ini: str, version: str | int | None = None):
    """跑一次 basmat 并返回「下一步」的矩阵（即它自己做的**一次**展开）。"""
    opts = ["-d", "-t", "1"] if version is None else ["-v", str(version), "-d", "-t", "1"]
    trace = parse_trace(bc.run_basmat(ini, options=opts, timeout=300))
    if len(trace.nodes) < 2:
        raise AssertionError(f"没拿到下一步：{trace.raw}")
    return trace.nodes[1].matrix


def blocks_of(cols, block_cols: int) -> list[str]:
    """按固定块宽切分，返回每块的文本（用来数「复制了几份坏部」）。"""
    return [
        format_matrix(cols[i : i + block_cols])
        for i in range(0, len(cols), block_cols)
    ]



@unittest.skipUnless(READY, SKIP_REASON)
class HelpAndErrorHandlingTests(unittest.TestCase):
    def test_help_works(self) -> None:
        out = bc.run_basmat("-h", options=[], timeout=120)
        self.assertIn("Usage: basmat", out)

    def test_invalid_input_exits_zero_but_is_detected(self) -> None:
        """实测：非法输入时 basmat **退出码仍是 0**，只能靠输出里的错误行判错。"""
        p = bc.subprocess.run(
            ["docker", "run", "--rm", bc.DEFAULT_IMAGE, "not-a-matrix"],
            capture_output=True,
            text=True,
            timeout=120,
        )
        self.assertEqual(p.returncode, 0, "实测 basmat 对非法输入退出 0；若这里变了说明上游改了行为")
        self.assertIn(bc.INVALID_INPUT_MARK, p.stdout)
        with self.assertRaises(BasmatError):
            bc.run_basmat("not-a-matrix", timeout=120)


@unittest.skipUnless(READY, SKIP_REASON)
class TraceParsingTests(unittest.TestCase):
    def test_all_captured_fixtures_parse(self) -> None:
        """每个探针的原始输出都必须能解析出至少一个节点（回归护栏）。"""
        for txt in sorted(FIXTURES.glob("*.txt")):
            with self.subTest(fixture=txt.name):
                trace = parse_trace(txt.read_text(encoding="utf-8"))
                self.assertGreaterEqual(len(trace.nodes), 1)

    def test_no_dash_d_means_no_ordinal(self) -> None:
        """实测：没有 -d 就没有 Ord 行，只有一串矩阵 —— 所以取序数必须带 -d。"""
        text = bc.run_basmat("(0,0)(1,1)[3]", options=[], timeout=120)
        self.assertNotIn("Ord =", text)
        self.assertIn("(0,0)(1,1)[3]", text)


@unittest.skipUnless(READY, SKIP_REASON)
class OrdinalExtractionTests(unittest.TestCase):
    def test_ord_and_trailing_zero_columns(self) -> None:
        """用户给的那个样本：Ord 只有 w^w，常数项要靠「末尾几个零括号」补回来。"""
        res = bc.ordinal_of("(0)(1)(2)(0)(0)[3]")
        self.assertEqual(res.ord_text, "w^w")
        self.assertEqual(res.constant, 2, "(0)(1)(2)(0)(0) 末尾是 2 个零括号")
        self.assertEqual(res.full_text(), "w^w + 2")
        self.assertEqual(res.source, "Ord")

    def test_constant_is_counted_by_column(self) -> None:
        """(0,0)(0,0)(0,0) 是 3 个零括号（按列数），不是 6 个 0。

        纯零列矩阵走的是「本仓库定义直接得出」那条路（见下一个用例），
        所以这里断言的是「零括号**计数** 3」+「序数 3」。
        """
        res = bc.ordinal_of("(0,0)(0,0)(0,0)[3]")
        self.assertEqual(trailing_zero_columns(res.matrix), 3)
        self.assertEqual(res.source, "TrailingZeroColumns")
        self.assertEqual(res.full_text(), "3")
        self.assertEqual(res.constant, 0)

    def test_pure_successor_uses_our_rule_not_basmat_number(self) -> None:
        """纯零列矩阵：序数由**本仓库定义**得出（k 个零列 = k），不用 basmat 报的数。

        为什么不能用：basmat 对这类矩阵不打 `Ord`，只在最后打一行
        `Finished. Calculated number = N`，而实测 N **就是传进去的 n** ——
        决定性证据：``(0)[5][5]`` 会被 basmat 解析成 n=55，它就打印 55。
        （最初我们由 ``(0)(0)(0)[3] → 3`` 误以为 N 是序数，那只是 n=3 与序数 3 的巧合。）
        """
        cases = [("(0)[3]", "1"), ("(0)(0)[3]", "2"),
                 ("(0)(0)(0)[3]", "3"), ("(0)(0)(0)(0)[3]", "4")]
        for ini, want in cases:
            with self.subTest(ini=ini):
                res = bc.ordinal_of(ini)
                self.assertEqual(res.source, "TrailingZeroColumns")
                self.assertEqual(res.full_text(), want)
                self.assertEqual(res.constant, 0)
                # 把陷阱本身也钉住：basmat 报的数就是 n（= 3），与序数无关。
                self.assertEqual(res.trace.calculated_number, 3)

    def test_epsilon0(self) -> None:
        """(0,0)(1,1) = ε₀ —— 本仓库 Ordinal.hs 表示不出来，basmat 给 e_0。"""
        res = bc.ordinal_of("(0,0)(1,1)[3]")
        self.assertEqual(res.ord_text, "e_0")
        self.assertEqual(res.constant, 0)

    def test_beyond_notation_returns_unavailable_not_a_guess(self) -> None:
        """远超 ε₀ 的矩阵 basmat 也只给 G/B/Delta/C、不给 Ord —— 必须如实标 Unavailable。"""
        res = bc.ordinal_of(GOLDEN_INI, version=4)
        self.assertEqual(res.source, "Unavailable")
        self.assertIsNone(res.ord_text)
        self.assertIsNone(res.full_text())

    def test_required_steps_rule(self) -> None:
        """实测：-t T 打印 T+1 个节点，最后一个没详情；所以需要 k+1 步才拿得到 Ord。"""
        cols = cols_of("(0)(1)(2)(0)(0)[3]")
        k = trailing_zero_columns(cols)
        self.assertEqual(bc.required_steps(cols), k + 1)
        # 给少了（-t k）就拿不到 Ord……
        few = parse_trace(
            bc.run_basmat("(0)(1)(2)(0)(0)[3]", options=["-d", "-t", str(k)], timeout=120)
        )
        self.assertIsNone(few.limit_node)
        # ……给够（-t k+1）就有。
        enough = parse_trace(
            bc.run_basmat("(0)(1)(2)(0)(0)[3]", options=["-d", "-t", str(k + 1)], timeout=120)
        )
        self.assertIsNotNone(enough.limit_node)
        self.assertEqual(enough.limit_node.ord_text, "w^w")


@unittest.skipUnless(READY, SKIP_REASON)
class TrapTests(unittest.TestCase):
    """两个「看着像对、其实会算错」的坑 —— 都是实测中真踩到的，钉住防止回退。"""

    def test_basmat_standardness_differs_from_minbms(self) -> None:
        """(0)(0)(1)：本仓库 isBasicBMS 认为标准（Explore.exe 列它 = ω），
        basmat 认为**不**标准，于是不给 `Ord` —— 这与「超出记法范围」是两回事。"""
        for ini, fixture in [("(0)(0)(1)[3]", "not-standard-1row"),
                             ("(0,0)(0,0)(1,1)[3]", "not-standard-2row")]:
            with self.subTest(ini=ini):
                trace = parse_trace(
                    (FIXTURES / f"{fixture}.txt").read_text(encoding="utf-8")
                )
                self.assertIs(trace.is_standard, False)
                self.assertIsNone(trace.limit_node)
                res = bc.ordinal_from_trace(ini, trace)
                self.assertEqual(res.source, "Unavailable")

    def test_calculated_number_is_n_not_the_ordinal(self) -> None:
        """`Finished. Calculated number = N` 里的 N 就是 n。

        证据：`(0)[5]` → N=5；而 `(0)` 的序数是 1。把它当序数就会把 1 说成 5。
        """
        trace = parse_trace(bc.run_basmat("(0)[5]", options=["-d", "-t", "1"], timeout=300))
        self.assertEqual(trace.calculated_number, 5)
        res = bc.ordinal_from_trace("(0)[5]", trace)
        self.assertEqual(res.source, "TrailingZeroColumns")
        self.assertEqual(res.full_text(), "1")


@unittest.skipUnless(READY, SKIP_REASON)
class DecompositionAgreementTests(unittest.TestCase):
    """`G` / `B` / `Delta` 就是本仓库的好部 / 坏部 / 阶差向量 —— 实测**逐列相同**。

    这是「两个实现同源」的最强证据：只有「份数」差 1（见下一个类），分解方式完全一致。
    """

    CASES = [
        ("(0)(1)[3]", "empty", "(0)", "(0)"),
        ("(0)(1)(2)[3]", "(0)", "(1)", "(0)"),
        ("(0,0)(1,0)[3]", "empty", "(0,0)", "(0,0)"),
        ("(0,0)(1,1)[3]", "empty", "(0,0)", "(1,0)"),
        (GOLDEN_INI, "empty", "(0,0,0)(1,1,1)(2,1,0)", "(1,1,0)"),
    ]

    def test_good_bad_delta(self) -> None:
        for ini, g, b, d in self.CASES:
            with self.subTest(ini=ini):
                node = parse_trace(
                    bc.run_basmat(ini, options=["-d", "-t", "1"], timeout=300)
                ).initial
                self.assertEqual(node.detail["G"], g)
                self.assertEqual(node.detail["B"], b)
                self.assertEqual(node.detail["Delta"], d)

    def test_delta_matches_versions_md_golden(self) -> None:
        """不只看 basmat 自报的 Delta：用 VERSIONS.md 的黄金值独立反推 Δ 再核对。

        黄金值 = 好部 + 若干块坏部，相邻两块逐列相减就是 Δ。
        """
        golden = cols_of(GOLDEN_BM4)  # 9 列 = 3 块 × 3 列
        self.assertEqual(len(golden), 9)
        b0, b1 = golden[0:3], golden[3:6]
        delta_from_golden = tuple(
            tuple(y - x for x, y in zip(c0, c1)) for c0, c1 in zip(b0, b1)
        )
        self.assertEqual(
            format_matrix(delta_from_golden), "(1,1,0)(1,1,0)(1,1,0)",
            "同一份 Δ 应当逐列相同",
        )
        node = parse_trace(
            bc.run_basmat(GOLDEN_INI, options=["-d", "-t", "1"], timeout=300)
        ).initial
        self.assertEqual(node.detail["Delta"], "(1,1,0)")

    def test_decomposition_matches_minbms_definition(self) -> None:
        """坏根 = 末列最下方非零项的父项所在列 —— 用 README 的定义独立验证一遍。

        ``(0,0,0)(1,1,1)(2,1,0)(1,1,1)``：末列 (1,1,1) 最下方的非零项在第 1 行（值 1），
        它的父项是左边第一个比它小的、即第 0 列 (0,0,0) → 坏根在第 0 列
        → 好部为空、坏部 = 前 3 列（含坏根，不含末列）。与 basmat 的 G/B 完全一致。
        """
        node = parse_trace(
            bc.run_basmat(GOLDEN_INI, options=["-d", "-t", "1"], timeout=300)
        ).initial
        self.assertEqual(node.detail["G"], "empty")
        self.assertEqual(node.detail["B"], "(0,0,0)(1,1,1)(2,1,0)")
        self.assertEqual(format_matrix(node.matrix[-1:]), "(1,1,1)")


@unittest.skipUnless(READY, SKIP_REASON)
class CopyCountOffsetTests(unittest.TestCase):
    """【最关键的一条】实测：basmat 的 ``[n]`` = 好部 + **(n+1) 份**坏部。

    本仓库 README 的约定是「``[n]`` = 好部 + **n** 份坏部」，所以

        basmat[n]  ≡  MinBMS[n+1]

    证据用的是 **VERSIONS.md 里本仓库自己锁死的黄金值**：basmat 的下一状态
    前 9 列与黄金值**逐列相同**，只是又多复制了一块。
    """

    BLOCK_COLS = 3

    def test_bm4_golden_is_a_prefix_of_basmat_next_state(self) -> None:
        state = next_state(GOLDEN_INI, version=4)
        blocks = blocks_of(state, self.BLOCK_COLS)
        self.assertEqual(len(blocks), 4, "n=3 → basmat 复制 4 份（本仓库是 3 份）")
        self.assertEqual(
            format_matrix(state[:9]), GOLDEN_BM4,
            "basmat 的前 9 列应当逐列等于 VERSIONS.md 里 BM4 的黄金值（= 本仓库的 n=3）",
        )
        self.assertEqual(blocks[0], "(0,0,0)(1,1,1)(2,1,0)")
        self.assertEqual(blocks[1], "(1,1,0)(2,2,1)(3,2,0)")
        self.assertEqual(blocks[3], "(3,3,0)(4,4,1)(5,4,0)")

    def test_bm33_golden_is_a_prefix_of_basmat_next_state(self) -> None:
        state = next_state(GOLDEN_INI, version="3.3")
        blocks = blocks_of(state, self.BLOCK_COLS)
        self.assertEqual(len(blocks), 4)
        self.assertEqual(
            format_matrix(state[:9]), GOLDEN_BM33,
            "basmat 的前 9 列应当逐列等于 VERSIONS.md 里 BM3.3 的黄金值",
        )
        self.assertEqual(blocks[1], "(1,1,0)(2,2,1)(3,1,0)", "BM3.3 少加的那一处 Δ")

    def test_version_number_mapping_is_real(self) -> None:
        """-v 4 与 -v 3.3 必须真的不同 —— 否则「版本号映射」这件事根本没被验证到。"""
        self.assertNotEqual(
            format_matrix(next_state(GOLDEN_INI, version=4)),
            format_matrix(next_state(GOLDEN_INI, version="3.3")),
        )
        self.assertEqual(bc.BASMAT_VERSIONS["4"], "BM4")
        self.assertEqual(bc.BASMAT_VERSIONS["3.3"], "BM3.3")

    def test_single_row_omega(self) -> None:
        """(0)(1) 是好部为空的极限：n=3 → 4 份坏部 (0)。"""
        state = next_state("(0)(1)[3]")
        self.assertEqual(format_matrix(state), "(0)(0)(0)(0)")

    def test_epsilon0_expansion(self) -> None:
        """ε₀ 也一样：B=(0,0)、Δ=(1,0)、4 块（k=0..3）。"""
        state = next_state("(0,0)(1,1)[3]")
        self.assertEqual(format_matrix(state), "(0,0)(1,0)(2,0)(3,0)")


@unittest.skipUnless(READY, SKIP_REASON)
class ReferenceImplementationTests(unittest.TestCase):
    """`tools/bms_reference.py`（独立实现）与 basmat 对拍。

    只对拍两件**数学事实**：

    * 展开：`bms_reference.expand(M, n+1)` 必须等于 basmat `M[n]` 的下一步
      （`tools/README.md` 事实 5：basmat[n] ≡ 本仓库[n+1]）；
    * 标准性：`bms_reference.is_standard(M)` 必须等于 basmat 的 `Standard.` / `Not standard`。
    """

    def test_expansion_matches_basmat_next_state(self) -> None:
        from bms_reference import expand

        cases = ["(0)(1)", "(0)(1)(2)", "(0,0)(1,1)", "(0,0)(1,1)(2,0)(1,0)",
                 "(0,0,0)(1,1,1)(2,1,0)(1,1,1)"]
        for text in cases:
            for n in (1, 2, 3):
                ini = f"{text}[{n}]"
                cols, _ = parse_matrix(text)
                ours = format_matrix(expand(cols, n + 1))
                theirs = format_matrix(next_state(ini))
                with self.subTest(text=text, n=n):
                    self.assertEqual(ours, theirs)

    def test_standardness_matches_basmat(self) -> None:
        from bms_reference import is_standard
        from standardness import parse_standardness

        # 固定的样品（来自 `Explore.exe 2 4 4`，含标准与非标准）——
        # 不依赖任何落盘文件；判据一律现场问 basmat。
        matrices = [
            "(0,0)(1,1)",
            "(0,0)(1,1)(1,0)",
            "(0,0)(1,1)(1,1)",
            "(0,0)(1,1)(2,0)",
            "(0,0)(1,1)(2,1)",
            "(0,0)(1,1)(2,2)",
            "(0,0)(1,1)(2,1)(1,0)",
            "(0,0)(1,1)(2,1)(2,0)",
            "(0,0)(0,0)(1,1)",
            "(0,0)(1,0)(1,1)",
            "(0,0)(1,0)(2,1)",
            "(0,0)(0,0)(0,0)(1,1)",
            "(0,0)(0,0)(1,0)(1,1)",
        ]
        entries = bc.run_batch([m + "[0]" for m in matrices], options="-d -t 1")
        for text, entry in zip(matrices, entries):
            want = parse_standardness(entry.stdout).standard is True
            cols, _ = parse_matrix(text)
            with self.subTest(matrix=text):
                self.assertEqual(is_standard(cols), want)


if __name__ == "__main__":
    unittest.main(verbosity=2)

