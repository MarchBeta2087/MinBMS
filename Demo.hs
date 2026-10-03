module Demo (main) where

import BashicuMatrix

-- 运行方式：在与 BashicuMatrix.hs 相同的目录下执行
--   runghc Demo.hs
-- 或在 GHCi 中 :l Demo.hs 后输入 main

-- BMatrix / Position 等类型别名统一由 BashicuMatrix 导出，此处不再重复定义。

------------------------------------------------------------------------
-- 示例矩阵
------------------------------------------------------------------------

-- (0,0)(1,1) = ε₀
epsilonZero :: BMatrix
epsilonZero = initBMS [[0,1],[0,1]]

-- (0,0)(1,1)(0,0) = ε₀ + 1
epsilonZeroPlus1 :: BMatrix
epsilonZeroPlus1 = initBMS [[0,1,0],[0,1,0]]

-- (0,0)(1,1)(0,0)(0,0) = ε₀ + 2
epsilonZeroPlus2 :: BMatrix
epsilonZeroPlus2 = initBMS [[0,1,0,0],[0,1,0,0]]

-- 《大数理论》式 (13.4)：(0,0,0)(1,1,1)(2,1,1)(3,1,0)(2,2,0)
bookExample1 :: BMatrix
bookExample1 = initBMS [[0,1,2,3,2],[0,1,1,1,2],[0,1,1,0,0]]

-- 非等长输入：各列末尾省略的 0 会自动补齐
-- initBMS [[0,1],[0,1],[0]] = (0,0,0)(1,1,0)（3 行；本工具不对 ≥3 行的序数做承诺）
raggedInput :: BMatrix
raggedInput = initBMS [[0,1],[0,1],[0]]

------------------------------------------------------------------------
-- 演示辅助
------------------------------------------------------------------------

hr :: IO ()
hr = putStrLn (replicate 60 '-')

-- 同时显示列记法和矩阵形式
showMatrix :: BMatrix -> IO ()
showMatrix m = do
  putStrLn ("  " ++ show m)
  mapM_ (putStrLn . ("  " ++)) (lines (renderBMS m))

-- 演示 expandBMS（书上的三条展开规则）
demoExpand :: String -> BMatrix -> Integer -> IO ()
demoExpand label m n = do
  putStrLn (label ++ " [" ++ show n ++ "] =")
  case expandBMS m n of
    Nothing -> putStrLn "  Nothing"
    Just e  -> showMatrix e

-- 演示 normalizeBMS（BMS + x 分解）
demoNormalize :: String -> BMatrix -> IO ()
demoNormalize label m =
  let (limitPart, offset) = normalizeBMS m
  in putStrLn (label ++ " = " ++ show limitPart ++ " + " ++ show offset)

-- 演示 mkOrdinal + expandedBMS（非常规序数：极限部分基本列第 n 项 + 偏移）
demoOrdinal :: String -> BMatrix -> Integer -> IO ()
demoOrdinal label m n = case mkOrdinal m n of
  Nothing -> putStrLn (label ++ " -> Nothing")
  Just bo -> do
    putStrLn (label ++ " -> " ++ show bo)
    case expandedBMS bo of
      Nothing -> putStrLn "  展开失败"
      Just e  -> showMatrix e

-- 演示 ordinalSequence（基本列的前几项）
demoSequence :: String -> BMatrix -> IO ()
demoSequence label m = case ordinalSequence m of
  Nothing -> putStrLn (label ++ " -> Nothing")
  Just os -> do
    putStrLn label
    mapM_ (putStrLn . ("  " ++) . show) (take 3 os)

------------------------------------------------------------------------
-- 主程序
------------------------------------------------------------------------

main :: IO ()
main = do
  putStrLn "== 1. 构造与显示 =="
  putStrLn "epsilonZero ="
  showMatrix epsilonZero
  -- BMS [[0,0],[1,1]]
  -- 0 1
  -- 0 1
  hr

  putStrLn "== 2. 非等长输入自动补零 =="
  putStrLn "initBMS [[0,1],[0,1],[0]] ="
  showMatrix raggedInput
  -- BMS [[0,0,0],[1,1,0]]
  -- 0 1
  -- 0 1
  -- 0 0
  hr

  putStrLn "== 3. expandBMS：末列非全零（规则 3），ε₀ 的基本列 =="
  mapM_ (demoExpand "epsilonZero" epsilonZero) [0 .. 3]
  -- epsilonZero [0] = BMS []              （好部为空，复制 0 次）
  -- epsilonZero [1] = BMS [[0,0]]         = 1
  -- epsilonZero [2] = BMS [[0,0],[1,0]]   = ω
  -- epsilonZero [3] = BMS [[0,0],[1,0],[2,0]] = ω^ω
  hr

  putStrLn "== 4. expandBMS：末列全零（规则 2，后继序数删去末列）与空矩阵（规则 1）=="
  demoExpand "epsilonZeroPlus1" epsilonZeroPlus1 2
  -- BMS [[0,0],[1,1]]    （删去全零末列，与复制次数无关）
  demoExpand "initBMS []" (initBMS []) 4
  -- BMS []
  hr

  putStrLn "== 5. 书例 1（式 13.4）的展开 =="
  demoExpand "bookExample1" bookExample1 2
  -- BMS [[0,0,0],[1,1,1],[2,1,1],[3,1,0],[2,1,1],[3,1,1],[4,1,0]]
  -- 与式 (13.18) 前 7 列一致
  hr

  putStrLn "== 6. normalizeBMS：BMS + x 分解 =="
  demoNormalize "epsilonZero"      epsilonZero
  -- BMS [[0,0],[1,1]] + 0
  demoNormalize "epsilonZeroPlus2" epsilonZeroPlus2
  -- BMS [[0,0],[1,1]] + 2
  demoNormalize "bookExample1"    bookExample1
  -- BMS [[0,0,0],[1,1,1],[2,1,1],[3,1,0],[2,2,0]] + 0
  hr

  putStrLn "== 7. mkOrdinal + expandedBMS：非常规序数「基本列第 n 项 + 偏移」=="
  demoOrdinal "epsilonZeroPlus2" epsilonZeroPlus2 4
  -- BO {matrix = BMS [[0,0],[1,1]], copies = 4, offset = 2}
  -- 展开 = BMS [[0,0],[1,0],[2,0],[3,0],[0,0],[0,0]]，即 ε₀[4] + 2 = ω^ω^ω + 2
  demoOrdinal "bookExample1" bookExample1 1
  -- BO {matrix = ..., copies = 1, offset = 0}
  -- 展开 = BMS [[0,0,0],[1,1,1],[2,1,1],[3,1,0]]（好部 + 原始坏部）
  hr

  putStrLn "== 8. ordinalSequence：惰性无限基本列 =="
  demoSequence "bookExample1 的基本列（取前 3 项）" bookExample1
  -- BO {matrix = ..., copies = 0, offset = 0}
  -- BO {matrix = ..., copies = 1, offset = 0}
  -- BO {matrix = ..., copies = 2, offset = 0}
