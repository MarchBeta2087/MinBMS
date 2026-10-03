-- | 用「定义」枚举标准 BMS，并**交叉验证**地给出序数（康托范式）。
--
-- 运行方式（在与本文件相同的目录下）：
--
--   runghc Explore.hs 1 6 5      -- 1 行、列数 ≤ 6、数值 ≤ 5
--   runghc Explore.hs 2 4 4      -- 2 行、列数 ≤ 4、数值 ≤ 4
--   runghc Explore.hs 1 6 5 3    -- 第 4 个参数是基本列深度 k（默认 4）
--
-- 铁律：序号一栏只写「能通过基本列交叉验证」的结果；
-- 验证不通过的矩阵一律标 unresolved，并原样打印其基本列供人工分析。
module Main (main) where

import BashicuMatrix
import Ordinal

import Control.Monad (replicateM)
import Data.List (foldl', intercalate, minimumBy, nubBy, transpose)
import qualified Data.Map.Strict as Map
import System.Environment (getArgs)

type BMatrix = GBashicuMatrix [GColumn [Integer]]
type Key = [[Integer]]
type Memo = Map.Map Key (Maybe CNF)

------------------------------------------------------------------------
-- 基本工具
------------------------------------------------------------------------

-- | 由「列」构造矩阵（initBMS 接受的是「行」）。
fromCols :: [[Integer]] -> BMatrix
fromCols = initBMS . transpose

-- | (0,0)(1,1) 风格的显示。
prettyCols :: [[Integer]] -> String
prettyCols = concatMap (\c -> "(" ++ intercalate "," (map show c) ++ ")")

------------------------------------------------------------------------
-- 枚举（BFS：按列数从少到多）
------------------------------------------------------------------------

-- | 高度 h、取值 ≤ v 的所有「非递增」列（对应 BMS 条件 2）。
columnsOf :: Int -> Integer -> [[Integer]]
columnsOf h v = [ c | c <- replicateM h [0 .. v], nonIncreasing c ]
  where
    nonIncreasing c = and (zipWith (>=) c (drop 1 c))

-- | 枚举标准矩阵：列数 1..maxCols，首列全零，并过滤 isBasicBMS。
enumerate :: Int -> Int -> Integer -> [[[Integer]]]
enumerate h maxCols v =
  nubBy (==)
    [ cols
    | n <- [1 .. maxCols]
    , rest <- replicateM (n - 1) allCols
    , let cols = replicate h 0 : rest
    , isBasicBMS (fromCols cols)
    ]
  where
    allCols = columnsOf h v

------------------------------------------------------------------------
-- 由基本列反推序数（纯序数层面，不涉及矩阵）
------------------------------------------------------------------------

lastExponent :: CNF -> CNF
lastExponent (CNF []) = oZero
lastExponent (CNF ts) = fst (last ts)

splitLast :: CNF -> (CNF, (CNF, Integer))
splitLast (CNF []) = (oZero, (oZero, 1))
splitLast (CNF ts) = (CNF (init ts), last ts)

-- | 「基本列对齐」判定。
--
-- 不同系统/实现对「第 n 项」的下标约定可能差一格，例如
--   1 行  (0)(1)[n]      = (0)^n        （从 0 起）
--   2 行  (0,0)(1,0)[n]  = (0,0)^(n+1)  （从 1 起）
-- 因此这里允许整体错位：只要存在平移 d，使忽略前几项后逐项相等即算对齐。
aligns :: CNF -> [CNF] -> Bool
aligns t os = any okShift [-3 .. 3]
  where
    okShift d =
      let pairs = [ (o, oFS t (toInteger n + d))
                  | (n, o) <- zip [0 ..] os
                  , toInteger n + d >= 0
                  ]
      in length pairs >= min 3 (length os)
           && all (\(a, b) -> a == b) pairs

-- | 生成候选序数（分别尝试忽略前 0、1、2 项）。
candidates :: Int -> [CNF] -> [CNF]
candidates depth os = nubBy (==) (concatMap candsFrom (dropUpTo 2 os))
  where
    candsFrom [] = []
    candsFrom os' =
      let (q, (e0, _)) = splitLast (head os')
          sub = if depth <= 0
                  then Nothing
                  else solveFS (depth - 1) (map lastExponent os')
      -- 候选 1：q + ω^(e0+1)（覆盖「末项系数在增长」与部分后继指数情形）
      -- 候选 2/3：末项指数本身是极限时，用递归得到的 e 再套一层 ω^e
      -- 注意：这里不做 c0 的预筛，一律交给 aligns 验证，宁滥勿缺。
      in [ oAdd q (oOmegaPow (oSucc e0)) ]
         ++ [ oAdd q (oOmegaPow e) | Just e <- [sub] ]
         ++ [ oAdd q (oOmegaPow (oSucc e)) | Just e <- [sub] ]

dropUpTo :: Int -> [a] -> [[a]]
dropUpTo n xs = [ drop k xs | k <- [0 .. min n (length xs - 1)] ]

-- | 由基本列序列反推序数：在所有候选里取「能对齐的最小序数」。
-- 找不到就返回 Nothing（绝不猜）。depth 为递归深度上限。
solveFS :: Int -> [CNF] -> Maybe CNF
solveFS depth os
  | depth <= 0 = Nothing
  | null os = Nothing
  | otherwise =
      case [ t | t <- candidates depth os, aligns t os ] of
        [] -> Nothing
        ts -> Just (minimumBy (\a b -> oCmp a b) ts)

------------------------------------------------------------------------
-- 矩阵 -> 序数（带记忆化与交叉验证）
------------------------------------------------------------------------

-- | 矩阵（以列表示）换算成序数。
--
--   * 空矩阵             -> 0
--   * 末列全零（后继）   -> oSucc (ordOf (去掉末列))
--   * 末列非全零（极限） -> 由基本列 os 反推 t，并要求 t 的基本列与 os 完全一致
--
-- depth 为递归深度上限（兜底防止意外不终止）；触顶即 unresolved。
ordOf :: Int -> Int -> Memo -> Key -> (Memo, Maybe CNF)
ordOf k depth memo cols
  | Just cached <- Map.lookup cols memo = (memo, cached)
  | depth <= 0 = (memo, Nothing)
  | null cols = (Map.insert cols (Just oZero) memo, Just oZero)
  | isAllZeroInThisColumn (last cols) =
      let (m1, r) = ordOf k (depth - 1) memo (init cols)
          res = fmap oSucc r
      in (Map.insert cols res m1, res)
  | otherwise =
      let m = fromCols cols
          fsList = [ fmap matrixColumns (expandBMS m n) | n <- [0 .. toInteger k] ]
      in case sequence fsList of
           Nothing -> (Map.insert cols Nothing memo, Nothing)
           Just fss ->
             let (m1, ords) = collectOrds memo fss
             in case sequence ords of
                  Nothing -> (Map.insert cols Nothing m1, Nothing)
                  Just os ->
                    -- 极限矩阵的基本列必须严格递增，否则视为不可验证。
                    let res = if strictlyIncreasing os then solveFS 8 os else Nothing
                    in (Map.insert cols res m1, res)
  where
    collectOrds mem [] = (mem, [])
    collectOrds mem (x : xs) =
      let (m1, y) = ordOf k (depth - 1) mem x
          (m2, ys) = collectOrds m1 xs
      in (m2, y : ys)

strictlyIncreasing :: [CNF] -> Bool
strictlyIncreasing os = and (zipWith (\a b -> oCmp a b == LT) os (drop 1 os))

------------------------------------------------------------------------
-- 主程序
------------------------------------------------------------------------

main :: IO ()
main = do
  args <- getArgs
  let (rows, maxCols, maxVal, k) = case args of
        [a, b, c]    -> (read a, read b, read c, 4)
        [a, b, c, d] -> (read a, read b, read c, read d)
        _            -> (1, 6, 5, 4)
  putStrLn ("序数分析：行数 = " ++ show rows
            ++ "，列数 ≤ " ++ show maxCols
            ++ "，数值 ≤ " ++ show maxVal
            ++ "，基本列深度 n = 0.." ++ show k)
  putStrLn "unresolved = 本工具无法用基本列交叉验证的结果；绝不猜测。"
  let ms = enumerate rows maxCols maxVal
  putStrLn ("枚举到 " ++ show (length ms) ++ " 个标准矩阵：")
  let step (mem, acc) cols =
        let (mem', r) = ordOf k 80 mem cols
        in (mem', (cols, r) : acc)
      (_, revResults) = foldl' step (Map.empty, []) ms
      results = reverse revResults
  mapM_ (report k) results
  let ok = length [ () | (_, Just _) <- results ]
  putStrLn ("---- 已定序 " ++ show ok ++ " 个；unresolved "
            ++ show (length results - ok) ++ " 个 ----")
  putStrLn "提示：把 unresolved 的矩阵发到 issue / PR，任何人都可以帮忙补。"
  putStrLn "（期望值必须能由本仓库的定义 + 基本列交叉验证得到，禁止照抄外部原文。）"

report :: Int -> ([[Integer]], Maybe CNF) -> IO ()
report _ (cols, Just t) =
  putStrLn ("  " ++ pad (prettyCols cols) ++ "= " ++ oShow t)
report k (cols, Nothing) = do
  let m = fromCols cols
      fsList = [ fmap matrixColumns (expandBMS m n) | n <- [0 .. toInteger k] ]
      shown = case sequence fsList of
                Just fss -> intercalate " , " (map prettyCols fss)
                Nothing  -> "<展开失败>"
  putStrLn ("  " ++ pad (prettyCols cols) ++ "= unresolved")
  putStrLn ("      n=0.." ++ show k ++ ": " ++ shown)

pad :: String -> String
pad s = s ++ replicate (max 1 (30 - length s)) ' '
