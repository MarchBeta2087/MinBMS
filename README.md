# Bashicu Matrix System（BMS）最小化实现

项目地址：

[https://github.com/MarchBeta2087/MinBMS](https://github.com/MarchBeta2087/MinBMS)

这是 BMS 的 Haskell 最小化实现，旨在提供 BMS 的基础功能。

本项目使用 BSD-3-Clause 许可证。

## BMS 形式

一个 BMS 是形如

```BMS
a00 a01 a02 ... a0n
a10 a11 a12 ... a1n
a20 a21 a22 ... a2n
... ... ... ... ...
am0 am1 am2 ... amn
```

的矩阵，记作

`(a00,a10,a20,...,am0)(a01,a11,a21,...,am1)(a02,a12,a22,...,am2)...(a0n,a1n,a2n,...,amn)`

在本项目中，我们用 `GBashicuMatrix` 表示一个 BMS，用 `GColumn` 表示其中的一列，具体为

`GBashicuMatrix [GColumn [a00,a10,a20,...,am0],GColumn [a01,a11,a21,...,am1],GColumn [a02,a12,a22,...,am2],GColumn [a0n,a1n,a2n,...,amn]]`

也就是按列存储，将同一列上的数据储存到一个一维列表。`initBMS` 的输入允许非等长（相当于省略了各列末尾的 0），构造时会统一按最大高度在右侧补零，例如 `initBMS [[0,1],[0,1],[0]]` 得到 `(0,0,0)(1,1,0)`。

## 概念

在 BMS 中定义如下概念：

1. 第一行元素的父项为从该元素起，在该元素左边且小于该元素的第一个项。
2. 元素的祖先项为元素自身、元素的父项、父项的父项等元素。

   > **注意「含自身」**：代码里的 `isAncestorOf` 把自身也算作自己的祖先项，
   > 展开规则 3 的判定直接依赖这一点（坏根列上的项正是因为「是自身的祖先」才加阶差）。
3. 其余行元素的父项为从该元素起，在该元素左边，小于该元素，且其正上方的项是该元素正上方的项的祖先项的第一个项。

   > 父项链只在**同一行**内传递，所以下面凡涉及「祖先项」的判定，都要按项所在的
   > 那一行取参照，不能拿坏根位置本身去比。
4. 坏根为最后一列中从下往上数的第一个非零项的父项所在的列。
5. 坏部为坏根和末列之间的部分，包含坏根，但是不包含末列。
6. 好部为坏根之前的部分，不包含坏根。
7. 阶差向量 Δ 为末列各项与坏根列对应项之差，但**末列最下方那个非零项所在的行及以下，Δ 恒为零**。
   记 z 为末列中从下往上数的第一个非零项所在的行（概念 4 用的就是它），则
   Δᵢ = 末列第 i 行 − 坏根列第 i 行（i < z），Δᵢ = 0（i ≥ z）。
   等价说法：若末列第 i+1 行为零，则 Δᵢ 也为零（末列是非递增的，两种说法一致）。

   > 这条容易被误读成「矩阵的最后一行 Δ 恒为零」。对**单行矩阵**来说 z 就是唯一的那一行，
   > 于是 Δ ≡ 0 —— 这是正确的、不是退化：单行时展开只复制坏部而不加 Δ，序数照样递增
   > （如 `(0)(1)(2) = ω^ω`，其基本列为 `(0)(1)`、`(0)(1)(1)`、`(0)(1)(1)(1)`…）。

## BMS 条件

一个标准的 BMS 应当满足如下的条件：

1. 首列的所有元素都应当为零。
2. 同列中排在下面的项不大于排在上面的项。
3. 每一个非零项都至多为其父项 +1。

> **注意：这三条只是必要条件，不是充分条件。** 满足三条、但并不标准的例子：
> `(0)(0)(1)`、`(0)(0)(1)(1)`、`(0,0,0)(1,1,1)(2,2,2)(3,2,2)(4,3,0)`。
> 上面的三条由 `isBasicBMS` 判定；**完整的标准性**由 `isStandardBMS` 判定：
>
> > 标准集 = 从极限种子 `(0,...,0)(1,...,1)`（行数 = 目标行数 + 1）出发，
> > 反复做基本列展开所能到达的矩阵。
>
> 也就是说，`M` 标准 ⇔ `M` 在该展开闭包里。闭包只生成标准矩阵，所以
> `isStandardBMS` 判「标准」永远正确；判「非标准」需要界够大（界不够只会漏报，不会误报）。
> 这条规律是与 basmat 的 `Standard.` / `Not standard` 实测对拍锁定的
> （1 行 341/341、`Explore.exe 2 4 4` 的 83 个 83/83），详情与实现见
> [tools/STANDARDNESS.md](tools/STANDARDNESS.md) 与 [tools/bms_reference.py](tools/bms_reference.py)。

## BMS 展开规则

BMS 的展开规则如下：

1. 空矩阵所对应的序数为 0，即 (∅)=0。
2. 如果 BMS 的最后一列全为零，则它所对应的序数为删去最后一列之后余下部分所对应的序数 +1
   （展开结果与复制次数 n 无关）。
3. 否则保留好部的所有内容不动，将坏部复制加在好部后面。**记作 `[n]` 的展开式是
   「好部 + n 份坏部」**，第 k 份（k = 0..n-1）是坏部加上 `k·Δ`。
   本约定与行数无关：`(0)(1)[n]` 与 `(0,0)(1,0)[n]` 都是 n 份（已实测并写进测试）。

   至于「坏部里哪些项要加 Δ」，**这是各个 BMS 版本唯一有差别的地方**，
   上面这一句描述的是 **BM4** 的规则，完整表述为：坏部中位于 `(c, y)` 的项加 Δ，
   当且仅当它**在同一行**的祖先链包含坏根列上的 `(坏根列, y)`；否则该项在所有副本中保持不变。
   BM3.3 等其它版本只改这一条判定，其余（好部 / 坏部 / 坏根 / Δ）完全相同 ——
   详见 [VERSIONS.md](VERSIONS.md)。

## 版本支持

本项目同时支持多个 BMS 版本。所有版本共享同一副骨架（父项 / 祖先项 / 坏根 / 好部 / 坏部 / Δ / 三条展开规则），
**唯一的可变点是「坏部复制时哪些项加 Δ」**，它被抽象成一个类型：

```haskell
type Ascension = BMatrix -> Int -> (Position -> Bool)   -- 位置 -> 是否加 Δ

data Version = Version { versionName :: String, versionAscend :: Ascension }
```

已登记的版本见 `Version.hs` 的 `versions`：**`BM4`**（现行版本，默认）与 **`BM3.3`**（rpakr & Ecl1psed，2019-03）。

```haskell
expandBMS  :: BMatrix -> Integer -> Maybe BMatrix        -- = BM4
expandWith :: Version -> BMatrix -> Integer -> Maybe BMatrix
lookupVersion "BM3.3"                                    -- Just (BM3.3)
```

命令行：`runghc Explore.hs --bm=BM3.3 1 5 3`（默认 BM4）。

**想加新版本？** 见 [VERSIONS.md](VERSIONS.md) 的「如何添加一个新版本」——
一句话概括：写一条 `Ascension` → 定义版本常量 → 加进 `versions` → 补测试。

> 注意：目前的可插拔点只有「加不加 Δ」。BM1 / BM2.3 这类**坏根搜索规则**不同的老版本
> 需要先改造 `BashicuMatrix.hs`，见 VERSIONS.md 末尾的「边界」。

## 非常规序数与无限序列

本项目用 `GBashicuOrdinal` 表示非常规序数，即「BMS + x」的形式：一个末列非全零的标准 BMS（极限部分）、一个非负整数复制次数，以及一个非负整数后继偏移：

```haskell
data GBashicuOrdinal bms where
    BO :: GBashicuMatrix [GColumn [Integer]] -> Integer -> Integer -> GBashicuOrdinal [GColumn [Integer]]
```

`BO matrix copies offset` 表示序数「`matrix` 的基本列的第 `copies` 项 + `offset`」。任意标准 BMS 都可以唯一地分解为极限部分加上若干个全零末列（每个全零末列对应序数 +1），`normalizeBMS` 执行这一分解，例如 `(0,0)(1,1)(0,0)(0,0)` 规范化为 `((0,0)(1,1), 2)`，即 ε₀ + 2。

推荐使用 `mkOrdinal` 构造序数。它会检查 BMS 条件以及复制次数非负，并自动对矩阵做上述规范化分解。

`ordinalSequence matrix` 返回惰性的无限列表，其各项的复制次数依次为 `0、1、2、...`（后继偏移保持不变）。使用 `expandedBMS` 可以将其中一项展开为有限 BMS：保留好部，复制指定次数的坏部，并按阶差向量调整受坏根祖先关系影响的元素，最后在末尾加回 `offset` 个全零列。有限展开项不包含作为极限标记的原末列，因此复制 0 次可能得到空矩阵或仅包含好部的矩阵。

`expandBMS` 则直接实现定义中的三条展开规则：空矩阵展开为空矩阵；末列全零时删去一个末列（与复制次数无关）；末列非全零时复制坏部并加阶差。

参考资料：

《大数理论》（曹知秋，2026 年 8 月 30 日，[https://github.com/ZhiqiuCao/Googology](https://github.com/ZhiqiuCao/Googology)）Chapter 13.Bashicu 矩阵，13.1 BMS 的定义，P343、P344
—— 上面「概念 / BMS 条件 / BMS 展开规则」三节的来源。

> **关于引用方式**：上述三节的文字是**独立重述**，不是逐字复制原文；
> 出处按学术惯例标注。该来源**未声明任何许可证**（保留所有权利），
> 因此这里只重述其中的**数学内容**（事实与定义，不受著作权保护），不搬运其表达。
> 若你在贡献中使用了其它外部资料，请照同样方式：**重述 + 标注出处**，
> 详见 [CONTRIBUTING.md](CONTRIBUTING.md) 的铁律二。

各**版本**的定义与出处另见 [VERSIONS.md](VERSIONS.md)。

## 测试与序数分析

本仓库附带两个**零依赖**小工具（只需 GHC，无需 cabal 包）：

```bash
make test                   # 推荐：先编译再跑（Windows 用 mingw32-make test，详见「如何构建」）
runghc Test.hs              # 测试：黄金用例 + 性质/不变量 + 多版本 + 序数引擎自检
runghc Explore.hs 1 5 3     # 枚举标准矩阵，并（交叉验证地）给出序数
runghc Explore.hs --bm=BM3.3 1 5 3    # 换一个版本
```

> **为什么别用 `runghc`**：`runghc` 是解释执行，实测 `Test.hs` 要 **19.5 秒**，
> 而先 `ghc -O1` 编译再跑只要 **0.37 秒**（约 50 倍差）。
> 用仓库自带的 `Makefile`（`make build` / `make test`）、便捷脚本（`./build.sh`）或 `minbms.cabal` 即可。

- `Test.hs`：全部通过时打印「全部通过」；有失败则列出名称并以非零码退出。
- `Explore.hs` 用法：`runghc Explore.hs <行数> <最大列数> <最大数值> [基本列深度k] [每矩阵燃料]`。
- 燃料是**每个矩阵独立**的步数预算（默认 2000）：调大可提高覆盖率但更慢，调小则更快、
  更多 `unresolved`。每个矩阵还受 `maxAnalyzedCols` 限制，所以在本仓库给出的参数范围内
  **不会卡死**（实测 `Explore.hs 1 5 3` 与 `Explore.hs 2 4 4` 都在 ~1 秒级）。
- **表示力上限（ε₀ 天花板，重要）**：内置序数引擎（`Ordinal.hs`）是康托范式，只能表示
  **< ε₀** 的序数。而 2 行以上的矩阵只要某一列在第 2 行及以下出现非零项（例如
  `(0,0)(1,1)`，它就是 ε₀），序数就 ≥ ε₀、**表示不出来**。`Explore.hs` 用
  `representableInCNF` 在**不烧燃料**的前提下把这类矩阵直接判为 `unresolved`，
  所以 2 行枚举里绝大多数都是 `unresolved` —— 这是**引擎的表示力**问题，不是矩阵不标准。
  要真正定出它们，需要把引擎升级到 Veblen 范式（ε 数 / Γ₀），见待办。
- `Explore.hs` **只输出能通过基本列交叉验证的序数**；验证不通过的一律标 `unresolved`
  并打印其基本列，**绝不猜测**。
- `Explore.hs` 现在先用 `isStandardBMS` 过滤：**不标准的矩阵不烧燃料**，直接标
  `(non-standard)`；只有标准矩阵才去（尝试）定序。所以每行结果是三者之一：
  `= 序数` / `= (non-standard)` / `= unresolved`（标准但定不出）。
  注意它枚举的是**满足 README 三条件**的矩阵（必要条件），不是全部矩阵。

## 与 basmat 对照（可选，Docker）

本仓库自己**不实现** ε₀ 以上的序数，但可以拿**独立实现**
[basmat](https://github.com/kyodaisuu/basmat)（Bashicu Matrix Calculator，GPL-3.0）
给 `Explore.hs` 标 `unresolved` 的矩阵补一个**外部参考序数**，并交叉验证已定序的结果：

```bash
docker compose -f docker/compose.yaml build          # 在容器里编译 basmat（约 1 分钟）
docker compose -f docker/compose.yaml run --rm basmat -d "(0)(1)(2)[3]"

python tools/search.py ordinals --rows 2 --cols 4 --maxval 4 --only-unresolved --out out.jsonl
python tools/search.py table --input out.jsonl
```

实测收益：`Explore.exe 2 4 4` 的 83 个 `unresolved` 里 **42 个**拿到了序数，其中包括
`(0,0)(1,1) = e_0`、`(0,0)(1,1)(1,1) = e_1`、`(0,0)(1,1)(2,0) = e_w`、
`(0,0)(1,1)(2,2) = p0(p1(p2(0)))`。

校准过程中**实测**出三处必须显式处理的差异（细节与复现命令见
[tools/README.md](tools/README.md)）：

1. **份数差 1**：basmat 的 `[n]` = 好部 + **(n+1)** 份坏部，本仓库是 n 份
   ⇒ 等价地 `basmat[n] ≡ 本仓库[n+1]`（证据是 VERSIONS.md 里本仓库自己锁死的黄金值）；
2. **标准性判定不同**：basmat 用「从固定种子出发的递降序列」判定，
   判不标准就**不给序数** —— 83 个里有 41 个属于这种（本仓库认为它们是标准矩阵）；
3. **`Ord` 里不含常数项**：末尾的全零列被它逐步消去了，要按「末尾几个零括号」补回来，
   注意数的是**列**：`(0,0)(0,0)(0,0)` 是 3 个零括号，不是 6 个 0。

> **这些序数只能当外部参考**：`Test.hs` 的期望值仍必须能由本仓库的定义推导出来
> （CONTRIBUTING.md 铁律一/二）。
>
> basmat 是 **GPL-3.0** 的第三方程序：本仓库**不包含**它的源码或二进制，
> Dockerfile 只在构建时按**固定 commit** 从上游拉取（许可证说明见
> [docker/README.md](docker/README.md)）。我们只把它当**另一个进程**调用、
> 解析它的 stdout，不链接、不修改、不派生。

Python 工具只用标准库（沿用本仓库「零第三方依赖」的脾气）；
日常开发**不需要** Docker —— 只有 `tools/test_calibration.py` 与 `search.py` 需要。

## 如何加测试用例

1. 打开 `Test.hs`，把新用例加进对应的一组：
   - `goldenChecks`：矩阵 → 矩阵（BM4 的黄金展开）；
   - `propertyChecks`：性质与不变量；
   - `versionChecks`：**多版本**相关（BM4 行为不变、BM3.3 分歧算例、各版本展开仍是标准 BMS）；
   - `standardnessChecks`：**标准性**（`isStandardBMS` 的种子展开闭包：标准与非标准样例）；
   - `ordinalChecks`：序数引擎自检。
2. 期望值**必须**能由本仓库的定义（上面的展开规则 + [VERSIONS.md](VERSIONS.md)）推导，
   并用 `expandBMS` / `expandWith` 实测确认；
3. 跑 `make test`（或 `runghc Test.hs`）确认全绿；
4. 详细规矩（尤其是许可证与「分清『事实』与『表达』」）见 [CONTRIBUTING.md](CONTRIBUTING.md)。

## 如何构建

```bash
make build          # 编译 Test / Demo / Explore
make test           # 编译并跑测试
make demo           # 跑演示
cabal build         # 也可以用 cabal（见 minbms.cabal）
```

Windows 上 `make` 通常不在 PATH 里（本机实测只有 `mingw32-make`）。不想记 `make` /
`mingw32-make` 的名字时，用仓库自带的一键脚本即可（构建参数与 `Makefile` 完全一致）：

```bash
./build.sh                  # Linux / macOS / Git Bash：编译 Test / Demo / Explore
./clean.sh                  # 清掉构建产物（./clean.sh dist 连 dist-newstyle 一起清）

build.cmd                   # Windows（cmd.exe）：编译 Test.exe / Demo.exe / Explore.exe
clean.cmd                   # 清掉构建产物（clean.cmd dist 连 dist-newstyle 一起清）
```

> CI 的 `scripts` job 会在 Ubuntu / macOS / Windows 三系统上跑这些脚本，
> 防止脚本与 `Makefile` 漂移。

CI 见 `.github/workflows/ci.yml`（每次 push / PR 都会跑构建与测试）。
