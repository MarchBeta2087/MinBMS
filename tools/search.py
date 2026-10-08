"""用 basmat 给一批标准矩阵标序数，并与本仓库的结果**交叉验证**。

数据流：

    Explore.exe R C V   ->  标准矩阵列表 + 本仓库自己的序数（或 unresolved）
                              |
                              v
                        basmat（批量，按需要的 -t 分组）
                              |
                              v
                    JSONL（可断点续跑）+ 对拍报告

为什么要「复用 Explore.exe 的枚举」而不是在 Python 里重写一遍：
标准矩阵的判定（BMS 三条件）是本仓库 `BashicuMatrix.hs` 的职责，
在这里重写一份迟早会与它漂移。所以 Python 只**消费** `Explore.exe` 的输出。

用法（在仓库根目录；先 `build.cmd` 或 `./build.sh` 生成 Explore.exe）：

    python tools/search.py ordinals --rows 1 --cols 5 --maxval 3 --n 3 --out out-1x5x3.jsonl
    python tools/search.py ordinals --rows 2 --cols 4 --maxval 4 --only-unresolved --out out-2x4x4.jsonl
    python tools/search.py table --input out-2x4x4.jsonl
    python tools/search.py find  --input out-2x4x4.jsonl --ord "e_0"

关于「份数差 1」：本工具**只用 basmat 的 `Ord`**（那是初始矩阵自己的序数，与份数无关），
不拿它的展开结果与本仓库比 —— 要比展开就必须先做那个 ±1 换算，容易出错。
展开的对照在 `test_calibration.py` 里单独做，并且是显式的。
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from basmat_client import (  # noqa: E402
    DEFAULT_IMAGE,
    BasmatError,
    format_matrix,
    image_exists,
    parse_matrix,
    parse_trace,
    required_steps,
    run_batch,
)
from basmat_client import ordinal_from_trace  # noqa: E402
from ordinal_notation import (  # noqa: E402
    comparable,
    format_cnf,
    ordinals_agree,
    parse_basmat_cnf,
    parse_minbms_cnf,
)

#: Explore.hs 的输出行：`  (0)(1)(2)                    = ω^(ω)`
_RE_EXPLORE_ROW = re.compile(r"^ {2}(?P<matrix>\S.*?)\s{2,}= (?P<value>.*)$")
_UNRESOLVED_MARK = "unresolved"


def default_explore() -> str:
    """仓库里的 Explore 可执行文件。

    POSIX 上必须写 ``./Explore``：当前目录不在 PATH 里，直接写 ``Explore``
    会报 ``[Errno 2] No such file or directory``（CI 上实测踩过）。
    Windows 默认会搜当前目录，``Explore.exe`` 即可。
    """
    return "Explore.exe" if sys.platform == "win32" else "./Explore"


def parse_explore_output(text: str) -> list[tuple[str, str | None]]:
    """解析 `Explore.exe` 的 stdout → ``[(矩阵文本, 本仓库序数文本 or None)]``。

    ``None`` 表示本仓库标了 ``unresolved``（**不是**「序数是 0」）。
    """
    rows: list[tuple[str, str | None]] = []
    for line in text.splitlines():
        m = _RE_EXPLORE_ROW.match(line)
        if not m:
            continue
        matrix = m.group("matrix").strip()
        value = m.group("value").strip()
        if value.startswith(_UNRESOLVED_MARK):
            rows.append((matrix, None))
        else:
            rows.append((matrix, value))
    return rows


def enumerate_with_minbms(
    explore: str, rows: int, cols: int, maxval: int, timeout: float = 900
) -> list[tuple[str, str | None]]:
    """跑 `Explore.exe`，拿到「标准矩阵 + 本仓库序数」的清单。"""
    argv = [explore, str(rows), str(cols), str(maxval)]
    try:
        p = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError) as exc:
        raise SystemExit(f"跑不了 {explore}（先构建：build.cmd / ./build.sh）：{exc}") from exc
    if p.returncode != 0:
        raise SystemExit(f"{explore} 退出码 {p.returncode}\n{p.stderr.strip()}")
    rows_out = parse_explore_output(p.stdout)
    if not rows_out:
        raise SystemExit(f"没能从 {explore} 的输出里解析出任何矩阵（格式变了吗？）")
    return rows_out


@dataclass(frozen=True)
class Row:
    """一个矩阵的完整结果（写进 JSONL 的一行）。"""

    matrix: str
    n: int
    version: str | None
    minbms_ord: str | None  # None = 本仓库 unresolved
    basmat_ord: str | None  # basmat 的 Ord 原文（None = 它没给）
    full_ord: str | None  # 补回常数项后的完整序数
    source: str  # Ord / TrailingZeroColumns / Unavailable
    constant: int
    agree: bool | None  # True/False/None（None = 不构成「对拍」或不可比）
    cmd: str  # 可复现的单条命令
    #: basmat 自己的标准性判定：True 标准 / False **不**标准 / None 它没打这一段。
    #: 实测它与本仓库的 isBasicBMS **不同**（例如 (0)(0)(1)：本仓库认为是标准矩阵 =ω，
    #: basmat 认为不是，于是不给 Ord）—— 必须与「序数超出记法范围」区分开。
    basmat_standard: bool | None = None


def _key(row: Row) -> tuple[str, int, str | None]:
    return (row.matrix, row.n, row.version)


def load_done(path: Path) -> set[tuple[str, int, str | None]]:
    """已有结果（断点续跑用）。坏行直接报错 —— 不静默跳过。"""
    done: set[tuple[str, int, str | None]] = set()
    if not path.exists():
        return done
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as exc:
            raise SystemExit(f"{path}:{line_no} 不是合法 JSON：{exc}") from exc
        done.add((obj["matrix"], obj["n"], obj.get("version")))
    return done


def options_for(steps: int, version: str | None, opt: int | None) -> str:
    """构造 basmat 选项：版本/模式（可选）+ 详细过程 + 步数。"""
    parts: list[str] = []
    if version is not None:
        parts += ["-v", str(version)]
    if opt is not None:
        parts += ["-o", str(opt)]
    parts += ["-d", "-t", str(steps)]
    return " ".join(parts)


def _chunks(items: list, size: int):
    for i in range(0, len(items), size):
        yield items[i : i + size]


def cmd_ordinals(args: argparse.Namespace) -> int:
    if not image_exists():
        raise SystemExit(
            f"本地没有镜像 {DEFAULT_IMAGE} —— 先构建：\n"
            "  docker compose -f docker/compose.yaml build"
        )

    out_path = Path(args.out)
    done = load_done(out_path)
    pairs = enumerate_with_minbms(args.explore, args.rows, args.cols, args.maxval)
    total_enumerated = len(pairs)
    if args.only_unresolved:
        pairs = [(m, v) for m, v in pairs if v is None]

    pending: list[tuple[str, int, str | None, str, int]] = []  # matrix, n, minbms, ini, steps
    skipped = 0
    for matrix, minbms_ord in pairs:
        ini = f"{matrix}[{args.n}]"
        cols, _ = parse_matrix(ini)
        key = (format_matrix(cols), args.n, args.version)
        if key in done:
            skipped += 1
            continue
        pending.append(
            (format_matrix(cols), args.n, minbms_ord, ini, required_steps(cols))
        )
    if args.limit:
        pending = pending[: args.limit]

    print(
        f"枚举到 {total_enumerated} 个标准矩阵；本次待跑 {len(pending)} 个"
        f"（跳过已完成 {skipped} 个）。镜像 {DEFAULT_IMAGE}"
    )
    if not pending:
        print("没有要跑的东西（都已完成？）。")
        return 0

    # 按 -t 分组：不同矩阵需要的步数不同，而 basmat-batch 的选项是**整批统一**的。
    groups: dict[int, list[tuple[str, int, str | None, str]]] = {}
    for matrix, n, minbms_ord, ini, steps in pending:
        groups.setdefault(steps, []).append((matrix, n, minbms_ord, ini))

    rows: list[Row] = []
    for steps, group in sorted(groups.items()):
        opts = options_for(steps, args.version, args.opt)
        for chunk in _chunks(group, args.chunk_size):
            try:
                entries = run_batch([ini for _, _, _, ini in chunk], options=opts)
            except BasmatError as exc:
                raise SystemExit(f"批量调用 basmat 失败（-t {steps}）：{exc}") from exc
            for (matrix, n, minbms_ord, ini), entry in zip(chunk, entries):
                cmd = f'docker run --rm {DEFAULT_IMAGE} {opts} "{ini}"'
                try:
                    trace = parse_trace(entry.stdout)
                except BasmatError:
                    # basmat 认为这个矩阵不合法（两边的「标准」定义可能不同）。
                    # 如实记录，不猜、也不当成「序数为 0」。
                    rows.append(
                        Row(
                            matrix=matrix, n=n, version=args.version,
                            minbms_ord=minbms_ord, basmat_ord=None, full_ord=None,
                            source="RejectedByBasmat", constant=0, agree=None, cmd=cmd,
                        )
                    )
                    continue
                ordi = ordinal_from_trace(ini, trace, cmd=cmd, steps_used=steps)
                # 只有 basmat 真的给了 `Ord` 才算「对拍」；
                # 而且必须拿 **full_text()**（补回常数项后的完整序数）去比 ——
                # 例如 (0)(1)(0) 的极限部分是 ω、常数项 1，完整序数是 ω+1；
                # 拿裸的 ord_text（"w"）去比会把 ω+1 误报成 ω。
                agree: bool | None = None
                if minbms_ord is not None and ordi.source == "Ord":
                    agree = ordinals_agree(ordi.full_text() or "", minbms_ord)
                rows.append(
                    Row(
                        matrix=matrix, n=n, version=args.version,
                        minbms_ord=minbms_ord, basmat_ord=ordi.ord_text,
                        full_ord=ordi.full_text(), source=ordi.source,
                        constant=ordi.constant, agree=agree, cmd=cmd,
                        basmat_standard=trace.is_standard,
                    )
                )

    with out_path.open("a", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(asdict(row), ensure_ascii=False) + "\n")

    _report(rows, out_path)
    return 0


def _report(rows: list[Row], out_path: Path) -> None:
    """打一份「看一眼就知道有没有问题」的摘要；分歧单独列出来。"""
    agree = [r for r in rows if r.agree is True]
    disagree = [r for r in rows if r.agree is False]
    # 「不可比」只对**basmat 真的给了 Ord**（source == "Ord"）的行有意义；
    # TrailingZeroColumns 是本仓库自己按定义得出的，不构成对拍，也就不该算进来。
    incomparable = [
        r
        for r in rows
        if r.source == "Ord" and r.basmat_ord and r.minbms_ord and r.agree is None
    ]
    unavailable = [r for r in rows if r.source == "Unavailable"]
    not_standard = [r for r in unavailable if r.basmat_standard is False]
    beyond = [r for r in unavailable if r.basmat_standard is not False]
    rejected = [r for r in rows if r.source == "RejectedByBasmat"]
    newly = [r for r in rows if r.minbms_ord is None and r.basmat_ord]

    print(f"写入 {out_path}：{len(rows)} 行")
    print(f"  两边一致            ：{len(agree)}")
    print(f"  两边不一致          ：{len(disagree)}")
    print(f"  给了序数但不可比    ：{len(incomparable)}（一边超出康托范式区间）")
    print(f"  basmat 说它不标准    ：{len(not_standard)}（两边「标准」定义不同，见 tools/README.md）")
    print(f"  basmat 也给不出序数  ：{len(beyond)}（超出它的记法范围）")
    print(f"  basmat 判输入非法    ：{len(rejected)}")
    print(f"  本仓库 unresolved 而 basmat 给了序数：{len(newly)}")
    if disagree:
        print("\n!! 以下矩阵两边不一致（需要人工判断，**不要**自动采信任何一边）：")
        for r in disagree:
            print(f"  {r.matrix}[{r.n}]  本仓库 = {r.minbms_ord}   basmat = {r.basmat_ord}")
            print(f"      {r.cmd}")
    if not_standard:
        print("\n以下矩阵 basmat 判为不标准（本仓库认为是标准矩阵）：")
        for r in not_standard:
            print(f"  {r.matrix}[{r.n}]  本仓库 = {r.minbms_ord}   {r.cmd}")
    if rejected:
        print("\n以下矩阵 basmat 判输入非法：")
        for r in rejected:
            print(f"  {r.matrix}[{r.n}]  {r.cmd}")


def _read_rows(path: Path) -> list[Row]:
    return [
        Row(**json.loads(line))
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def cmd_table(args: argparse.Namespace) -> int:
    rows = _read_rows(Path(args.input))
    if args.ordinal_only:
        rows = [r for r in rows if r.basmat_ord]
    if args.format == "tsv":
        print("\t".join(["matrix", "n", "minbms", "basmat", "full", "source", "agree"]))
        for r in rows:
            print(
                "\t".join(
                    [
                        r.matrix, str(r.n), r.minbms_ord or "unresolved",
                        r.basmat_ord or "-", r.full_ord or "-", r.source,
                        "?" if r.agree is None else str(r.agree),
                    ]
                )
            )
        return 0
    print("| 矩阵 | n | 本仓库 | basmat | 完整序数 | 来源 | 一致 |")
    print("|---|---|---|---|---|---|---|")
    for r in rows:
        mark = "?" if r.agree is None else ("是" if r.agree else "**否**")
        print(
            f"| `{r.matrix}` | {r.n} | {r.minbms_ord or 'unresolved'} | "
            f"{r.basmat_ord or '—'} | {r.full_ord or '—'} | {r.source} | {mark} |"
        )
    return 0


def cmd_find(args: argparse.Namespace) -> int:
    """按序数找矩阵：目标文本两边记法都能写（``ω^(ω)`` 或 ``w^w``）。

    目标**超出康托范式**时（``e_0`` / ``p0(...)``）不做序数比较，
    退化成**文本精确匹配**（并明确说出来）—— 那些记法我们没有归一化，
    硬比只会给出假的「相等/不等」。
    """
    rows = _read_rows(Path(args.input))
    target = parse_minbms_cnf(args.ord) or parse_basmat_cnf(args.ord)

    if target is None:
        want = args.ord.strip()
        # 只比 **full_ord（完整序数）**，不比 basmat 裸的 `Ord` ——
        # 裸 `Ord` 是不含常数项的（`(0,0)(1,1)(0,0)` 的裸 Ord 也是 "e_0"，
        # 但它的完整序数是 e_0+1）。拿裸 Ord 去比就会把 e_0+1 说成 e_0 ——
        # 这正是本文档反复强调的那个「消去常数项」的坑。
        # （这条路径天然要求 full_ord 非空，所以 `--exact` 在这里没有额外效果。）
        hits = [r for r in rows if r.full_ord is not None and want == r.full_ord]
        print(
            f"目标 {want!r} 超出康托范式（e/p 记法）→ 退化为**文本完全相等**：命中 {len(hits)} 个"
        )
        for r in sorted(hits, key=lambda r: (len(r.matrix), r.matrix)):
            print(f"  {r.matrix}[{r.n}]  = {r.full_ord}  （本仓库：{r.minbms_ord or 'unresolved'}）")
        return 0

    hits = [r for r in rows if _row_cnf(r) == target]
    if args.exact:
        hits = [r for r in hits if r.full_ord is not None]
    print(f"目标 {format_cnf(target)}：命中 {len(hits)} 个")
    for r in sorted(hits, key=lambda r: (len(r.matrix), r.matrix)):
        print(f"  {r.matrix}[{r.n}]  = {r.full_ord}  （本仓库：{r.minbms_ord or 'unresolved'}）")
    return 0


def _row_cnf(row: Row) -> object | None:
    """把一行里的「完整序数」解析成 CNF；解析不了返回 None。"""
    if not row.full_ord:
        return None
    return parse_minbms_cnf(row.full_ord) or parse_basmat_cnf(row.full_ord)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="用 basmat 给标准矩阵标序数并交叉验证。")
    sub = ap.add_subparsers(dest="command", required=True)

    p_ord = sub.add_parser("ordinals", help="枚举 + 批量取序数 + 对拍，写 JSONL")
    p_ord.add_argument("--rows", type=int, default=1)
    p_ord.add_argument("--cols", type=int, default=5)
    p_ord.add_argument("--maxval", type=int, default=3)
    p_ord.add_argument("--n", type=int, default=3, help="矩阵后面的 [n]（默认 3）")
    p_ord.add_argument("--version", default=None, help="basmat 版本号，如 4 或 3.3（默认用它的默认值）")
    p_ord.add_argument("--opt", type=int, default=None, help="basmat 的 -o（默认不传）")
    p_ord.add_argument("--explore", default=default_explore(), help="Explore 可执行文件路径")
    p_ord.add_argument("--out", default="search-out.jsonl")
    p_ord.add_argument("--only-unresolved", action="store_true", help="只跑本仓库 unresolved 的")
    p_ord.add_argument("--limit", type=int, default=0, help="最多跑几个（0 = 不限）")
    p_ord.add_argument("--chunk-size", type=int, default=200, help="每批多少个（一次容器启动）")
    p_ord.set_defaults(func=cmd_ordinals)

    p_tab = sub.add_parser("table", help="把 JSONL 打成表格")
    p_tab.add_argument("--input", required=True)
    p_tab.add_argument("--format", choices=["md", "tsv"], default="md")
    p_tab.add_argument("--ordinal-only", action="store_true", help="只列 basmat 给了序数的")
    p_tab.set_defaults(func=cmd_table)

    p_find = sub.add_parser("find", help="按序数找矩阵")
    p_find.add_argument("--input", required=True)
    p_find.add_argument("--ord", required=True, help="目标序数，如 ω^(ω) 或 w^w")
    p_find.add_argument("--exact", action="store_true", help="只匹配「完整序数」明确的那些")
    p_find.set_defaults(func=cmd_find)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
