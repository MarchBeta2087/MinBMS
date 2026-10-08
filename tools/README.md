# tools —— 拿 basmat 当「对照基线」

basmat（[kyodaisuu/basmat](https://github.com/kyodaisuu/basmat)，GPL-3.0）是 BMS 的**独立实现**，
它会打印计算过程并给出序数。本目录把它当 **oracle** 用：

- 给 `Explore.hs` 标 `unresolved` 的矩阵补序数（尤其是 ≥ ε₀、超出本仓库 `Ordinal.hs` 表示力的那些）；
- **交叉验证**本仓库已定序的结果（不是替换、更不是「以 basmat 为准」）；
- 把两边的**约定差异**显式记录并换算，而不是悄悄抹平。

容器怎么建、怎么跑见 [../docker/README.md](../docker/README.md)。

## 文件

| 文件 | 作用 | 需要 Docker？ |
|---|---|---|
| `basmat_client.py` | 调容器、解析 `-d` 输出、把序数还原成「极限部分 + 常数项」 | 调用时需要 |
| `ordinal_notation.py` | 把两边的**序数文本**归一到同一棵树（只为交叉验证） | **否** |
| `calibrate.py` | 跑探针、把**原始输出**存进 `fixtures/`、打印结构化摘要 | 是 |
| `search.py` | 枚举矩阵 → 批量取序数 → JSONL（可断点续跑）+ 对拍 | 是 |
| `standardness.py` | 抓 basmat 的**下探**标准性判定（种子 / 递降序列 / 理由），可 sweep | 是 |
| `bms_reference.py` | **独立参考实现**：BM4 展开 + 「种子展开闭包」标准性（不移植 basmat） | 是（仅调容器对拍时） |
| `STANDARDNESS.md` | 「下探」方法的实测笔记；含关键规律「标准 = 种子展开闭包」 | — |
| `test_basmat_client.py` | 纯逻辑单测（矩阵解析 / 常数项计数 / 批处理框解析） | **否** |
| `test_bms_reference.py` | 参考实现的离线单测（展开黄金值 / 若干标准性样例） | **否** |
| `test_ordinal_notation.py` | 序数记法的解析 / 比对单测（含与 `Explore.exe` 值的对拍） | **否** |
| `test_calibration.py` | 把下面「已实测锁定的事实」写成断言 | 是（没 Docker 时自动 skip） |
| `fixtures/` | 探针的原始输出 + `manifest.json`（含可复现命令行、镜像、时间） | — |

```bash
python tools/test_basmat_client.py      # 离线
python tools/test_ordinal_notation.py   # 离线
python tools/calibrate.py --capture     # 跑探针 + 存证据（升级 basmat 后重跑）
python tools/test_calibration.py        # 实测事实的断言（要镜像）

# 搜索（需要先 build.cmd / ./build.sh 生成 Explore.exe）
python tools/search.py ordinals --rows 2 --cols 4 --maxval 4 --only-unresolved --out out.jsonl
python tools/search.py table --input out.jsonl
python tools/search.py find  --input out.jsonl --ord "e_0"
```

---

## 已实测锁定的事实

> 基线：镜像 `minbms/basmat:4.0-f2f0125`，即上游 tag **v4.0** / commit
> `f2f0125b6618a1a298f53b63464ebdcec137ff92`。
> 每条都给了**复现命令** —— 换版本后请重跑 `calibrate.py --capture` 再看差异，
> `test_calibration.py` 会立刻把变化标红。

### 事实 1：没有 `-d` 就没有 `Ord`

不带 `-d` 时 basmat 只打一串矩阵（计算过程的每一步），**没有任何 `Ord =` 行**。

```bash
docker run --rm minbms/basmat:4.0-f2f0125 "(0,0)(1,1)[3]"     # 没有 Ord
```

所以取序数**必须带 `-d`**。

### 事实 2：`Ord` 只打在「极限节点」上；常数项 = 末尾全零列的个数

末列全零的矩阵是**后继步**（basmat 会摘掉那个零列，等于 +1），这种节点**不打 `Ord`**；
只有末列非零的**极限节点**才打。实测：

```bash
docker run --rm minbms/basmat:4.0-f2f0125 -d -t 3 "(0)(1)(2)(0)(0)[3]"
```

```
(0)(1)(2)(0)(0)[3]        <- 没有 Ord（后继）
(0)(1)(2)(0)[3]           <- 没有 Ord（后继）
(0)(1)(2)[3]
Ord = w^w                 <- 极限节点
```

于是 **完整序数 = 第一个带 `Ord` 的节点的序数 + 之前被摘掉的零列数**，
也就是 ω^ω + 2。常数项**按列数**：`(0,0)(0,0)(0,0)` 是 **3** 个零括号（不是 6 个 0），
对应 `Ordinal.constant` / `trailing_zero_columns()`。

### 事实 3：`-t T` 是「最多走 T 步」，且**最后一个被截住的节点是光秃秃的**

实测：`-t T` 会打印 **T+1** 个节点，其中最后一个（被步数上限截住的那个）
**没有 `G/B/Delta/C`、也没有 `Ord`**。所以「末尾有 k 个零列」时，必须给 **`-t (k+1)`**
才能让极限节点落在「有详情」的位置上：

```bash
docker run --rm minbms/basmat:4.0-f2f0125 -d -t 2 "(0)(1)(2)(0)(0)[3]"   # 拿不到 Ord
docker run --rm minbms/basmat:4.0-f2f0125 -d -t 3 "(0)(1)(2)(0)(0)[3]"   # 拿得到 w^w
```

`basmat_client.required_steps()` 就是这条规则（`k + 1`），`ordinal_of()` 自动用它。

### 事实 4：`G` / `B` / `Delta` 与本仓库的好部 / 坏部 / 阶差向量**逐列相同**

这条很重要：它说明两个实现的**分解方式同源**，分歧只在「份数」（事实 5）。

```bash
docker run --rm minbms/basmat:4.0-f2f0125 -d -t 1 "(0,0,0)(1,1,1)(2,1,0)(1,1,1)[3]"
```

```
G = empty                              <- 好部
B = (0,0,0)(1,1,1)(2,1,0)              <- 坏部（含坏根、不含末列）
Delta = (1,1,0)                        <- 阶差向量 Δ
```

与 README 的定义对照：末列 `(1,1,1)` 最下方的非零项在第 1 行（值 1），
其父项是左边第一个比它小的项，即第 0 列 `(0,0,0)` → 坏根在第 0 列
→ 好部为空、坏部 = 前 3 列。**完全一致**。
（`C` 这一项见文末「未确定」。）

### 事实 5（最关键）：份数差 1 —— `basmat[n]` ≡ 本仓库 `MinBMS[n+1]`

本仓库 README 的约定是「`[n]` = 好部 + **n** 份坏部」；
basmat 实测是「好部 + **(n+1)** 份坏部」（第 k 份加 k·Δ，k = 0..n）。

证据用的是 **VERSIONS.md 里本仓库自己锁死的黄金值**（不是从 basmat 抄的）：

```bash
docker run --rm minbms/basmat:4.0-f2f0125 -v 4 -d -t 1 "(0,0,0)(1,1,1)(2,1,0)(1,1,1)[3]"
```

basmat 的下一状态是 **12 列 = 4 块**（n=3 却复制 4 份），而
VERSIONS.md 的 BM4 黄金值 `(0,0,0)(1,1,1)(2,1,0)(1,1,0)(2,2,1)(3,2,0)(2,2,0)(3,3,1)(4,3,0)`
正好是它的**前 9 列（逐列相同）**。也就是说 basmat 比本仓库多复制了一块。

**同理**：`(0)(1)[3]` 给 `(0)(0)(0)(0)`（4 份）；`(0,0)(1,1)[3]` 给
`(0,0)(1,0)(2,0)(3,0)`（4 块）。

> 这不是「谁对谁错」的问题：`ω^ω` 的共尾列 `ω^1, ω^2, ω^3, …` 与 `ω^2, ω^3, …`
> 都是合法的基本列，只差一个指标平移。**但必须显式换算，绝不能把两个数字直接比。**
>
> 顺带一提，这也解释了 CONTRIBUTING.md 里那段「`[0]` 有时给出一个额外起点项」的来历。

### 事实 6：版本号对应 —— `-v 4` ↔ `BM4`，`-v 3.3` ↔ `BM3.3`

```bash
docker run --rm minbms/basmat:4.0-f2f0125 -v 3.3 -d -t 1 "(0,0,0)(1,1,1)(2,1,0)(1,1,1)[3]"
```

basmat `-v 3.3` 的前 9 列 = VERSIONS.md 里 **BM3.3** 的黄金值（`…(3,3,1)(4,1,0)`），
`-v 4` 的前 9 列 = **BM4** 的黄金值（`…(3,3,1)(4,3,0)`）—— 两者确实在这处分道扬镳，
所以「版本号映射」这件事是**被验证到**的，而不是假设的。

### 事实 7：输入非法时**退出码仍是 0**

```bash
docker run --rm minbms/basmat:4.0-f2f0125 "not-a-matrix"; echo "rc=$?"   # rc=0！
```

只会打印 `Error: invalid sequence of Bashicu matrix.` + 帮助。
所以判错**不能只看退出码**，必须同时看这一行（`basmat_client.INVALID_INPUT_MARK`）。

### 事实 8：纯后继（零列）矩阵：`Calculated number` **就是 n，不是序数**

```bash
docker run --rm minbms/basmat:4.0-f2f0125 -d -t 5 "(0)(0)(0)(0)[3]"
#   ... 一路摘零列 ...
#   (0)[3]
#   Finished. Calculated number = 3
```

这类矩阵 basmat **不打 `Ord`**，只在最后打一行 `Finished. Calculated number = N`。
一开始我们由 `(0)(0)(0)[3] → 3` 以为「N 就是序数」，**那是错的**（n=3 与序数 3 的巧合）：

```bash
docker run --rm minbms/basmat:4.0-f2f0125 "(0)[5][5]"    # 注意：输入被解析成 n=55
#   (0)[55]
#   Finished. Calculated number = 55
docker run --rm minbms/basmat:4.0-f2f0125 -t 9 "(0)(0)[7]"      # → 7
docker run --rm minbms/basmat:4.0-f2f0125 -t 9 "(0,0)(0,0)[9]"  # → 9
```

**N 恒等于传进去的 n**，与矩阵的序数无关（`(0)` 是 1、`(0)(0)` 是 2、`(0)(0)(0)(0)` 是 4）。
所以 `basmat_client` **不使用**这个数，改用本仓库 README 的展开规则 2 直接得出
（每摘掉一个零列 +1 ⇒ k 个零列 = k），来源标成 `TrailingZeroColumns` 以示区别。

> 「下探」标准性判定的完整实测（种子规律、三种失败理由、为什么它不是可物化的列表、
> 以及为什么不应搬进本仓库）见 **[STANDARDNESS.md](STANDARDNESS.md)**。

### 事实 10：basmat 的「标准性」判定与本仓库 `isBasicBMS` **不同**

basmat 会给不符合它标准的矩阵**不给 `Ord`**，而不是告诉你「序数算不出」：

```bash
docker run --rm minbms/basmat:4.0-f2f0125 -d -t 1 "(0)(0)(1)[3]"
```

```
Checking if (0)(0)(1) is standard or not.
Decreasing sequence from (0,0)(1,1) follows.
(0)(1)
Not standard because it is (0)(0)(0)...
--------------------------------------------
(0)(0)(1)[3]                <- 只有 G/B/Delta/C，没有 Ord
```

它用的是「**从固定种子出发的递降序列**」这一套判定（种子会原样打印出来：
`Decreasing sequence from (0,0)(1,1) follows.`），而本仓库用的是 README 的三条件
（`isBasicBMS`）。两者实测**不一致**：在 `Explore.exe 2 4 4` 的 83 个
本仓库 `unresolved` 矩阵里，**41 个被 basmat 判为不标准**（因此拿不到 `Ord`），
42 个拿到了序数。

> 我们**不裁决**谁对 —— 这是标准性**定义**的分歧，不是某个实现的 bug。
> 工具只负责把两者分开报：`search.py` 的摘要里「basmat 说它不标准」与
> 「basmat 也给不出序数（超出记法范围）」是**两栏**，绝不混为一谈。

### 事实 11：序数记法对照表（ε₀ 以下可直接互译）

| 序数 | 本仓库 `oShow` | basmat | 备注 |
|---|---|---|---|
| 1 | `1` | `1` | |
| ω | `ω` | `w` | |
| ω² | `ω^(2)` | `w^2` | basmat 指数是原子时省括号 |
| ω^ω | `ω^(ω)` | `w^w` | |
| ω^(ω+1) | `ω^(ω + 1)` | `w^(w+1)` | basmat 指数是式子时带括号 |
| ω·2 | `ω·2` | `w+w` | ★ basmat 把系数写成**重复相加** |
| ω³·2 | `ω^(3)·2` | `w^3+w^3` | |
| ε₀ | 表示不出（> ε₀ 天花板） | `e_0` | |
| ε_ω | 表示不出 | `e_w` | |
| ε₀·ω | 表示不出 | `(e_0)w` | 记法细节我们不深究，只原样记录 |
| ψ(ψ₁(Ω₂)) | 表示不出 | `p0(p1(p2(p3(0)+p2(0))))` | 上游文档里的那个例子 |

`ordinal_notation.py` 把两边归一到同一棵康托范式树，因此可以机械地对拍；
**一旦文本里出现 `e` / `p`（超出康托范式区间），解析返回 `None`，调用方必须跳过比较。**
注意 `oShow` 的指数里也可能带空格（`ω^(ω + 1)`），所以切分必须按**括号深度**做。

### 实测收益（这个工具到底解决了什么）

`Explore.exe 2 4 4` 的 83 个 `unresolved` 里，42 个拿到了 basmat 的序数，其中包括
README「ε₀ 天花板」那一节点名的矩阵：

| 矩阵 | basmat 序数 | 本仓库 |
|---|---|---|
| `(0,0)(1,1)` | `e_0` | unresolved（ε₀ 表示不出） |
| `(0,0)(1,1)(1,1)` | `e_1` | unresolved |
| `(0,0)(1,1)(2,0)` | `e_w` | unresolved |
| `(0,0)(1,1)(2,1)` | `p0(p1(p1(0)))` | unresolved |
| `(0,0)(1,1)(2,2)` | `p0(p1(p2(0)))` | unresolved |
| `(0,0)(1,1)(0,0)(1,0)` | `e_0+w` | unresolved |

复现：`python tools/search.py ordinals --rows 2 --cols 4 --maxval 4 --only-unresolved --out out.jsonl`

> **注意**：这些序数来自 basmat，**不是**本仓库自己推导的，所以只能当「外部参考值」，
> 不能直接写进 `Test.hs` 的期望值（CONTRIBUTING 铁律：期望值必须能由本仓库的定义推出）。

### 事实 9：超出记法范围的矩阵，basmat 也**不给** Ord

`(0,0,0)(1,1,1)(2,1,0)(1,1,1)` 这种远超 ε₀ 的矩阵，basmat 只给
`G/B/Delta/C/f(n)`，**没有 `Ord`**。这时 `ordinal_of()` 返回
`source="Unavailable"`、`ord_text=None` —— **如实说「基线也不知道」**，
绝不拿别的东西顶替（铁律三）。

### 未确定：`C` 的含义（本工具**不使用**）

`-d` 的详情块里还有一项 `C`（列数与坏部相同）。我们**没有**从黑盒确定它的语义，
所以工具里不读它、文档里不解释它。唯一记录在案的观察是：BM4 与 BM3.3 的 `C`
差异位置，和 VERSIONS.md 记录的两个版本的**分歧位置**一致。
真要弄清它，得读上游源码 —— 而本项目的立场是**不参考、不搬运**它的代码（见下「许可证」）。

---

## 怎么用

```python
import sys; sys.path.insert(0, "tools")
from basmat_client import ordinal_of, trailing_zero_columns, format_matrix, parse_trace

r = ordinal_of("(0,0)(1,1)[3]")
r.ord_text        # 'e_0'     —— basmat 打印的极限部分
r.constant        # 0         —— 需要补回的常数项
r.full_text()     # 'e_0'     —— 完整序数的文本
r.source          # 'Ord' | 'CalculatedNumber' | 'Unavailable'
r.cmd             # 可复现的命令行（证据链）

r2 = ordinal_of("(0)(1)(2)(0)(0)[3]")
r2.full_text()    # 'w^w + 2'
```

逐条查（单条调用，`-t` 自动按末尾零列数算好）：

```python
from basmat_client import ordinal_of
r = ordinal_of("(0,0)(1,1)(2,1)[3]")
r.ord_text, r.source, r.cmd   # ('p0(p1(p1(0)))', 'Ord', 'docker run --rm ... ')
```

### 搜索：`search.py`

枚举的来源是 `Explore.exe`（**不重复实现**标准矩阵判定），用 basmat 批量标序数、
与本仓库的结果对拍，结果写 JSONL（**可断点续跑**：重跑会跳过已完成的行）。

```bash
python tools/search.py ordinals --rows 2 --cols 4 --maxval 4 --n 3 \
                               --only-unresolved --out out-2x4x4.jsonl
```

摘要会把结果分成六栏，**互不混淆**：

```
  两边一致            ：10
  两边不一致          ：0     <- 有分歧会逐条列出（含复现命令），绝不自动采信任何一边
  给了序数但不可比    ：0     （一边超出康托范式区间）
  basmat 说它不标准    ：0     （两边「标准」定义不同，见事实 10）
  basmat 也给不出序数  ：0     （超出它的记法范围）
  本仓库 unresolved 而 basmat 给了序数：2
```

```bash
python tools/search.py table --input out-2x4x4.jsonl            # markdown 表
python tools/search.py table --input out-2x4x4.jsonl --format tsv
python tools/search.py find  --input out-2x4x4.jsonl --ord "e_0"   # 两边记法都能写
python tools/search.py find  --input out-2x4x4.jsonl --ord "w^w"
```

`find` 会把目标文本归一到康托范式再比；目标**超出康托范式**时（`e_0`、`p0(...)`）
退化为**文本完全相等**，并明确告诉你「这是文本比较、不是序数比较」——
那些记法我们没有归一化，硬比只会给出假的结论（想找 `e_0+k` 就直接写 `"e_0 + 1"`）。

其它参数：`--version 3.3`（换 basmat 版本）、`--opt 2|3|4`、`--limit N`、
`--chunk-size N`（每批多少条 —— 一个容器跑完整批，这在 Windows 上快一个数量级）。

> **为什么没有 `--jobs`**：批量执行已经把「每次开容器 0.3–1 秒」的固定开销摊掉了，
> 再并行只会引入不确定性（同一批里 `-t` 必须一致）。要提速请先调 `--chunk-size`。

### 对拍是靠什么做到的

`ordinal_notation.py` 把「本仓库 `oShow` 的文本」与「basmat 的 `Ord` 文本」归一到
同一棵康托范式树再比 —— 所以 `ω^(ω + 1)` 与 `w^(w+1)`、`ω·2` 与 `w+w` 会被认成同一个序数。
超出康托范式（出现 `e`/`p`）的一律返回 `None` → 判为**不可比**，**不是**不一致。

---

## 绝不猜测

- 解析对不上就**报错**，不返回半个结果；
- basmat 给不出序数就记 `Unavailable`，**不猜**；
- 两边的约定差异（份数）**显式换算并记录**，不静默对齐；
- 每条结论都带**可复现命令**（`calibrate.py --capture` 存进 `fixtures/manifest.json`）。

这与 [CONTRIBUTING.md](../CONTRIBUTING.md) 铁律三一致。

## 许可证

本目录的 Python 代码是本仓库自己的作品，按 **BSD-3-Clause** 授权（见 [../LICENSE](../LICENSE)）。
basmat 是 **GPL-3.0** 的第三方程序：我们只把它当成**另一个进程**来调用、解析它的 stdout，
既不链接也不修改、更没有搬运它的代码 —— 不构成衍生作品。
分发**镜像**时的义务见 [../docker/README.md](../docker/README.md) 的「许可证」一节。
