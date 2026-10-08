"""basmat 客户端 —— 在 Docker 容器里调用 basmat，并把它「容器视角」的输入输出管起来。

只用标准库（与本仓库「零第三方依赖」的脾气一致：base/containers 之外什么都不用）。

容器与调用约定见 ``docker/README.md``，本模块与它一一对应：

* **单条查询**：``docker run --rm <image> <选项...> "<ini>"``
* **批量查询**：``docker run --rm -i --entrypoint basmat-batch <image>``，
  stdin 逐行一个 ``ini``。Windows / Docker Desktop 上每开一个容器要 0.3–1 秒，
  批量能把这一大块固定开销摊掉（搜索场景动辄上千条）。

矩阵一律用**按列**的元组表示：``((0, 0), (1, 1))`` 就是 ``(0,0)(1,1)``。
理由：本仓库 ``BashicuMatrix`` 也是按列存；而且「末尾有几个零括号」这种判断
（常数项！）必须按**列**数 —— ``(0,0)(0,0)(0,0)`` 是 **3** 个零括号，不是 6 个 0。
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from typing import Iterable, Sequence

# 镜像名与 docker/compose.yaml 里的 image 标签保持一致（可用环境变量覆盖）。
DEFAULT_IMAGE = os.environ.get("BASMAT_IMAGE", "minbms/basmat:4.0-f2f0125")

# 默认选项：-d 打开详细过程（**没有 -d 就没有 Ord 行**，实测）。
DEFAULT_OPTIONS = "-d"

# basmat 对**输入不合法**时只打印这一行 + 帮助，而**退出码仍然是 0**（实测！）。
# 所以判错不能只看 rc，必须也看这行。
INVALID_INPUT_MARK = "Error: invalid sequence of Bashicu matrix."

# basmat-batch 的框（见 docker/basmat-batch）：
#   === BEGIN <n> ===
#   <basmat 原始输出>
#   === END <n> rc=<rc> ===
_BEGIN_RE = re.compile(r"^=== BEGIN (\d+) ===$")
_END_RE = re.compile(r"^=== END (\d+) rc=(-?\d+) ===$")
_DONE_RE = re.compile(r"^=== DONE (\d+) ===$")

# `(0,0)(1,1)[3]` 里的列与 n
_COLUMN_RE = re.compile(r"\(([^()]*)\)")
_N_RE = re.compile(r"\[(\d+)\]")

# ---------------------------------------------------------------------------
# -d 输出里的行（全部由 tools/fixtures/ 里的**真实输出**锁定，见 tools/README.md）
# ---------------------------------------------------------------------------

#: 分隔线：44 个 `-`
_SECTION_RE = re.compile(r"^-{10,}$")
#: 节点行：`(0)(1)(2)[3]`；空矩阵时是 `[3]`
_NODE_RE = re.compile(r"^(?P<cols>(?:\(\s*\d+(?:\s*,\s*\d+)*\s*\))*)\[(?P<n>\d+)\]\s*$")
#: 节点详情：`Ord = w^w` / `G = (0)` / `Delta = (0)` / `C = (1)` / `f(n) = 3`
_KEYVAL_RE = re.compile(r"^(Ord|G|B|Delta|C|f\(n\))\s*=\s*(.*?)\s*$")
#: 三种停止原因
_STOP_STEP_RE = re.compile(r"^Maximum step of calculation (\d+) has reached\.$")
_STOP_LEN_RE = re.compile(r"^Length of sequence exceeds (\d+) at next step\.$")
_FINISHED_RE = re.compile(r"^Finished\. Calculated number = (\d+)$")


class BasmatError(RuntimeError):
    """调用 basmat（或 Docker）失败。"""


# ---------------------------------------------------------------------------
# 矩阵（按列）
# ---------------------------------------------------------------------------

#: 矩阵：按列存放，每列是一个自下（第 1 行）向上（第 n 行）的非负整数元组。
Matrix = tuple[tuple[int, ...], ...]


def parse_matrix(text: str) -> tuple[Matrix, int | None]:
    """把 ``"(0,0)(1,1)[3]"`` 解析成 ``(((0, 0), (1, 1)), 3)``。

    允许：
      * **空矩阵**：``""`` 或 ``"()"`` → ``((), None)``。这不是凑数 ——
        基本列里真的会出现它（``(0,0)(1,0)[0]`` 的好部为空就是 ``∅``，
        ``Explore.hs`` 把它打成空串），README 也写作 ``(∅) = 0``；
      * 省略 ``[n]``（返回 ``None``，与 basmat 一致：默认 2）；
      * 列内元素个数不一致（BMS 允许省略各列末尾的 0，
        与 ``initBMS`` 的输入约定相同）；
      * 列内、列间有空白。

    不允许（直接报错，不猜）：
      * 空列（``(0,)`` / ``(,0)`` / ``(0)()``）、非整数、负数、
        ``[n]`` 之外的方括号内容、括号外的多余字符。
    """
    s = text.strip()
    if s == "" or s == "()":
        return (), None

    n: int | None = None
    m = _N_RE.search(s)
    if m:
        n = int(m.group(1))
        s = s[: m.start()] + s[m.end() :]


    # 剩下的部分必须由 (…) 组成
    leftover = _COLUMN_RE.sub("", s)
    if leftover.strip():
        raise ValueError(f"无法解析的矩阵表达式：{text!r}（多余内容 {leftover!r}）")

    cols: list[tuple[int, ...]] = []
    for body in _COLUMN_RE.findall(s):
        if body.strip() == "":
            raise ValueError(f"空的列：{text!r}")
        vals: list[int] = []
        for item in body.split(","):
            item = item.strip()
            if not item.isdigit():
                raise ValueError(f"列里的元素不是非负整数：{item!r}（{text!r}）")
            vals.append(int(item))
        cols.append(tuple(vals))
    return tuple(cols), n


def format_matrix(cols: Matrix, n: int | None = None) -> str:
    """``((0, 0), (1, 1))`` -> ``"(0,0)(1,1)"``；给了 ``n`` 则在末尾补 ``[n]``。"""
    body = "".join("(" + ",".join(str(v) for v in col) + ")" for col in cols)
    return body if n is None else f"{body}[{n}]"


def matrix_rows(cols: Matrix) -> int:
    """矩阵的行数（按最高的一列算）。空矩阵为 0。"""
    return max((len(col) for col in cols), default=0)


def pad_column(col: Sequence[int], rows: int) -> tuple[int, ...]:
    """把一列右侧补零到 ``rows`` 行（与 ``initBMS`` 的做法一致）。"""
    return tuple(col) + (0,) * (rows - len(col))


def pad_matrix(cols: Matrix, rows: int | None = None) -> Matrix:
    """把所有列右侧补零到统一行数（默认取该矩阵的行数）。"""
    rows = matrix_rows(cols) if rows is None else rows
    return tuple(pad_column(col, rows) for col in cols)


def is_zero_column(col: Sequence[int]) -> bool:
    """是不是「零括号」（全零列）。"""
    return all(v == 0 for v in col)


def trailing_zero_columns(cols: Matrix) -> int:
    """末尾**连续**全零列的个数 —— 也就是这个矩阵对应的序数里的常数项。

    这里刻意按「列」数，不按数字个数：

        (0,0)(0,0)(0,0)  -> 3   （三个零括号）
        (0,0)(1,1)(0,0)  -> 1
        ()               -> 0
    """
    k = 0
    for col in reversed(cols):
        if not is_zero_column(col):
            break
        k += 1
    return k


def strip_trailing_zero_columns(cols: Matrix) -> Matrix:
    """去掉末尾的全零列（留下极限部分）。"""
    return cols[: len(cols) - trailing_zero_columns(cols)] if cols else cols


# ---------------------------------------------------------------------------
# 调用容器
# ---------------------------------------------------------------------------


def docker_available() -> bool:
    """本机有没有可用的 docker（没装 / 引擎没起 → False，不抛异常）。"""
    if shutil.which("docker") is None:
        return False
    try:
        p = subprocess.run(
            ["docker", "info", "--format", "{{.OSType}}"],
            capture_output=True,
            text=True,
            timeout=60,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return p.returncode == 0


def image_exists(image: str = DEFAULT_IMAGE) -> bool:
    """本地有没有该镜像（没有就先 `docker compose -f docker/compose.yaml build`）。"""
    try:
        p = subprocess.run(
            ["docker", "image", "inspect", image],
            capture_output=True,
            text=True,
            timeout=120,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return p.returncode == 0


def _split_options(options: str | Sequence[str]) -> list[str]:
    """选项既可直接给字符串（按空白拆）也可给列表。"""
    return options.split() if isinstance(options, str) else list(options)


def run_basmat(
    ini: str,
    options: str | Sequence[str] = DEFAULT_OPTIONS,
    image: str = DEFAULT_IMAGE,
    timeout: float | None = 300,
) -> str:
    """跑一条 basmat，返回 stdout（退出码非 0 则抛 ``BasmatError``）。"""
    argv = ["docker", "run", "--rm", image, *_split_options(options), ini]
    try:
        p = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError) as exc:
        raise BasmatError(f"调用 docker 失败：{exc}") from exc
    if p.returncode != 0:
        raise BasmatError(
            f"basmat 退出码 {p.returncode}：{ini!r}\nstderr: {p.stderr.strip()}"
        )
    # rc == 0 也可能是「输入非法」—— 实测 basmat 对非法输入照样退出 0。
    if INVALID_INPUT_MARK in p.stdout:
        raise BasmatError(f"basmat 认为输入非法：{ini!r}")
    return p.stdout


@dataclass(frozen=True)
class BatchEntry:
    """批处理里的一条：输入 + 原始输出 + 退出码。"""

    ini: str
    stdout: str
    rc: int


def _check_batch_ini(ini: str) -> None:
    """批处理把每条 ini 当成**一个**参数传（不做 shell 拆词），所以限定得死一点。"""
    if not ini or ini != ini.strip():
        raise ValueError(f"ini 首尾不能有空白：{ini!r}")
    if any(c.isspace() for c in ini):
        raise ValueError(f"ini 里不能有空白：{ini!r}")
    if ini.startswith("-"):
        raise ValueError(f"ini 不能以 - 开头（会被 basmat 当成选项）：{ini!r}")


def run_batch(
    inis: Iterable[str],
    options: str | Sequence[str] = DEFAULT_OPTIONS,
    image: str = DEFAULT_IMAGE,
    timeout: float | None = 3600,
) -> list[BatchEntry]:
    """一次容器启动跑多条查询。

    返回顺序与 ``inis`` 一致；其中空的 / 以 ``#`` 开头的输入会被跳过（与
    ``docker/basmat-batch`` 的行为一致），因此长度可能小于输入条数。

    一条失败**不会**终止整批，失败那条的 ``rc`` 非 0（basmat 的输出仍在 ``stdout`` 里）。
    """
    queries = [q for q in inis if q.strip() and not q.lstrip().startswith("#")]
    for q in queries:
        _check_batch_ini(q)
    if not queries:
        return []

    argv = [
        "docker",
        "run",
        "--rm",
        "-i",
        "-e",
        f"BASMAT_ARGS={' '.join(_split_options(options))}",
        "--entrypoint",
        "basmat-batch",
        image,
    ]
    stdin_text = "".join(q + "\n" for q in queries)
    try:
        p = subprocess.run(
            argv, input=stdin_text, capture_output=True, text=True, timeout=timeout
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise BasmatError(f"调用 docker 失败：{exc}") from exc
    if p.returncode != 0:
        raise BasmatError(
            f"basmat-batch 退出码 {p.returncode}\nstderr: {p.stderr.strip()}"
        )
    return _parse_batch_output(p.stdout, queries)


def _parse_batch_output(text: str, queries: list[str]) -> list[BatchEntry]:
    """按 ``=== BEGIN/END/DONE ===`` 切段；段数必须与输入条数一致，否则报错（不猜）。"""
    entries: list[BatchEntry] = []
    stdout_lines: list[str] = []
    rc: int | None = None
    saw_done = False
    in_block = False

    for line in text.splitlines():
        m_begin = _BEGIN_RE.match(line)
        if m_begin:
            if in_block:
                raise BasmatError(f"批处理输出格式意外：重复的 BEGIN（{line!r}）")
            in_block = True
            stdout_lines = []
            rc = None
            continue
        m_end = _END_RE.match(line)
        if m_end:
            idx = int(m_end.group(1))
            if not in_block or idx != len(entries) + 1:
                raise BasmatError(f"批处理输出格式意外：段号不连续（{line!r}）")
            if len(entries) >= len(queries):
                raise BasmatError("批处理输出的段数多于输入条数")
            rc = int(m_end.group(2))
            entries.append(
                BatchEntry(queries[len(entries)], "\n".join(stdout_lines), rc)
            )
            in_block = False
            continue
        if _DONE_RE.match(line):
            saw_done = True
            continue
        stdout_lines.append(line)

    if not saw_done:
        raise BasmatError("批处理输出里没有 === DONE ===，容器可能被提前杀死")
    if len(entries) != len(queries):
        raise BasmatError(f"批处理输出了 {len(entries)} 段，但输入有 {len(queries)} 条")
    return entries


# ---------------------------------------------------------------------------
# 解析 -d 的输出（「轨迹」）
# ---------------------------------------------------------------------------
#
# 下面这些规则**全部来自实测**（证据在 tools/fixtures/，结论在 tools/README.md）：
#
#   1. `-d` 的每个节点是「一行矩阵 + 可选的详情块」；详情块里 `Ord` 一行**只有极限节点才有**
#      （末列全零的后继节点不打印 Ord）。
#   2. `G` / `B` / `Delta` 就是好部 / 坏部 / 阶差向量，与本仓库 BashicuMatrix.hs 的定义**逐列相同**。
#   3. `-t T` 是「最多走 T 步」：会打印 T+1 个节点，**最后一个（被步数上限截住的那个）是光秃秃的**，
#      没有详情、也没有 Ord。
#   4. 因此：若初始矩阵末尾有 k 个全零列，必须给 `-t (k+1)` 才能让极限节点落在「有详情」的位置。
#   5. 纯后继（全零）矩阵没有 Ord，但会以 `Finished. Calculated number = N` 收尾，N 就是序数。
#   6. 输入非法时打印 `Error: invalid sequence of Bashicu matrix.`，**退出码仍是 0**。


@dataclass(frozen=True)
class Node:
    """`-d` 轨迹里的一个节点。"""

    matrix: Matrix
    n: int
    ord_text: str | None
    detail: dict[str, str]


@dataclass(frozen=True)
class Trace:
    """一次 `basmat -d` 的完整结构。"""

    nodes: list[Node]
    stop: str | None
    calculated_number: int | None
    is_standard: bool | None
    raw: str

    @property
    def initial(self) -> Node:
        return self.nodes[0]

    @property
    def limit_node(self) -> Node | None:
        """第一个带 `Ord` 的节点（= 去掉末尾全零列之后的那个「极限节点」）。"""
        for node in self.nodes:
            if node.ord_text is not None:
                return node
        return None


def parse_trace(text: str) -> Trace:
    """把 `basmat -d` 的输出解析成 :class:`Trace`。

    **不猜**：出现对不上的东西（例如没有任何节点行）就抛 :class:`BasmatError`。
    """
    if INVALID_INPUT_MARK in text:
        raise BasmatError(f"basmat 认为输入非法：{INVALID_INPUT_MARK}")

    nodes: list[Node] = []
    current_detail: dict[str, str] = {}
    current_matrix: Matrix | None = None
    current_n = 0

    stop: str | None = None
    calculated_number: int | None = None
    is_standard: bool | None = None

    def flush() -> None:
        nonlocal current_matrix, current_detail, current_n
        if current_matrix is not None:
            nodes.append(
                Node(
                    matrix=current_matrix,
                    n=current_n,
                    ord_text=current_detail.get("Ord"),
                    detail=dict(current_detail),
                )
            )
        current_matrix, current_detail, current_n = None, {}, 0

    for line in text.splitlines():
        line = line.rstrip()
        if _SECTION_RE.match(line.strip()):
            continue
        m_node = _NODE_RE.match(line.strip())
        if m_node:
            flush()
            cols, _ = parse_matrix(m_node.group("cols"))
            current_matrix = cols
            current_n = int(m_node.group("n"))
            continue
        m_kv = _KEYVAL_RE.match(line.strip())
        if m_kv and current_matrix is not None:
            current_detail[m_kv.group(1)] = m_kv.group(2)
            continue
        if stop is None:
            if _STOP_STEP_RE.match(line) or _STOP_LEN_RE.match(line):
                stop = line
                continue
            m_fin = _FINISHED_RE.match(line)
            if m_fin:
                stop = line
                calculated_number = int(m_fin.group(1))
                continue
        if line.endswith("is standard.") or line == "Standard.":
            is_standard = True
        elif line.startswith("Not standard") or line == "Not standard":
            # 实测 basmat 还会给理由，例如：
            #   `Not standard because it is (0)(0)(0)...`
            # 所以只比 `"Not standard."` 会漏掉 —— 用前缀判断。
            is_standard = False
    flush()

    if not nodes:
        raise BasmatError(f"没解析出任何节点行，输出是：\n{text}")
    return Trace(
        nodes=nodes,
        stop=stop,
        calculated_number=calculated_number,
        is_standard=is_standard,
        raw=text,
    )


# ---------------------------------------------------------------------------
# 高层封装：拿一个矩阵的序数
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Ordinal:
    """basmat 给出的一个矩阵的序数。

    :attr:`ord_text` 是**极限部分**的序数（basmat 原样打印的文本，如 ``w^w`` / ``e_0``），
    :attr:`constant` 是**需要补回**的常数项（= 末尾全零列的个数）。
    完整序数 = :attr:`ord_text` ``+`` :attr:`constant`，用 :meth:`full_text` 拿到现成的字符串。

    为什么要补：basmat 每走过一个全零末列就把它摘掉（那是一个后继步），
    于是它打印的 `Ord` 里**不含**这些 +1。实测：``(0)(1)(2)(0)(0)[3]`` 打出
    ``Ord = w^w``，而真正的序数是 ω^ω + 2。

    **两个例外**：

    * :attr:`source` 为 ``TrailingZeroColumns`` 时（所有列都是零列），basmat 不打 `Ord`，
      序数由本仓库定义直接得出（k 个零列 = k），此时 :attr:`ord_text` 已经是完整值、
      :attr:`constant` 为 0；
    * :attr:`source` 为 ``Unavailable`` 时 basmat 也给不出序数（远超它的记法范围），
      :attr:`ord_text` 为 ``None``。

    想知道「末尾有几个零括号」请直接用 :func:`trailing_zero_columns`（那是矩阵的属性，
    与取值口径无关）。
    """

    ini: str
    matrix: Matrix
    constant: int
    ord_text: str | None
    source: str
    #: "Ord"（basmat 打印的 Ord）
    #: / "TrailingZeroColumns"（纯零列矩阵，由本仓库定义直接得出）
    #: / "Unavailable"（basmat 也给不出）
    steps_used: int
    cmd: str
    trace: Trace

    def full_text(self, constant_symbol: str = "") -> str | None:
        """完整序数的文本；常数直接贴在后面（如 ``w^w + 2``）。

        basmat 也给不出序数时（:attr:`ord_text` 为 ``None``）返回 ``None`` ——
        「也不知道」是一个必须如实传达的结果，不能拿别的东西顶替。
        """
        if self.ord_text is None:
            return None
        if self.constant == 0:
            return self.ord_text
        if constant_symbol:
            return f"{self.ord_text} + {constant_symbol}{self.constant}"
        return f"{self.ord_text} + {self.constant}"


def required_steps(cols: Matrix) -> int:
    """要让极限节点落在「有详情」的位置，需要给 basmat 的 `-t` 值。

    实测规则（见 tools/README.md）：末尾有 k 个全零列时给 ``-t (k+1)``。
    全零矩阵（k 就是总列数）也走同一条公式，只是 basmat 会提前
    `Finished. Calculated number = k` 收尾。
    """
    return trailing_zero_columns(cols) + 1


def ordinal_from_trace(
    ini: str, trace: Trace, cmd: str = "", steps_used: int = 0
) -> Ordinal:
    """由一条**已经跑好的**轨迹构造 :class:`Ordinal`（批处理时用，避免重复开容器）。

    ``cmd`` 只作证据留痕，请传入**真正执行的那条命令**（批处理时是整批的命令）。
    """
    cols, _ = parse_matrix(ini)
    # 有 Ord：极限节点的序数 + 被摘掉的全零列（常数项）
    limit = trace.limit_node
    if limit is not None and limit.ord_text is not None:
        return Ordinal(
            ini=ini,
            matrix=cols,
            constant=trailing_zero_columns(cols),
            ord_text=limit.ord_text,
            source="Ord",
            steps_used=steps_used,
            cmd=cmd,
            trace=trace,
        )
    # 纯后继（所有列都是零列）矩阵：basmat 的 -d 输出里**没有 Ord**，
    # 只会在最后打一行 `Finished. Calculated number = N`。
    #
    # ★ 实测：那个 N **就是传进去的 n**，根本不是序数 ——
    #   `(0)[5][5]`（被解析成 n=55）→ `Calculated number = 55`；
    #   `(0)(0)[7]` → 7；`(0,0)(0,0)[9]` → 9。
    #   最初我们从 `(0)(0)(0)[3] → 3` 误以为「N 就是序数」，那只是 n=3 与序数 3 的巧合，
    #   换一个 n 或换一个矩阵长度立刻露馅。所以**不能用它**。
    #
    # 这种矩阵的序数由本仓库 README 的展开规则 2 直接得出：每摘掉一个零列就 +1，
    # 于是「k 个零列」的序数就是 k（空矩阵是 0）。来源如实标成 TrailingZeroColumns，
    # 免得它看起来像是 basmat 给的。
    if all(is_zero_column(col) for col in cols):
        return Ordinal(
            ini=ini,
            matrix=cols,
            constant=0,
            ord_text=str(len(cols)),
            source="TrailingZeroColumns",
            steps_used=steps_used,
            cmd=cmd,
            trace=trace,
        )
    # 既没有 Ord 也没有 Calculated number：basmat 对远超它记法范围的矩阵就是这样
    # （实测：(0,0,0)(1,1,1)(2,1,0)(1,1,1) 只给 G/B/Delta/C，不给 Ord）。
    # 这不是解析失败，而是「基线也不知道」—— 如实标 Unavailable，绝不拿别的东西顶替。
    return Ordinal(
        ini=ini,
        matrix=cols,
        constant=trailing_zero_columns(cols),
        ord_text=None,
        source="Unavailable",
        steps_used=steps_used,
        cmd=cmd,
        trace=trace,
    )


def ordinal_of(
    ini: str,
    version: str | int | None = None,
    opt: int | None = None,
    image: str = DEFAULT_IMAGE,
    timeout: float | None = 300,
    trace: Trace | None = None,
) -> Ordinal:
    """拿到 ``ini``（形如 ``"(0,0)(1,1)[3]"``）对应序数，并把常数项补回来。

    ``version`` 用 basmat 的写法（``4`` / ``"3.3"``）；``None`` 表示用 basmat 默认（4）。

    ``trace`` 可以传入已经跑好的轨迹（批处理时用），从而避免重复开容器。
    """
    cols, n = parse_matrix(ini)
    if n is None:
        n = 2  # 与 basmat 一致：不给 [n] 时默认 2
    steps = required_steps(cols)
    opts = list(_split_options(DEFAULT_OPTIONS)) + ["-t", str(steps)]
    if version is not None:
        opts = ["-v", str(version)] + opts
    if opt is not None:
        opts = ["-o", str(opt)] + opts
    ini_norm = format_matrix(cols, n)

    if trace is None:
        trace = parse_trace(run_basmat(ini_norm, options=opts, image=image, timeout=timeout))

    cmd = f'docker run --rm {image} {" ".join(opts)} "{ini_norm}"'
    return ordinal_from_trace(ini_norm, trace, cmd=cmd, steps_used=steps)
    # 既没有 Ord 也没有 Calculated number：basmat 对远超它记法范围的矩阵就是这样
    # （实测：(0,0,0)(1,1,1)(2,1,0)(1,1,1) 只给 G/B/Delta/C，不给 Ord）。
    # 这不是解析失败，而是「基线也不知道」—— 如实标 Unavailable，绝不拿别的东西顶替。
    return Ordinal(
        ini=ini_norm,
        matrix=cols,
        constant=trailing_zero_columns(cols),
        ord_text=None,
        source="Unavailable",
        steps_used=steps,
        cmd=cmd,
        trace=trace,
    )

#: basmat 的版本号写法 ⇄ 本仓库的版本名（实测对应关系见 tools/README.md）
BASMAT_VERSIONS: dict[str, str] = {"4": "BM4", "3.3": "BM3.3"}



