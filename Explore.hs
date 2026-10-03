-- | 用「定义」枚举标准 BMS，并**交叉验证**地给出序数（康托范式）。
--
-- 运行方式（在与本文件相同的目录下）：
--
--   runghc Explore.hs 1 5 3      -- 1 行、列数 ≤ 5、数值 ≤ 3（快）
--   runghc Explore.hs 2 4 4      -- 2 行、列数 ≤ 4、数值 ≤ 4
--   runghc Explore.hs 1 5 3 3    -- 第 4 个参数是基本列深度 k（默认 4）
--   runghc Explore.hs 1 6 5 4 200000   -- 第 5 个参数是燃料（默认 30000）
--
-- 内部带「燃料」（步数预算）与「矩阵列数上限」（maxAnalyzedCols）：
-- 任一超限的矩阵一律标 unresolved —— 所以本工具**永不卡死**，只会少给结果。
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

-- | 矩阵 -> 序数 的记忆表。
type Memo = Map.Map Key (Maybe CNF)

-- | 计算上下文：两张记忆表 + 燃料（步数预算）。
--
-- 燃料耗尽后一律返回 Nothing（unresolved），从而保证**永不卡死**：
-- 宁可少给结果，也绝不挂住。
data Ctx = Ctx
  { cMatrixMemo :: Memo
  , cOrdMemo :: Map.Map [CNF] (Maybe CNF)
  , cFuel :: Int
  }

freshCtx :: Int -> Ctx
freshCtx fuel = Ctx Map.empty Map.empty fuel

-- | 消耗 1 点燃料；返回 False 表示已耗尽。
burn :: Ctx -> (Ctx, Bool)
burn ctx
  | cFuel ctx <= 0 = (ctx, False)
  | otherwise = (ctx { cFuel = cFuel ctx - 1 }, True)

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

-- | 生成候选序数（分别尝试忽略前 0..maxDrop 项）。带燃料与记忆化。
candidates :: Int -> Int -> [CNF] -> Ctx -> (Ctx, [CNF])
candidates depth maxDrop os ctx0 = go (dropUpTo maxDrop os) ctx0 []
  where
    go [] ctx acc = (ctx, nubBy (==) (reverse acc))
    go (os' : rest) ctx acc =
      let (ctx1, sub) = if depth <= 0
                          then (ctx, Nothing)
                          else solveFS (depth - 1) (map lastExponent os') ctx
          (q, (e0, _)) = splitLast (head os')
          -- 候选 1：q + ω^(e0+1)（覆盖「末项系数在增长」与部分后继指数情形）
          -- 候选 2/3：末项指数本身是极限时，用递归得到的 e 再套一层 ω^e
          -- 注意：不做预筛，一律交给 aligns 验证，宁滥勿缺。
          cs = [ oAdd q (oOmegaPow (oSucc e0)) ]
               ++ [ oAdd q (oOmegaPow e) | Just e <- [sub] ]
               ++ [ oAdd q (oOmegaPow (oSucc e)) | Just e <- [sub] ]
      in go rest ctx1 (cs ++ acc)

dropUpTo :: Int -> [a] -> [[a]]
dropUpTo n xs = [ drop k xs | k <- [0 .. min n (length xs - 1)] ]

-- | 由基本列序列反推序数：在所有候选里取「能对齐的最小序数」。
--
-- 找不到、或燃料耗尽 → Nothing（绝不猜）。depth 为递归深度上限。
solveFS :: Int -> [CNF] -> Ctx -> (Ctx, Maybe CNF)
solveFS depth os ctx
  | depth <= 0 = (ctx, Nothing)
  | null os = (ctx, Nothing)
  | Just cached <- Map.lookup os (cOrdMemo ctx) = (ctx, cached)
  | otherwise =
      let (ctx1, ok) = burn ctx
      in if not ok
           then (ctx, Nothing)
           else
             let (ctx2, cands) = candidates depth maxDrop os ctx1
             in case [ t | t <- cands, aligns t os ] of
                  [] -> (rememberOrd os Nothing ctx2, Nothing)
                  hits ->
                    let t = minimumBy (\a b -> oCmp a b) hits
                    in (rememberOrd os (Just t) ctx2, Just t)
  where
    maxDrop = 2

rememberOrd :: [CNF] -> Maybe CNF -> Ctx -> Ctx
rememberOrd os v ctx = ctx { cOrdMemo = Map.insert os v (cOrdMemo ctx) }

------------------------------------------------------------------------
-- 矩阵 -> 序数（带记忆化与交叉验证）
------------------------------------------------------------------------

-- | 矩阵（以列表示）换算成序数。
--
--   * 空矩阵             -> 0
--   * 末列全零（后继）   -> oSucc (ordOf (去掉末列))
--   * 末列非全零（极限） -> 由基本列 os 反推 t，并要求 t 的基本列与 os 完全一致
--
-- depth 为递归深度上限；燃料或深度耗尽即 unresolved（保证不卡死）。
ordOf :: Int -> Int -> Key -> Ctx -> (Ctx, Maybe CNF)
ordOf k depth cols ctx
  | Just cached <- Map.lookup cols (cMatrixMemo ctx) = (ctx, cached)
  | depth <= 0 = (ctx, Nothing)
  | length cols > maxAnalyzedCols = (ctx, Nothing)   -- 太大：放弃，避免列数爆炸
  | otherwise =
      let (ctx1, ok) = burn ctx
      in if not ok
           then (ctx, Nothing)
           else let (ctx2, res) = compute cols ctx1
                in (rememberMat cols res ctx2, res)
  where
    compute [] c = (c, Just oZero)
    compute cs c
      | isAllZeroInThisColumn (last cs) =
          let (c1, r) = ordOf k (depth - 1) (init cs) c
          in (c1, fmap oSucc r)
      | otherwise =
          let m = fromCols cs
              fsList = [ fmap matrixColumns (expandBMS m n)
                       | n <- [0 .. toInteger k] ]
          in case sequence fsList of
               Nothing -> (c, Nothing)
               Just fss ->
                 let (c1, ords) = collectOrds fss c
                 in case sequence ords of
                      Nothing -> (c1, Nothing)
                      Just os ->
                        -- 极限矩阵的基本列必须严格递增，否则视为不可验证。
                        if strictlyIncreasing os
                          then solveFS 5 os c1
                          else (c1, Nothing)

    collectOrds [] c = (c, [])
    collectOrds (x : xs) c =
      let (c1, y) = ordOf k (depth - 1) x c
          (c2, ys) = collectOrds xs c1
      in (c2, y : ys)

rememberMat :: Key -> Maybe CNF -> Ctx -> Ctx
rememberMat cols v ctx = ctx { cMatrixMemo = Map.insert cols v (cMatrixMemo ctx) }

strictlyIncreasing :: [CNF] -> Bool
strictlyIncreasing os = and (zipWith (\a b -> oCmp a b == LT) os (drop 1 os))

------------------------------------------------------------------------
-- 主程序
------------------------------------------------------------------------

main :: IO ()
main = do
  args <- getArgs
  let (rows, maxCols, maxVal, k, fuel) = case args of
        [a, b, c]       -> (read a, read b, read c, 4, fuelBudget)
        [a, b, c, d]    -> (read a, read b, read c, read d, fuelBudget)
        [a, b, c, d, e] -> (read a, read b, read c, read d, read e)
        _               -> (1, 5, 3, 4, fuelBudget)
  putStrLn ("序数分析：行数 = " ++ show rows
            ++ "，列数 ≤ " ++ show maxCols
            ++ "，数值 ≤ " ++ show maxVal
            ++ "，基本列深度 n = 0.." ++ show k
            ++ "，燃料 = " ++ show fuel)
  putStrLn "unresolved = 本工具无法用基本列交叉验证的结果；绝不猜测。"
  let ms = enumerate rows maxCols maxVal
  putStrLn ("枚举到 " ++ show (length ms) ++ " 个标准矩阵：")
  let step (ctx, acc) cols =
        let (ctx', r) = ordOf k 20 cols ctx
        in (ctx', (cols, r) : acc)
      (finalCtx, revResults) = foldl' step (freshCtx fuel, []) ms
      results = reverse revResults
  mapM_ (report k) results
  let ok = length [ () | (_, Just _) <- results ]
  putStrLn ("---- 已定序 " ++ show ok ++ " 个；unresolved "
            ++ show (length results - ok) ++ " 个 ----")
  putStrLn ("剩余燃料：" ++ show (cFuel finalCtx)
            ++ "（燃料/深度耗尽时其余矩阵会被标 unresolved —— 这是为了永不卡死）")
  putStrLn "提示：把 unresolved 的矩阵发到 issue / PR，任何人都可以帮忙补。"
  putStrLn "（期望值必须能由本仓库的定义 + 基本列交叉验证得到，禁止照抄外部原文。）"

-- | 总步数预算。调大可提高覆盖率，但会更慢；调小则更快、更多 unresolved。
-- 注意：每一步可能包含一次 expandBMS + 若干次 oFS，所以这个数不要太大，
-- 否则「有上限」仍然可能跑很久。经验值：3 万步 ≈ 几十秒。
fuelBudget :: Int
fuelBudget = 30000

-- | 单个矩阵参与分析的**最大列数**。超过就直接放弃（标 unresolved）。
--
-- 为什么必须有它：深层展开会让列数爆炸（把坏部复制 n 份，而坏部本身
-- 在下一层又变长）。没有这道闸，单步代价会无限增长，
-- 「有燃料上限也照样卡死」。取值要足够大到能覆盖 ω^ω 那一档。
maxAnalyzedCols :: Int
maxAnalyzedCols = 200

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
