# BMS 版本与「如何添加版本」

## 为什么版本可以只差一点点

BMS 有 BM1、BM2、BM2.3、BM3、BM3.1、BM3.2、BM3.3、BM4 等许多版本，但它们**共享同一副骨架**：

- 行、列、项、父项、祖先项的定义；
- 坏根 / 好部 / 坏部的切分；
- 阶差向量 Δ 的算法；
- 展开的三条规则（空矩阵、末列全零、复制坏部）。

真正随版本变化的，只有一件事：**坏部复制时，哪些位置的项要加上 Δ**。

本项目把这个「唯一的可变点」抽成了一个类型（见 `BashicuMatrix.hs`）：

```haskell
-- | 「坏部复制时哪些项要加阶差」的判定规则。
--   给定矩阵与坏根所在列，返回「位置 -> 是否加阶差」的查询函数。
type Ascension = BMatrix -> Int -> (Position -> Bool)
```

于是**一个版本 = 一个名字 + 一条 `Ascension`**（见 `Version.hs`）：

```haskell
data Version = Version
  { versionName   :: String
  , versionAscend :: Ascension
  }
```

展开的公共入口是 `expandBMSWith`，所有版本都走它：

```haskell
expandBMSWith :: Ascension -> BMatrix -> Integer -> Maybe BMatrix
expandBMS     :: BMatrix -> Integer -> Maybe BMatrix   -- = expandBMSWith ascendBM4
```

> **「复制 n 次」的约定（对所有版本统一）**：`[n]` = 好部 + **n 份**坏部，
> 第 k 份加 `k·Δ`（k = 0..n-1）。与行数无关 —— 实测 `(0)(1)[n]` 与
> `(0,0)(1,0)[n]` 都是 n 份。

---

## 已支持的版本

| 名字 | 出处 | `Ascension` | 说明 |
|---|---|---|---|
| `BM4` | Bashicu，2018-09 | `ascendBM4` | 现行版本。坏部中位于 `(c, y)` 的项加 Δ，当且仅当**同一行**的祖先链包含坏根列上的 `(坏根列, y)`。 |
| `BM3.3` | rpakr & Ecl1psed，2019-03 | `ascendBM33` | 在 BM4 之外再排除两类项（下文的规则 2、规则 3）。曾被认为是理想无提升 BMS，现已发现有提升。 |

### BM3.3 的两条额外规则

设 A 是坏部中位于第 y 行的一项：

1. **规则 2**：若 A **正下方**的项已被判定为不加 Δ（无论是被本条规则判的，还是被 BM4 的判定判的），
   且 A 的父项位于坏根列，且 A 的值 **≥** 同一行末项的值 —— 那么 A 也不加 Δ。
2. **规则 3**：若 B 的祖先项中存在满足规则 2 的项 —— 那么 B 也不加 Δ。

因为规则 2 要用到「正下方那一项」的**最终**判定，所以 `noDeltaBM33` 必须
**自下而上**逐行计算（行号从大到小），不能按任意顺序。

算例（这也是测试里锁住的黄金用例）：`(0,0,0)(1,1,1)(2,1,0)(1,1,1)[3]`

```
BM4   = (0,0,0)(1,1,1)(2,1,0)(1,1,0)(2,2,1)(3,2,0)(2,2,0)(3,3,1)(4,3,0)
BM3.3 = (0,0,0)(1,1,1)(2,1,0)(1,1,0)(2,2,1)(3,1,0)(2,2,0)(3,3,1)(4,1,0)
                                        ↑ 只有这一处阶差被规则 2/3 排除了
```

---

## 怎么用

**库**（`Version.hs`）：

```haskell
import BashicuMatrix
import Version

expandWith bm33 matrix 3        -- 按 BM3.3 展开
lookupVersion "BM3.3"           -- Just (BM3.3)
map versionName versions        -- ["BM4", "BM3.3"]
```

**命令行**（`Explore.hs`，默认 BM4）：

```bash
runghc Explore.hs 1 5 3              # BM4
runghc Explore.hs --bm=BM3.3 1 5 3   # BM3.3
```

`--bm=` 后面必须是 `versions` 里登记过的名字；否则会报错并列出可用版本。
注意 `Explore.hs` 的记忆表键是矩阵、**不含版本**，所以一次运行只用一个版本。

---

## 如何添加一个新版本

以「加一个叫 `BMX` 的版本」为例，一共 5 步。

### 第 1 步：写一条 `Ascension`

在 `Version.hs` 里加一个函数。签名的含义是：
「给定矩阵和坏根所在列，返回一个『位置 → 是否要加 Δ』的查询函数」。

```haskell
-- | BMX：<这里用一句话写清判定规则>。
ascendBMX :: Ascension
ascendBMX matrix rootColumn =
  \pos@(columnIndex, rowIndex) -> <你的判定>
```

判定里可以直接用的工具（都由 `BashicuMatrix` 导出）：

| 工具 | 含义 |
|---|---|
| `valueAt matrix pos` | 取该位置的项（越界返回 `Nothing`） |
| `fatherOf matrix pos` | 父项位置 |
| `isAncestorOf matrix cand target` | `cand` 是否为 `target` 的祖先项（**含自身**） |
| `matrixColumns matrix` | 按列取出的所有值 |
| `badRootPosition matrix` / `badRoot matrix` | 坏根位置 / 坏根列 |
| `differenceVector matrix` | 阶差向量 Δ |

两个现成的参考实现：

- 只在一行内判定、不需要跨行信息 → 照 `ascendBM4` 写（它是逐项无状态的）。
- 需要「下方项的结果」这类顺序依赖 → 照 `ascendBM33` 写：先算一张
  `Map Position Bool`，再返回查表函数。`Ascension` 的类型故意写成
  `BMatrix -> Int -> (Position -> Bool)`（而不是把位置也并进参数），
  就是为了让你能**预先算好整张掩码**而不是逐项重算。

### 第 2 步：定义版本常量

```haskell
bmx :: Version
bmx = Version "BMX" ascendBMX
```

### 第 3 步：登记进 `versions`

```haskell
versions :: [Version]
versions = [bm4, bm33, bmx]
```

`lookupVersion`、`Explore.hs --bm=`、测试里的不变量都靠这个列表自动生效，**不用改别处**。

### 第 4 步：补测试（`Test.hs`）

至少要有这三类，缺一不可：

1. **黄金用例**：找一个你的版本与已有版本**结果不同**的矩阵，把双方的展开逐列写死。
   期望值必须能由你实现的规则推导，并用本程序实测确认（见 CONTRIBUTING.md 铁律一/二）。
2. **不变量**：`expandWith v m n` 的结果仍满足 `isBasicBMS`（标准 BMS 三条件）。
3. **与 BM4 的关系**（如果你的版本是 BM4 的收缩）：
   `noDeltaSubset` 可以验证「你的版本不加 Δ 的位置 ⊇ BM4 不加 Δ 的位置」。

没有「分歧算例」的版本要警惕：那很可能说明你的 `Ascension` 和 BM4 是同一个函数，
新版本只是换了个名字。

### 第 5 步：更新文档

- 在本文件的版本表里加一行（名字、出处、`Ascension`、一句话说明）；
- 若版本有已知问题（比如 BM3.3 的提升效应），一并写清。

---

## 边界：不是所有版本都能这样加

目前的可插拔点**只有 `Ascension`**。它覆盖的是「BM3 / BM3.1 / BM3.2 / BM3.3 / BM4 /
UPMS 这条分析友好线」—— 这些版本改的全是「复制时哪些项加 Δ」。

有些老版本改的是**别的旋钮**，例如：

- **BM1 / BM1.1 / BM2 / BM2.3** 的「坏根怎么找」用的是 upper-branch-ignoring model，
  与本项目 `fatherOf` 的定义不同；
- 少数版本还会改「好部 / 坏部怎么切」。

要支持这些，得先把 `BashicuMatrix.hs` 里对应的部分（如 `badRootPosition`）
也参数化成一个可替换的记录，再扩展 `Version`。**做之前请先开 issue 讨论**，
因为那会动到所有版本的公共语义，需要同步更新 README 的定义章节。

---

## 参考资料

- 《大数理论》（曹知秋，2026-08-30）Chapter 13. Bashicu 矩阵，13.1 BMS 的定义，P343、P344
  —— 本项目 README 中「概念 / 条件 / 展开规则」的来源。
- rpakr, *Bashicu Matrix Version 3.3*（Googology Wiki 用户博客）—— BM3.3 定义与算例来源。
- Googology Wiki `BM3.3` 条目 —— 上文规则 2、规则 3 的措辞来源。

> 引用出处是允许且鼓励的；**别人的「表达」不要大段复制**。
> 注意这些来源的许可状态各不相同（《大数理论》**未声明许可**，Googology Wiki 是 **CC BY-SA**），
> 但本项目的做法对两者都成立：**只重述数学内容（事实不受著作权保护）+ 标注出处**。
> 详见 CONTRIBUTING.md 铁律二「分清『事实』与『表达』」。
