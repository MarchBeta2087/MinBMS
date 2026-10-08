"""basmat ⇄ MinBMS 的**约定校准**工具。

为什么需要它：basmat 与本仓库是两套独立实现，同一件事（尤其「`[n]` 展开几份坏部」）
**不保证**是同一个约定。想当然地拿两个数字比对，就会在「已知分歧」与「实现 bug」
之间分不清 —— 那正是 CONTRIBUTING.md 铁律三（算不出的不许猜）要防的事。

本工具只做两件事，都不做解释、不猜：

1. ``--capture``：把探针的**原始输出**原样存进 ``tools/fixtures/``，并写 ``manifest.json``
   （含 ini、选项、镜像、可复现命令行、时间）。
2. ``--report``：把每条探针的「关键行」结构化打印出来（哪些行是矩阵、哪些是 ``Ord =``、
   哪些是 ``G/B/Delta/C/f(n)``、最后一行是什么），供人眼判断。

**结论**（哪些约定一致、哪些差 1 份、版本号怎么对应）由人看过之后，
写进 ``tools/README.md`` 的「已实测锁定的事实」与 ``test_calibration.py`` 的断言里。
本工具刻意**不**自动下结论 —— 自动对齐会把真正的分歧抹平。

用法（在仓库根目录）：

    python tools/calibrate.py --capture     # 跑探针并存 fixtures（需要 Docker + 已构建镜像）
    python tools/calibrate.py --report       # 重新跑并打印结构化摘要
    python tools/calibrate.py --from-fixtures  # 不跑容器，直接读 fixtures 打印摘要
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from basmat_client import (  # noqa: E402
    DEFAULT_IMAGE,
    BasmatError,
    docker_available,
    image_exists,
    run_batch,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures"

#: 探针：每条形如 (名字, 选项, ini, 想确认什么)。
#:
#: 挑这些矩阵的理由：
#:   * ``(0)(1)`` 与 ``(0,0)(1,0)`` 是**同一个序数**（ω），但好部长度不同
#:     （前者好部 = (0)，后者好部 = 空）—— 用它俩就能把「份数」这件事钉死；
#:   * ``(0)(1)(2)`` = ω^ω，Δ = 0，是最干净的「只复制、不加阶差」的例子；
#:   * ``(0,0)(1,1)`` = ε₀，超出本仓库 Ordinal.hs 的表示力（README 的「ε₀ 天花板」）；
#:   * ``(0,0,0)(1,1,1)(2,1,0)(1,1,1)`` 是 VERSIONS.md 里 **BM4 与 BM3.3 的黄金分歧算例**
#:     （两个版本的期望值**本仓库已经写死**）—— 拿它还能顺带验证「basmat 的版本号 ↔ 本仓库的版本名」怎么对应；
#:   * ``(0)(1)(2)(0)(0)`` 是常数项的例子（用户给的样本，常数 = 2 个零括号）；
#:   * 最后两条是上游文档与本仓库 CONTRIBUTING 里各出现过一次的「难例」。
PROBES: list[tuple[str, str, str, str]] = [
    ("copy-1row-omega", "-d -t 1", "(0)(1)[3]", "1 行最小极限 ω：看 [n] 复制几份坏部"),
    ("copy-2row-omega", "-d -t 1", "(0,0)(1,0)[3]", "同一个 ω，但好部为空：验证份数与行数/好部无关"),
    ("copy-1row-ww", "-d -t 1", "(0)(1)(2)[3]", "ω^ω：Δ = 0 时只看份数"),
    ("ord-epsilon0", "-d -t 1", "(0,0)(1,1)[3]", "ε₀：超出本仓库序数引擎的表示力"),
    ("const-offset", "-d -t 1", "(0)(1)(2)(0)(0)[3]", "常数项 = 2 个零括号（样本来自用户）"),
    ("const-pure-zero", "-d -t 1", "(0)(0)(0)[3]", "纯零括号：常数项 = 3"),
    ("golden-bm4", "-v 4 -d -t 1", "(0,0,0)(1,1,1)(2,1,0)(1,1,1)[3]", "VERSIONS.md 黄金分歧算例：BM4"),
    ("golden-bm33", "-v 3.3 -d -t 1", "(0,0,0)(1,1,1)(2,1,0)(1,1,1)[3]", "VERSIONS.md 黄金分歧算例：BM3.3"),
    ("psi-2row", "-d -t 1", "(0,0)(1,1)(2,2)(3,3)(3,2)[3]", "上游文档的 ψ(ψ_1(Ω_2))：远超 ε₀"),
    ("rise-chain", "-d -t 1", "(0)(1)(2)(1)(0)(1)(2)(1)(0)(1)(1)(1)(1)[3]", "CONTRIBUTING 里的「无限上升链」矩阵"),
    ("hardy-mode", "-o 4 -d -t 1", "(0,0)(1,1)[3]", "Hardy 模拟模式（-o 4）"),

    # ---- 序数记法探针：为了把 basmat 的文本与本仓库 oShow 的文本对上，先实测它怎么写 ----
    ("notation-w", "-d -t 1", "(0)(1)[3]", "ω 的写法"),
    ("notation-w-plus-1", "-d -t 1", "(0)(1)(0)[3]", "后继（+1）怎么叠在极限后面"),
    ("notation-w-squared", "-d -t 1", "(0)(1)(1)[3]", "ω^2 的写法"),
    ("notation-w-times-2", "-d -t 1", "(0)(1)(0)(1)[3]", "ω·2 的写法（乘号？还是连加？）"),
    ("notation-w-pow-w-plus-1", "-d -t 1", "(0)(1)(2)(1)[3]", "ω^(ω+1) 的写法"),
    ("notation-multi-term", "-d -t 1", "(0)(1)(1)(1)(0)(1)(1)(1)[3]", "多系数项 ω^3·2 的写法"),
    ("notation-e0-plus-w", "-d -t 1", "(0,0)(1,1)(1,0)[3]", "ε₀+ω：跨到 e 记法时怎么写"),

    # ---- 三个「坑」的探针：都是实测中真踩到的，留证据防回归 ----
    ("not-standard-1row", "-d -t 1", "(0)(0)(1)[3]", "basmat 判它**不标准**，于是不给 Ord（本仓库认为是标准矩阵 =ω）"),
    ("not-standard-2row", "-d -t 1", "(0,0)(0,0)(1,1)[3]", "同上，2 行版"),
    ("calc-number-is-n", "-d -t 1", "(0)[5]", "纯零列矩阵：`Calculated number` 就是 n（不是序数！）"),
]

# 摘要时用来分类的行
_RE_MATRIX_LINE = re.compile(r"^[\s(]*\(")
_RE_KEYVALUE = re.compile(r"^(Ord|G|B|Delta|C|f\(n\))\s*=\s*(.*)$")


@dataclass(frozen=True)
class Captured:
    """一条探针的结果。"""

    name: str
    options: str
    ini: str
    why: str
    stdout: str
    rc: int

    @property
    def cmd(self) -> str:
        """可复现的命令行（证据链）。"""
        return f'docker run --rm {DEFAULT_IMAGE} {self.options} "{self.ini}"'


def capture() -> list[Captured]:
    """跑所有探针（批量：一次容器启动跑完），返回结果。"""
    if not docker_available():
        raise SystemExit("找不到可用的 docker（引擎没起来？）")
    if not image_exists():
        raise SystemExit(
            f"本地没有镜像 {DEFAULT_IMAGE} —— 先构建：\n"
            "  docker compose -f docker/compose.yaml build"
        )

    # 按选项分组，每组一批（basmat-batch 的 BASMAT_ARGS 是整批统一的）。
    by_options: dict[str, list[tuple[str, str, str]]] = {}
    for name, options, ini, why in PROBES:
        by_options.setdefault(options, []).append((name, ini, why))

    out: list[Captured] = []
    for options, group in by_options.items():
        entries = run_batch([ini for _, ini, _ in group], options=options)
        if len(entries) != len(group):
            raise SystemExit("批处理返回的条数与探针数不一致（不猜，直接停）")
        for (name, _ini, why), entry in zip(group, entries):
            out.append(
                Captured(
                    name=name,
                    options=options,
                    ini=entry.ini,
                    why=why,
                    stdout=entry.stdout,
                    rc=entry.rc,
                )
            )
    # 保持 PROBES 的顺序，好看
    order = {name: i for i, (name, _, _, _) in enumerate(PROBES)}
    out.sort(key=lambda c: order[c.name])
    return out


def write_fixtures(captured: list[Captured]) -> Path:
    """把原始输出原样写进 tools/fixtures/，并写 manifest.json。"""
    FIXTURES.mkdir(parents=True, exist_ok=True)
    manifest = {
        "image": DEFAULT_IMAGE,
        "captured_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "note": "原始 stdout，未经任何加工；改 basmat 版本后请重新 capture 再看差异。",
        "probes": [],
    }
    for cap in captured:
        (FIXTURES / f"{cap.name}.txt").write_text(cap.stdout + "\n", encoding="utf-8")
        manifest["probes"].append(
            {
                "name": cap.name,
                "ini": cap.ini,
                "options": cap.options,
                "why": cap.why,
                "rc": cap.rc,
                "cmd": cap.cmd,
            }
        )
    path = FIXTURES / "manifest.json"
    path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return path


def summarize(cap: Captured, out_lines: list[str]) -> int:
    """打印一条探针的**结构化摘要**：只分类、不解释。返回「看起来可疑」的计数。"""
    lines = [ln for ln in cap.stdout.splitlines() if ln.strip()]
    matrix_lines = [ln for ln in lines if _RE_MATRIX_LINE.match(ln)]
    kv = [(m.group(1), m.group(2)) for ln in lines if (m := _RE_KEYVALUE.match(ln))]
    ords = [v for k, v in kv if k == "Ord"]
    others = [ln for ln in lines if ln not in matrix_lines and not _RE_KEYVALUE.match(ln)]

    out_lines.append(f"### {cap.name}")
    out_lines.append(f"    为什么看它：{cap.why}")
    out_lines.append(f"    复现命令　：{cap.cmd}")
    out_lines.append(f"    退出码　　：{cap.rc}")
    out_lines.append(f"    首个 Ord ：{ords[0] if ords else '（无 Ord 行）'}")
    out_lines.append(f"    Ord 个数 ：{len(ords)}  ->  {ords[:4]}")
    out_lines.append(f"    G/B/Δ/C  ：{' | '.join(f'{k}={v}' for k, v in kv if k != 'Ord') or '（无）'}")
    out_lines.append(f"    矩阵行数 ：{len(matrix_lines)}（首行：{matrix_lines[0] if matrix_lines else '（无）'}）")
    out_lines.append(f"    其它行　 ：{others[:4]}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="basmat ⇄ MinBMS 的约定校准：只捕获与分类，不自动下结论。",
    )
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--capture", action="store_true", help="跑探针并把原始输出写进 tools/fixtures/")
    g.add_argument("--from-fixtures", action="store_true", help="不跑容器，直接读 fixtures 打印摘要")
    g.add_argument("--report", action="store_true", help="跑容器并打印摘要（默认行为）")
    args = ap.parse_args(argv)

    out: list[str] = []
    if args.from_fixtures:
        manifest_path = FIXTURES / "manifest.json"
        if not manifest_path.exists():
            raise SystemExit(f"没有 {manifest_path} —— 先跑 --capture")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        captured = [
            Captured(
                name=p["name"],
                options=p["options"],
                ini=p["ini"],
                why=p["why"],
                stdout=(FIXTURES / f"{p['name']}.txt").read_text(encoding="utf-8"),
                rc=p["rc"],
            )
            for p in manifest["probes"]
        ]
    else:
        try:
            captured = capture()
        except BasmatError as exc:
            raise SystemExit(f"跑探针失败：{exc}") from exc
        if args.capture:
            path = write_fixtures(captured)
            out.append(f"已写入 {path}")
            out.append("")

    out.append(f"镜像：{DEFAULT_IMAGE}")
    out.append("")
    for cap in captured:
        summarize(cap, out)
        out.append("")
    out.append("----")
    out.append("下一步（人工）：对着上面的摘要判断哪些约定一致、哪些差 1 份、版本号怎么对应，")
    out.append("把结论 + 复现命令写进 tools/README.md 与 test_calibration.py（绝不自动对齐）。")
    print("\n".join(out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

