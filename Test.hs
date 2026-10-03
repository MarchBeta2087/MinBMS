-- | 零依赖测试：在本文件所在目录执行
--
--   runghc Test.hs
--
-- 全部通过时打印「全部通过 ✅」；有失败则列出名称并返回非零退出码。
--
-- 铁律（详见 CONTRIBUTING.md）：
--   * 期望值只能由本仓库的定义推导（并用 expandBMS 实测确认），
--     禁止照抄任何外部原文的表达（CC BY-SA 等）。
--   * 无法由定义/基本列确认的，**不要**写成测试用例，宁缺毋滥。
module Main (main) where

import BashicuMatrix
import Ordinal

import Data.List (transpose)
import Data.Maybe (isNothing)
import System.Exit (exitFailure)

type BMatrix = GBashicuMatrix [GColumn [Integer]]

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

-- ω^ω 的两种写法
omegaOmega :: BMatrix
omegaOmega = fromCols [[0, 0], [1, 1]]        -- 2 行：(0,0)(1,1)

oneRowOmegaOmega :: BMatrix
oneRowOmegaOmega = fromCols [[0], [1], [2]]   -- 1 行：(0)(1)(2)

-- 注意本仓库的「复制 n 次」约定（2 行从 0 起、1 行从 ω^0 起，差一格）：
--   (0,0)(1,1)[n] = (0,0)(1,0)...(n-1,0)   即 ω^(n-1)
--   (0)(1)(2)[n]  = (0)(1)^n               即 ω^n
goldenChecks :: [Check]
goldenChecks =
  [ Check "(0,0)(1,1)[0] = 空矩阵" (expanded omegaOmega 0 == Just [])
  , Check "(0,0)(1,1)[1] = (0,0)"  (expanded omegaOmega 1 == Just [[0, 0]])
  , Check "(0,0)(1,1)[2] = (0,0)(1,0)"
      (expanded omegaOmega 2 == Just [[0, 0], [1, 0]])
  , Check "(0,0)(1,1)[3] = (0,0)(1,0)(2,0)"
      (expanded omegaOmega 3 == Just [[0, 0], [1, 0], [2, 0]])
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
      (isNothing (mkOrdinal omegaOmega (-1)))
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
-- 序数引擎自检（Ordinal.hs）
------------------------------------------------------------------------

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
  ]

------------------------------------------------------------------------
-- 运行
------------------------------------------------------------------------

main :: IO ()
main = do
  let allChecks = goldenChecks ++ propertyChecks ++ ordinalChecks
      fails = [ name | Check name ok <- allChecks, not ok ]
  putStrLn ("共 " ++ show (length allChecks)
            ++ " 项检查，失败 " ++ show (length fails) ++ " 项。")
  mapM_ (\n -> putStrLn ("  FAIL: " ++ n)) fails
  if null fails
    then putStrLn "全部通过"
    else exitFailure
