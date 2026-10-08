"""探测 basmat 的「标准性判定」—— 把它的**下探序列**原样抓下来。

basmat 判定一个 BMS 是否标准，用的不是局部条件，而是「下探」：

* 先确定一个**种子**——行数 = 目标行数 + 1 的底矩阵 ``(0,...,0)(1,...,1)``
  （也就是该行数 BMS 系统的极限）；
* 从种子出发，**按目标引导**生成一条递降序列（basmat 打印的
  ``Decreasing sequence from ... follows.``）；
* 目标落在序列上 ⇒ 标准；序列「跨过」目标 ⇒ 不标准，并给出下一个本该出现的矩阵。

本模块只做两件事：**解析**这段输出、把种子/序列/失败原因结构化；以及**枚举**
一批矩阵去跑 basmat，供后续找规律 / 对拍用。判定本身永远是 basmat 做的 ——
这里不重写、不猜测（与 [CONTRIBUTING.md](../CONTRIBUTING.md) 铁律三一致）。

用法（需要 Docker 与 ``minbms/basmat`` 镜像，见 ../docker/README.md）::

    python tools/standardness.py show "(0)(0)(1)"
    python tools/standardness.py seed "(0,0)(1,1)"
    python tools/standardness.py sweep --rows 1 --cols 5 --maxval 3 --out std-1row.jsonl

``sweep`` 的输出是 JSONL，每行一个矩阵；``--version`` 可换 basmat 版本做对拍。
"""

from __future__ import annotations

import argparse
import itertools
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from basmat_client import (  # noqa: E402
    DEFAULT_IMAGE,
    BasmatError,
    format_matrix,
    image_exists,
    matrix_rows,
    parse_matrix,
    run_batch,
)

# ---------------------------------------------------------------------------
# 解析「标准性判定」那一段
# ---------------------------------------------------------------------------

#: 种子行：`Decreasing sequence from (0,0)(1,1) follows.`
_RE_SEED = re.compile(r"^Decreasing sequence from (?P<seed>\(.*\)) follows\.$")
#: 直接判定：`(0)(1)(2) is standard.`
_RE_STD_DIRECT = re.compile(r"^(?P<m>\(.*\)) is standard\.$")
#: 检查开头：`Checking if (0)(0)(1) is standard or not.`
_RE_CHECKING = re.compile(r"^Checking if (?P<m>\(.*\)) is standard or not\.$")
#: 序列里的一行：``(0,0)(1,1)``（只由括号与数字组成的一整行）
_RE_SEQ_LINE = re.compile(r"^(?P<m>(?:\(\s*\d+(?:\s*,\s*\d+)*\s*\))+)$")
#: 全局失败：`Not standard because it is (0)(0)(0)...`
_RE_NOT_STD_GLOBAL = re.compile(r"^Not standard because it is (?P<z>.*?)\.{3}$")
#: 局部失败：`(0)(1)(3) is not standard because (0)(1)(2) does not decrease to the sequence.`
#: （实测有的理由末尾带句点、有的不带，比如 `not starting from (0,0)`，所以句点可选。）
_RE_NOT_STD_LOCAL = re.compile(
    r"^(?P<m>\(.*\)) is not standard because (?P<why>.*?)\.?$"
)


@dataclass(frozen=True)
class Probe:
    """basmat 对一个矩阵的标准性判定（结构化）。

    :attr:`standard`：``True`` 标准 / ``False`` 不标准 / ``None`` 没解析到判定行。
    :attr:`reason`：不标准时的原文理由（局部失败 / 全局失败 / 首列非零）。
    :attr:`seed`：递降序列的起点（极限矩阵）；直接判标准时为 ``None``。
    :attr:`sequence`：basmat 打印的递降序列（从大到小，不含目标本身的情形也有）。
    """

    matrix: str
    standard: bool | None
    reason: str | None
    seed: str | None
    sequence: tuple[str, ...]
    raw: str

    def to_json(self) -> dict:
        return asdict(self)


def parse_standardness(text: str) -> Probe | None:
    """把一段 basmat ``-d`` 输出里的标准性判定解析成 :class:`Probe`。

    解析不到任何判定行（例如没带 ``-d``）时返回 ``None`` —— **不猜**。
    """
    matrix: str | None = None
    standard: bool | None = None
    reason: str | None = None
    seed: str | None = None
    sequence: list[str] = []
    in_sequence = False

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if set(line) == {"-"} and len(line) >= 10:
            # 详情块开始，后面是展开信息，不属于标准性判定
            break

        m = _RE_CHECKING.match(line)
        if m:
            matrix = m.group("m")
            continue
        m = _RE_STD_DIRECT.match(line)
        if m:
            matrix = m.group("m")
            standard = True
            sequence = []
            continue
        if line == "Standard.":
            standard = True
            in_sequence = False
            continue
        m = _RE_SEED.match(line)
        if m:
            seed = m.group("seed")
            in_sequence = True
            continue
        m = _RE_NOT_STD_GLOBAL.match(line)
        if m:
            standard = False
            reason = m.group("z") + "..."
            in_sequence = False
            continue
        m = _RE_NOT_STD_LOCAL.match(line)
        if m:
            matrix = matrix or m.group("m")
            standard = False
            reason = m.group("why")
            in_sequence = False
            continue
        if in_sequence and _RE_SEQ_LINE.match(line):
            sequence.append(line)

    if matrix is None and standard is None:
        return None
    return Probe(
        matrix=matrix or "",
        standard=standard,
        reason=reason,
        seed=seed,
        sequence=tuple(sequence),
        raw=text,
    )


# ---------------------------------------------------------------------------
# 调用 basmat
# ---------------------------------------------------------------------------


def seed_for(ini: str) -> str:
    """由目标矩阵直接算出「种子」——行数 = 目标行数 + 1 的底矩阵。

    实测（见 tools/STANDARDNESS.md）：basmat 的下探总是从
    ``(0,...,0)(1,...,1)``（比目标多一行、两列）出发。这一步**不需要**跑容器，
    纯按列构造即可 —— 需要 basmat 的是「下探」本身，不是种子。
    """
    cols, _ = parse_matrix(ini)
    rows = matrix_rows(cols)
    if rows < 1:
        raise ValueError(f"空矩阵没有种子：{ini!r}")
    zero = (0,) * (rows + 1)
    one = (1,) * (rows + 1)
    return format_matrix((zero, one))


def probe(ini: str, version: str | None = None) -> Probe:
    """跑一条 basmat（强制 ``-d``）并解析标准性判定。"""
    parts: list[str] = []
    if version is not None:
        parts += ["-v", str(version)]
    parts += ["-d", "-t", "1"]
    [entry] = run_batch([ini], options=" ".join(parts))
    parsed = parse_standardness(entry.stdout)
    if parsed is None:
        raise BasmatError(f"没能从输出里解析出标准性判定：{ini!r}\n{entry.stdout}")
    return parsed


# ---------------------------------------------------------------------------
# 枚举（sweep 用）
# ---------------------------------------------------------------------------


def enumerate_candidates(rows: int, cols: int, maxval: int):
    """枚举「可能标准」的候选矩阵（按列）。

    只生成满足最基础两条的：首列全零、每列非递增。条件 3（父项 +1）与真正的
    标准性都交给 basmat —— 这样枚举不会因为本仓库的判定而漏掉边界情形。
    """
    if rows < 1:
        raise ValueError("rows 至少为 1")

    def columns():
        # 列出所有「同列非递增、元素 0..maxval」的列，按字典序
        for col in itertools.combinations_with_replacement(range(maxval + 1), rows):
            yield tuple(reversed(col))  # (大...小) -> 上面大、下面小

    all_cols = list(columns())
    zero_col = (0,) * rows
    for length in range(1, cols + 1):
        for tail in itertools.product(all_cols, repeat=length - 1):
            yield (zero_col,) + tail


def _matrix_text(cols) -> str:
    return format_matrix(cols)


# ---------------------------------------------------------------------------
# 子命令
# ---------------------------------------------------------------------------


def cmd_show(args: argparse.Namespace) -> int:
    p = probe(args.ini, version=args.version)
    mark = {True: "标准", False: "不标准", None: "?"}[p.standard]
    print(f"{p.matrix}  -> {mark}")
    if p.seed:
        print(f"  种子：{p.seed}")
    if p.reason:
        print(f"  理由：{p.reason}")
    for i, m in enumerate(p.sequence):
        print(f"  [{i}] {m}")
    return 0


def cmd_seed(args: argparse.Namespace) -> int:
    syntactic = seed_for(args.ini)
    p = probe(args.ini, version=args.version)
    print(f"{p.matrix} 的种子（按定义构造）：{syntactic}")
    if p.seed is not None:
        tag = "与 basmat 打印的一致" if p.seed == syntactic else "!! 与 basmat 打印的不一致"
        print(f"basmat 打印的种子：{p.seed}（{tag}）")
    else:
        print("（basmat 直接给了判定，没有打印种子行）")
    return 0


def cmd_sweep(args: argparse.Namespace) -> int:
    if not image_exists():
        print(
            f"本地没有镜像 {DEFAULT_IMAGE} —— 先构建：\n"
            "  docker compose -f docker/compose.yaml build",
            file=sys.stderr,
        )
        return 2

    cands = list(enumerate_candidates(args.rows, args.cols, args.maxval))
    inis = [_matrix_text(c) + f"[{args.n}]" for c in cands]
    print(f"候选 {len(inis)} 个（rows={args.rows}, cols={args.cols}, maxval={args.maxval}）")

    parts: list[str] = []
    if args.version is not None:
        parts += ["-v", str(args.version)]
    parts += ["-d", "-t", str(args.steps)]
    opts = " ".join(parts)

    out_path = Path(args.out) if args.out else None
    fh = out_path.open("w", encoding="utf-8") if out_path else None
    counts: dict[str, int] = {}
    try:
        for start in range(0, len(inis), args.chunk_size):
            chunk = inis[start : start + args.chunk_size]
            entries = run_batch(chunk, options=opts)
            for ini, entry in zip(chunk, entries):
                parsed = parse_standardness(entry.stdout)
                if parsed is None:
                    counts["未解析"] = counts.get("未解析", 0) + 1
                    continue
                key = {True: "标准", False: "不标准", None: "未判定"}[parsed.standard]
                counts[key] = counts.get(key, 0) + 1
                if fh is not None:
                    row = parsed.to_json()
                    row["ini"] = ini
                    row["version"] = args.version
                    fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    finally:
        if fh is not None:
            fh.close()

    print("统计：" + "，".join(f"{k}={v}" for k, v in sorted(counts.items())))
    if out_path is not None:
        print(f"已写入 {out_path}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="探测 basmat 的标准性判定（下探序列）。")
    sub = ap.add_subparsers(dest="command", required=True)

    p_show = sub.add_parser("show", help="跑一个矩阵，打印种子 / 序列 / 理由")
    p_show.add_argument("ini", help='如 "(0)(0)(1)"（不带 [n] 也行）')
    p_show.add_argument("--version", default=None, help="basmat 版本号（默认它的默认值）")
    p_show.set_defaults(func=cmd_show)

    p_seed = sub.add_parser("seed", help="只打印种子（递降序列的起点）")
    p_seed.add_argument("ini")
    p_seed.add_argument("--version", default=None)
    p_seed.set_defaults(func=cmd_seed)

    p_sweep = sub.add_parser("sweep", help="枚举一批候选矩阵，批量跑 basmat，写 JSONL")
    p_sweep.add_argument("--rows", type=int, default=1)
    p_sweep.add_argument("--cols", type=int, default=5, help="最大列数")
    p_sweep.add_argument("--maxval", type=int, default=3, help="每个元素的最大值")
    p_sweep.add_argument("--n", type=int, default=3, help="矩阵后面的 [n]（不影响标准性）")
    p_sweep.add_argument("--steps", type=int, default=1, help="basmat -t（读判定用 1 就够）")
    p_sweep.add_argument("--version", default=None)
    p_sweep.add_argument("--out", default=None, help="JSONL 输出路径（不写则只统计）")
    p_sweep.add_argument("--chunk-size", type=int, default=200)
    p_sweep.set_defaults(func=cmd_sweep)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
