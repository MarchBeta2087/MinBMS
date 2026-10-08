-- | 零依赖测试：在本文件所在目录执行
--
--   runghc Test.hs
--
-- 全部通过时打印「全部通过 ✅」；有失败则列出名称并返回非零退出码。
--
-- 铁律（详见 CONTRIBUTING.md）：
--   * 期望值只能由本仓库的定义推导（并用 expandBMS 实测确认）；
--   * 分清「事实」与「表达」：数学事实随便用，别人的**表达**不要大段复制，
--     用到了就标出处（各外部来源的许可状态不同，详见 CONTRIBUTING.md 铁律二）。
--   * 无法由定义/基本列确认的，**不要**写成测试用例，宁缺毋滥。
module Main (main) where

import BashicuMatrix
import Ordinal

import Data.List (transpose)
import Data.Maybe (isNothing)
import qualified Data.Set as Set
import System.Exit (exitFailure)
import Version       -- 多版本（BM4 / BM3.3）回归测试

-- BMatrix / Position 等类型别名统一由 BashicuMatrix 导出，此处不再重复定义。

------------------------------------------------------------------------
-- 小工具
------------------------------------------------------------------------

-- | 由「列」构造矩阵（initBMS 接受的是「行」）。
fromCols :: [[Integer]] -> BMatrix
fromCols = initBMS . transpose

-- | 展开结果（以列表示）。
expanded :: BMatrix -> Integer -> Maybe [[Integer]]
expanded m n = fmap matrixColumns (expandBMS m n)

-- | 一项检查。
data Check = Check String Bool

------------------------------------------------------------------------
-- 黄金用例（期望值由定义推导，并用 expandBMS 实测确认）
------------------------------------------------------------------------

-- ε₀ = (0,0)(1,1)（2 行）
epsilonZero :: BMatrix
epsilonZero = fromCols [[0, 0], [1, 1]]       -- 2 行：(0,0)(1,1)

-- ω^ω 有不止一种写法：2 行 (0,0)(1,0)(2,0) 与 1 行 (0)(1)(2)。
-- 不同矩阵对应同一序数是正常的：序数是「值」，矩阵只是「表示」。
oneRowOmegaOmega :: BMatrix
oneRowOmegaOmega = fromCols [[0], [1], [2]]   -- 1 行：(0)(1)(2)

-- 本仓库的「复制 n 次」约定**与行数无关**，统一是：
--   [n] = 好部 + n 份坏部，第 k 份加 k·Δ（k = 0..n-1）。
-- 实测确认：`(0)(1)[n]` 与 `(0,0)(1,0)[n]` 都是 n 份（不存在「差一格」）。
--   (0,0)(1,1)[0] = ∅，(0,0)(1,1)[1] = (0,0)，
--   (0,0)(1,1)[n] = (0,0)(1,0)(2,0)...(n-1,0)（n ≥ 2），即 (n-1) 层 ω 塔
--   (0)(1)(2)[n]  = (0)(1)^n                     即 ω^n
goldenChecks :: [Check]
goldenChecks =
  [ Check "(0,0)(1,1)[0] = 空矩阵" (expanded epsilonZero 0 == Just [])
  , Check "(0,0)(1,1)[1] = (0,0)"  (expanded epsilonZero 1 == Just [[0, 0]])
  , Check "(0,0)(1,1)[2] = (0,0)(1,0)"
      (expanded epsilonZero 2 == Just [[0, 0], [1, 0]])
  , Check "(0,0)(1,1)[3] = (0,0)(1,0)(2,0)"
      (expanded epsilonZero 3 == Just [[0, 0], [1, 0], [2, 0]])
  , Check "(0)(1)(2)[0] = (0)"    (expanded oneRowOmegaOmega 0 == Just [[0]])
  , Check "(0)(1)(2)[1] = (0)(1)" (expanded oneRowOmegaOmega 1 == Just [[0], [1]])
  , Check "(0)(1)(2)[2] = (0)(1)(1)"
      (expanded oneRowOmegaOmega 2 == Just [[0], [1], [1]])
  , Check "(0)(1)(2)[3] = (0)(1)(1)(1)"
      (expanded oneRowOmegaOmega 3 == Just [[0], [1], [1], [1]])
  ]

------------------------------------------------------------------------
-- 性质 / 不变量
------------------------------------------------------------------------

-- | 一批「标准且为极限」的样品矩阵（末列非全零）。
limitSamples :: [BMatrix]
limitSamples =
  [ fromCols [[0], [1]]
  , fromCols [[0], [1], [2]]
  , fromCols [[0, 0], [1, 0]]
  , fromCols [[0, 0], [1, 1]]
  , fromCols [[0, 0], [1, 1], [2, 2]]
  ]

propertyChecks :: [Check]
propertyChecks =
  [ Check "规则1：空矩阵展开仍为空"
      (and [ expanded (fromCols []) n == Just [] | n <- [0 .. 3] ])
  , Check "规则2：末列全零时，展开与 n 无关"
      (let m = fromCols [[0, 0], [1, 1], [0, 0]]
           r = expanded m 0
       in and [ expanded m n == r | n <- [0 .. 4] ])
  , Check "极限标准矩阵：expandBMS m 1 = 去掉末列"
      (and [ expanded m 1 == Just (init (matrixColumns m)) | m <- limitSamples ])
  , Check "展开结果仍满足 BMS 条件"
      (and [ maybe False isBasicBMS (expandBMS m n)
           | m <- limitSamples, n <- [0 .. 3] ])
  , Check "normalizeBMS (0,0)(1,1)(0,0)(0,0) = ((0,0)(1,1), 2)"
      (let (lp, off) = normalizeBMS (fromCols [[0, 0], [1, 1], [0, 0], [0, 0]])
       in matrixColumns lp == [[0, 0], [1, 1]] && off == 2)
  , Check "mkOrdinal 拒绝负复制次数"
      (isNothing (mkOrdinal epsilonZero (-1)))
  , Check "mkOrdinal 拒绝非标准矩阵（首列非全零）"
      (isNothing (mkOrdinal (fromCols [[1], [0]]) 0))
  , Check "expandedBMS (BO m n o) = 补 o 个全零列(expandBMS m n)"
      (case mkOrdinal (fromCols [[0, 0], [1, 1], [0, 0], [0, 0]]) 3 of
         Just bo ->
           case (expandedBMS bo,
                 expandBMS (ordinalMatrix bo) (ordinalCopies bo)) of
             (Just e1, Just e2) ->
               matrixColumns e1
                 == matrixColumns (appendZeroColumns (ordinalOffset bo) e2)
             _ -> False
         Nothing -> False)
  ]

------------------------------------------------------------------------
-- 多版本（BM4 / BM3.3）
------------------------------------------------------------------------

-- | 按版本展开的结果（以列表示）。
expandedWith :: Version -> BMatrix -> Integer -> Maybe [[Integer]]
expandedWith v m n = fmap matrixColumns (expandWith v m n)

-- (0,0,0)(1,1,1)(2,1,0)(1,1,1)：BM4 与「理想 BMS」分歧的最小著名算例。
-- 该矩阵展开后第 2 份坏部的末列，BM4 是 (3,2,0)、BM3.3 是 (3,1,0)。
-- 期望值由 Version.hs 里记录的规则（BM4 判定 + BM3.3 规则 2/3）推导，
-- 并用本程序实测确认；不是照抄外部原文（见 CONTRIBUTING.md 铁律二）。
liftingExample :: BMatrix
liftingExample = fromCols [[0, 0, 0], [1, 1, 1], [2, 1, 0], [1, 1, 1]]

versionChecks :: [Check]
versionChecks =
  [ Check "registry：BM4 与 BM3.3 都已登记"
      (map versionName versions == ["BM4", "BM3.3"])
  , Check "lookupVersion 能按名字找到版本"
      (fmap versionName (lookupVersion "BM3.3") == Just "BM3.3")
  , Check "lookupVersion 对未登记名字返回 Nothing"
      (isNothing (lookupVersion "BM9"))
  , Check "BM4 与原来的 expandBMS 行为完全一致"
      (and [ expandedWith bm4 m n == expanded m n
           | m <- versionSamples, n <- [0 .. 4] ])
  , Check "BM4：算例 [3] 末份坏部为 (2,2,0)(3,2,0)(4,3,0)"
      (expandedWith bm4 liftingExample 3
         == Just [[0,0,0],[1,1,1],[2,1,0],[1,1,0],[2,2,1],[3,2,0],[2,2,0],[3,3,1],[4,3,0]])
  , Check "BM3.3：算例 [3] 末份坏部为 (2,2,0)(3,1,0)(4,1,0)"
      (expandedWith bm33 liftingExample 3
         == Just [[0,0,0],[1,1,1],[2,1,0],[1,1,0],[2,2,1],[3,1,0],[2,2,0],[3,3,1],[4,1,0]])
  , Check "BM3.3 复制 0/1 次时与 BM4 相同（第 0 份不加阶差，故差异要到 n≥2 才显形）"
      (and [ expandedWith bm33 liftingExample n == expandedWith bm4 liftingExample n
           | n <- [0, 1] ])
  , Check "BM3.3 从复制 2 次起与本例的 BM4 不同"
      (expandedWith bm33 liftingExample 2 /= expandedWith bm4 liftingExample 2)
  , Check "两个版本的展开结果都仍是标准 BMS"
      (and [ maybe False isBasicBMS (expandWith v m n)
           | v <- versions, m <- versionSamples, n <- [0 .. 4] ])
  , Check "BM3.3 加阶差的项不多于 BM4（它只做减法）"
      (and [ noDeltaSubset bm33 bm4 m
           | m <- versionSamples, hasNonZeroLastColumn m ])
  ]

-- | 样品矩阵（覆盖 1/2/3 行，含末列全零的后继情形）。
versionSamples :: [BMatrix]
versionSamples =
  [ fromCols [[0], [1]]
  , fromCols [[0], [1], [2], [1]]
  , fromCols [[0, 0], [1, 1]]
  , fromCols [[0, 0], [1, 1], [2, 2], [2, 1], [1, 1], [2, 2]]
  , fromCols [[0, 0, 0], [1, 1, 1], [2, 1, 0], [1, 1, 1]]
  , fromCols [[0, 0, 0], [1, 1, 1], [2, 2, 2], [3, 3, 3], [4, 2, 0]]
  , fromCols [[0, 0], [1, 1], [0, 0]]       -- 末列全零（后继）
  ]

-- | 在坏部里，version a 「不加阶差」的位置是否包含 version b 的那些位置。
--   只对末列非全零的矩阵有意义（否则走的是规则 2，没有坏部）。
noDeltaSubset :: Version -> Version -> BMatrix -> Bool
noDeltaSubset a b m = case badRoot m of
  Nothing -> True
  Just rc ->
    let cols = matrixColumns m
        height = maximum (0 : map length cols)
        ps = [ (c, y) | c <- [rc .. length cols - 2], y <- [0 .. height - 1] ]
    in and [ versionAscend b m rc p || not (versionAscend a m rc p) | p <- ps ]

------------------------------------------------------------------------
-- 标准性（种子展开闭包）
------------------------------------------------------------------------

-- | 期望值来自 tools/STANDARDNESS.md 的实测结论：
--   README 三条（isBasicBMS）只是必要条件；真正的标准性 = 在
--   (0,..,0)(1,..,1)（行数+1）的展开闭包里。这些用例也已与 basmat 对拍一致。
standardnessChecks :: [Check]
standardnessChecks =
  [ Check "(0)(1) 标准（ω）" (isStandardBMS (fromCols [[0], [1]]))
  , Check "(0)(0)(1) 不标准（三条件之外）"
      (not (isStandardBMS (fromCols [[0], [0], [1]])))
  , Check "(0,0)(1,1) 标准（ε₀）"
      (isStandardBMS (fromCols [[0, 0], [1, 1]]))
  , Check "(0,0)(1,1)(2,0) 标准（e_ω）"
      (isStandardBMS (fromCols [[0, 0], [1, 1], [2, 0]]))
  , Check "(0,0)(1,1)(1,1) 标准（e_1）"
      (isStandardBMS (fromCols [[0, 0], [1, 1], [1, 1]]))
  , Check "(0,0,0)(1,1,1)(2,2,2)(3,2,2)(4,2,0) 标准"
      (isStandardBMS (fromCols [[0, 0, 0], [1, 1, 1], [2, 2, 2], [3, 2, 2], [4, 2, 0]]))
  , Check "(0,0,0)(1,1,1)(2,2,2)(3,2,2)(4,3,0) 不标准（被下探序列跨过）"
      (not (isStandardBMS (fromCols [[0, 0, 0], [1, 1, 1], [2, 2, 2], [3, 2, 2], [4, 3, 0]])))
  , Check "标准 ⇒ isBasicBMS（必要条件不被违反）"
      (and [ isBasicBMS m | m <- standardnessSamples, isStandardBMS m ])
  , Check "前缀封闭：标准矩阵的每个前缀都标准"
      (let cl = standardClosure 2 (StandardBounds 6 6 4)
           prefixes m = [ take i m | i <- [0 .. length m] ]
       in all (all (`Set.member` cl) . prefixes) (Set.toList cl))
  ]
  where
    standardnessSamples =
      [ fromCols [[0], [1]]
      , fromCols [[0, 0], [1, 1]]
      , fromCols [[0, 0], [1, 1], [2, 0]]
      , fromCols [[0, 0], [1, 1], [1, 1]]
      , fromCols [[0, 0, 0], [1, 1, 1], [2, 2, 2], [3, 2, 2], [4, 2, 0]]
      ]

------------------------------------------------------------------------
-- 序数引擎自检（Ordinal.hs）
------------------------------------------------------------------------

-- 自然数与 ω 的记号，供 oSupSeq 用例使用
natCNF :: Integer -> CNF
natCNF 0 = oZero
natCNF k = CNF [(oZero, k)]

omegaCNF :: CNF
omegaCNF = oOmegaPow oOne

ordinalChecks :: [Check]
ordinalChecks =
  [ Check "oShow 0 = \"0\"" (oShow oZero == "0")
  , Check "oSucc 0 = 1" (oShow (oSucc oZero) == "1")
  , Check "1 + 1 = 2" (oShow (oAdd oOne oOne) == "2")
  , Check "1 < ω" (oCmp oOne (oOmegaPow oOne) == LT)
  , Check "ω 是极限序数" (oIsLimit (oOmegaPow oOne))
  , Check "1 不是极限序数" (not (oIsLimit oOne))
  , Check "ω[n] = n+1"
      (and [ oShow (oFS (oOmegaPow oOne) n) == show (n + 1) | n <- [0 .. 4] ])
  , Check "ω^ω[n] = ω^(n+1)"
      (and [ oFS (oOmegaPow (oOmegaPow oOne)) n
               == oOmegaPow (CNF [(oZero, n + 1)])
           | n <- [0 .. 3] ])
  , Check "ω^ω + ω^ω = ω^ω·2"
      (oAdd (oOmegaPow (oOmegaPow oOne)) (oOmegaPow (oOmegaPow oOne))
         == CNF [(oOmegaPow oOne, 2)])
  , Check "ω + 1 + ω = ω·2"
      (oAdd (oAdd (oOmegaPow oOne) oOne) (oOmegaPow oOne)
         == CNF [(oOne, 2)])
  , Check "oSupSeq [0,1,2,3,4] = ω"
      (oSupSeq [natCNF k | k <- [0 .. 4]] == Just omegaCNF)
  , Check "oSupSeq [1, ω, ω·2, ω·3, ω·4] = ω²"
      (oSupSeq [oOne, omegaCNF, CNF [(oOne, 2)], CNF [(oOne, 3)], CNF [(oOne, 4)]]
         == Just (oOmegaPow (CNF [(oZero, 2)])))
  , Check "oSupSeq [ω, ω+1, ω+2, ω+3, ω+4] = ω·2"
      (oSupSeq [oAdd omegaCNF (natCNF k) | k <- [0 .. 4]]
         == Just (CNF [(oOne, 2)]))
  , Check "oSupSeq [ω^ω, ω^(ω+1), ω^(ω+2), ω^(ω+3)] = ω^(ω·2)"
      (oSupSeq [oOmegaPow (oAdd omegaCNF (natCNF (k + 1))) | k <- [0 .. 3]]
         == Just (oOmegaPow (CNF [(oOne, 2)])))
  , Check "oSupSeq [1, ω^ω, ω^(ω·2), ω^(ω·3)] = ω^(ω²)"
      (oSupSeq (oOne : [oOmegaPow (CNF [(oOne, k + 2)]) | k <- [0 .. 2]])
         == Just (oOmegaPow (oOmegaPow (CNF [(oZero, 2)]))))
  , Check "oSupSeq [0,0,0,0,0] = Nothing（退化序列不猜）"
      (oSupSeq (replicate 5 oZero) == Nothing)
  , Check "oSupSeq [1,1,1] = Nothing（非严格递增不猜）"
      (oSupSeq [oOne, oOne, oOne] == Nothing)
  ]

------------------------------------------------------------------------
-- 运行
------------------------------------------------------------------------

main :: IO ()
main = do
  let allChecks = goldenChecks ++ propertyChecks ++ versionChecks
                  ++ standardnessChecks ++ ordinalChecks
      fails = [ name | Check name ok <- allChecks, not ok ]
  putStrLn ("共 " ++ show (length allChecks)
            ++ " 项检查，失败 " ++ show (length fails) ++ " 项。")
  mapM_ (\n -> putStrLn ("  FAIL: " ++ n)) fails
  if null fails
    then putStrLn "全部通过"
    else exitFailure
