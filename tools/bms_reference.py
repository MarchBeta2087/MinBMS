"""BMS 的**独立参考实现**：展开（BM4）与「下探式」标准性判定。

这个模块是**重新写的**，不移植任何 basmat 代码（见 [../CONTRIBUTING.md](../CONTRIBUTING.md) 铁律二
与 [../docker/README.md](../docker/README.md) 的许可证一节）。它做两件事：

1. **展开 `expand`**：按 README/VERSIONS.md 的 BM4 定义实现基本列展开。
   与 `BashicuMatrix.hs` 的 `expandBMS` 等价（用 basmat 与 VERSIONS.md 的黄金值对拍过）。
2. **标准性 `is_standard`**：README 的三条只是**必要条件**（本项目叫 `isBasicBMS`），
   真正的标准性用一个数学定义来判 ——

   > **标准集 = 从「极限」种子出发、反复做基本列展开所能到达的矩阵。**

   其中种子是 `(0,...,0)(1,...,1)`（行数比目标多 1，即该行数系统的极限）。
   把种子的第一次展开结果（「对角」矩阵）当作起点，对它们做展开闭包；
   目标（末尾补一行 0 之后）落在闭包里 ⇔ 标准。

   这个定义是**实测锁定**的：对 `Explore.exe 2 4 4` 的 83 个矩阵，
   闭包判定与 basmat 的 `Standard.` / `Not standard` **83/83 一致**；
   1 行的 341 个候选也完全一致（见 [STANDARDNESS.md](STANDARDNESS.md)）。

### 为什么是「闭包」而不是「把递降序列列出来」

basmat 打印的 `Decreasing sequence` 是**目标引导的搜索路径**（随目标变化、会跳项），
不是标准集全集（见 STANDARDNESS.md）。但「标准 ⇔ 在种子的展开闭包里」是等价的数学刻画，
而且**只往下走**（展开让序数变小），所以可以直接生成、直接判成员。

### 可靠性

闭包只会生成**标准**矩阵，所以：

* 判「标准」永远不会错（不会把非标准说成标准）；
* 判「非标准」在**界够大**时才对；界不够大只会漏掉标准矩阵（假阴性）。
  默认界按目标规模自动放大，`is_standard` 也可以手动给更宽的界。

用法::

    from bms_reference import expand, is_standard, standard_set
    expand(((0,0),(1,1)), 2)              # 展开
    is_standard(((0,0),(1,1),(2,0)))      # -> bool
    standard_set(rows=1, max_cols=5, max_val=3)   # 生成标准集
"""

from __future__ import annotations

from typing import Iterable, Iterator

#: 矩阵：按列存放，每列自**上**而下（与 basmat 的 `(a1, a2, ...)` 一致）。
Matrix = tuple[tuple[int, ...], ...]


# ---------------------------------------------------------------------------
# 基本结构：父项 / 坏根 / 阶差 / 提升
# ---------------------------------------------------------------------------


def pad(matrix: Matrix) -> Matrix:
    """把各列右侧补 0 到统一行数（与 `initBMS` 的约定一致）。"""
    rows = max((len(c) for c in matrix), default=0)
    return tuple(c + (0,) * (rows - len(c)) for c in matrix)


def rows_of(matrix: Matrix) -> int:
    return max((len(c) for c in matrix), default=0)


def value_at(matrix: Matrix, x: int, y: int) -> int:
    """第 x 列第 y 行的值（越界为 0）。"""
    if 0 <= x < len(matrix) and 0 <= y < len(matrix[x]):
        return matrix[x][y]
    return 0


def father(matrix: Matrix, x: int, y: int) -> int | None:
    r"""(x, y) 的父项所在列。

    * 第 0 行：左边最近的更小项；
    * 第 y>0 行：还要求该列落在**上一行 y-1** 的父项链上（祖先，含自身）。
    """
    if y == 0:
        for p in range(x - 1, -1, -1):
            if value_at(matrix, p, y) < value_at(matrix, x, y):
                return p
        return None

    # 上一行 y-1 的祖先链（从 x 出发，含 x）
    chain: set[int] = set()
    cur: int | None = x
    while cur is not None:
        chain.add(cur)
        cur = father(matrix, cur, y - 1)
    for p in range(x - 1, -1, -1):
        if value_at(matrix, p, y) < value_at(matrix, x, y) and p in chain:
            return p
    return None


def bottom_most_nonzero_row(matrix: Matrix) -> int | None:
    """末列中从下往上数第一个非零项所在行；末列全零时返回 ``None``。"""
    if not matrix:
        return None
    last = matrix[-1]
    for y in range(len(last) - 1, -1, -1):
        if last[y] != 0:
            return y
    return None


def bad_root(matrix: Matrix) -> int | None:
    """坏根所在列（末列最底非零行的父项）。"""
    if not matrix:
        return None
    t = bottom_most_nonzero_row(matrix)
    if t is None:
        return None
    return father(matrix, len(matrix) - 1, t)


def difference_vector(matrix: Matrix) -> tuple[int, ...]:
    """阶差向量 Δ：末列 − 坏根列（仅最底非零行 t 之上；t 及以下为 0）。"""
    r = bad_root(matrix)
    if r is None:
        return tuple(0 for _ in range(rows_of(matrix)))
    t = bottom_most_nonzero_row(matrix)
    assert t is not None
    last = matrix[-1]
    root = matrix[r]
    return tuple(
        (last[y] - root[y]) if y < t else 0 for y in range(len(last))
    )


def adds_delta(matrix: Matrix, root: int, x: int, y: int) -> bool:
    """BM4：坏部中位置 (x, y) 是否加 Δ。

    判定：坏根列上的 (root, y) 是否落在 (x, y) 在**第 y 行**的祖先链上（含自身）。
    """
    cur: int | None = x
    while cur is not None:
        if cur == root:
            return True
        cur = father(matrix, cur, y)
    return False


# ---------------------------------------------------------------------------
# 展开
# ---------------------------------------------------------------------------


def expand(matrix: Matrix, copies: int) -> Matrix:
    """BM4 展开：`[copies]` = 好部 + `copies` 份坏部（第 k 份加 k·Δ）。"""
    if copies < 0:
        raise ValueError("copies 不能为负")
    m = pad(matrix)
    if not m:
        return ()
    # 规则 2：末列全零（后继序数）→ 删去末列
    if all(v == 0 for v in m[-1]):
        return m[:-1]
    # 规则 3：保留好部，复制坏部
    root = bad_root(m)
    assert root is not None
    delta = difference_vector(m)
    good = m[:root]
    bad = m[root : len(m) - 1]  # 坏根 .. 末列之前（**不含末列**）
    out: list[tuple[int, ...]] = list(good)
    for k in range(copies):
        for xi, col in enumerate(bad):
            x = root + xi
            out.append(
                tuple(
                    col[y] + k * delta[y] if adds_delta(m, root, x, y) else col[y]
                    for y in range(len(col))
                )
            )
    return tuple(out)


# ---------------------------------------------------------------------------
# 标准性：种子展开闭包
# ---------------------------------------------------------------------------


def seed(rows: int) -> Matrix:
    """行数为 ``rows`` 的 BMS 系统的「极限」种子 `(0,...,0)(1,...,1)`。

    注意：调用方给的 `rows` 应比目标**多 1**（目标 r 行 → 种子 r+1 行）。
    """
    return ((0,) * rows, (1,) * rows)


def reachable(
    rows: int,
    max_cols: int,
    max_val: int,
    max_copies: int,
) -> Iterator[Matrix]:
    """生成 ``rows`` 行的标准矩阵，直到超出界。

    做法：种子 ``(0,...,0)(1,...,1)``（``rows+1`` 行）先展开一次得到「对角」矩阵，
    投影回 ``rows`` 行；之后直接在 ``rows`` 行里做展开闭包
    （对最底行全零的矩阵，``rows+1`` 行展开与 ``rows`` 行展开只差一个全零行，
    所以投影后等价 —— 这也正是种子要多一行的原因）。

    **只生成标准矩阵**；界越大越全，但永远不会生成非标准矩阵。
    """
    if rows < 1:
        return
    seen: set[Matrix] = set()
    stack: list[Matrix] = []

    def push(m: Matrix) -> None:
        if len(m) > max_cols or any(v > max_val for c in m for v in c):
            return
        if m not in seen:
            seen.add(m)
            stack.append(m)

    # 种子比目标多一行；展开一次后最底行恒为 0，投影掉。
    top = seed(rows + 1)
    for n in range(1, max_copies + 1):
        push(_drop_last_row(expand(top, n)))

    while stack:
        cur = stack.pop()
        for n in range(1, max_copies + 1):
            push(expand(cur, n))

    yield from seen


def _drop_last_row(m: Matrix) -> Matrix:
    """去掉最底一行（只用于种子展开结果，其最底一行恒为 0）。"""
    return tuple(c[:-1] for c in m)


def standard_set(rows: int, max_cols: int, max_val: int, max_copies: int | None = None) -> set[Matrix]:
    """``reachable`` 的集合形式。"""
    if max_copies is None:
        max_copies = max_cols + 1
    return set(reachable(rows, max_cols, max_val, max_copies))


def default_bounds(matrix: Matrix) -> tuple[int, int, int]:
    """按目标规模给一组「通常够用」的闭包界（列数 / 元素上界 / 复制次数）。

    实测：对 2 行、≤4 列、≤4 的矩阵（`Explore.exe 2 4 4` 的全部 83 个），
    `(n+3, v+4, n+1)` 的界能给出 83/83；更大的行数/列数可能需要手动放大界
    （放大只会更慢，不会把非标准判成标准）。
    """
    r = rows_of(matrix)
    n = len(matrix)
    v = max((val for c in matrix for val in c), default=0)
    return (n + 3, v + 4, n + 1)


#: 闭包搜索的节点上限（防卡死）。到了上限就当作「界不够」——宁可漏报不误报。
NODE_LIMIT = 300_000


def _closure_contains(
    rows: int, target: Matrix, max_cols: int, max_val: int, max_copies: int
) -> bool:
    """目标是否在种子展开闭包里（含提前退出与节点上限）。"""
    seen: set[Matrix] = set()
    stack: list[Matrix] = []

    def push(m: Matrix) -> bool:
        if len(m) > max_cols or any(v > max_val for c in m for v in c):
            return False
        if m not in seen:
            seen.add(m)
            stack.append(m)
        return m == target

    top = seed(rows + 1)
    for n in range(1, max_copies + 1):
        if push(_drop_last_row(expand(top, n))):
            return True
    while stack:
        if len(seen) > NODE_LIMIT:
            return False  # 界太小 / 太大，放弃（不误报为标准）
        cur = stack.pop()
        for n in range(1, max_copies + 1):
            if push(expand(cur, n)):
                return True
    return False


def is_standard(
    matrix: Matrix,
    max_cols: int | None = None,
    max_val: int | None = None,
    max_copies: int | None = None,
) -> bool:
    """判断 ``matrix`` 是否标准（标准集 = 种子展开闭包）。

    界不传时用 :func:`default_bounds`；想更快/更严可显式给界。
    **判 True 一定对；判 False 需要界够大**（界不够时会漏报，不会误报）。
    """
    m = pad(matrix)
    if not m:
        return True  # 空矩阵 = 0，标准
    r = rows_of(m)
    dc, dv, dk = default_bounds(m)
    max_cols = dc if max_cols is None else max_cols
    max_val = dv if max_val is None else max_val
    max_copies = dk if max_copies is None else max_copies
    return _closure_contains(r, m, max_cols, max_val, max_copies)
