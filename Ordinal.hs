-- | 下 ε₀ 的康托范式（Cantor normal form, CNF）序数引擎。
--
-- 本模块只依赖 base（零第三方依赖），供 Explore.hs 与 Test.hs 使用。
--
-- 表示法：CNF ts 表示 ω^{e1}·c1 + ω^{e2}·c2 + ... + ω^{ek}·ck，
-- 其中 ts = [(e1,c1),...,(ek,ck)]。不变式为
--
--   * 指数严格递减：e1 > e2 > ... > ek ≥ 0
--   * 系数 ci ≥ 1
--   * 指数 0（即 ω^0 = 1）只允许出现在最后一项
--
-- CNF [] 表示序数 0。
--
-- 注意：本模块把「序数」当纯值处理，与 BMS 矩阵无关；
-- 「矩阵 -> 序数」的翻译由 Explore.hs 负责，且必须经过基本列交叉验证。
module Ordinal
  ( CNF(..)
  , oZero, oOne, oSucc, oPred, oAdd, oOmegaPow
  , oIsZero, oIsLimit, oCmp, oFS, oShow, oSize
  , oSupSeq, oSupSeqFrom
  ) where

import Data.List (intercalate)

data CNF = CNF [(CNF, Integer)]
  deriving (Eq, Ord)

oZero :: CNF
oZero = CNF []

oOne :: CNF
oOne = CNF [(oZero, 1)]

oIsZero :: CNF -> Bool
oIsZero (CNF ts) = null ts

-- | 粗略「复杂度」，用于试探候选序数时排序（越小越简单）。
oSize :: CNF -> Int
oSize (CNF []) = 0
oSize (CNF ts) = length ts + sum [oSize e | (e, _) <- ts]

-- | 比较两个序数（康托范式逐项：先比指数，再比系数）。
oCmp :: CNF -> CNF -> Ordering
oCmp (CNF []) (CNF []) = EQ
oCmp (CNF []) _ = LT
oCmp _ (CNF []) = GT
oCmp (CNF ((e1, c1) : r1)) (CNF ((e2, c2) : r2)) =
  case oCmp e1 e2 of
    EQ -> case compare c1 c2 of
            EQ -> oCmp (CNF r1) (CNF r2)
            o  -> o
    o -> o

-- | 后继：加 1。
oSucc :: CNF -> CNF
oSucc (CNF []) = oOne
oSucc (CNF ts) =
  case last ts of
    (e, c)
      | oIsZero e -> CNF (init ts ++ [(e, c + 1)])
      | otherwise -> CNF (ts ++ [(oZero, 1)])

-- | 前驱。仅对后继序数有意义；对 0 与极限序数返回 0 作为兜底。
oPred :: CNF -> CNF
oPred (CNF []) = oZero
oPred (CNF ts) =
  case last ts of
    (e, c)
      | oIsZero e && c > 1 -> CNF (init ts ++ [(e, c - 1)])
      | oIsZero e          -> CNF (init ts)
      | otherwise          -> oZero

-- | ω^e
oOmegaPow :: CNF -> CNF
oOmegaPow e = CNF [(e, 1)]

-- | 康托范式加法 a + b（自动吸收 / 合并）。
oAdd :: CNF -> CNF -> CNF
oAdd a (CNF []) = a
oAdd (CNF []) b = b
oAdd (CNF as) (CNF bs) =
  let (e1, c1) = head bs
      bs' = tail bs
      kept = takeWhile (\(e, _) -> oCmp e e1 /= LT) as
  in case reverse kept of
       [] -> CNF bs
       (ek, ck) : keptInitRev
         | oCmp ek e1 == EQ -> CNF (reverse keptInitRev ++ [(ek, ck + c1)] ++ bs')
         | otherwise        -> CNF (kept ++ bs)

-- | 是否为极限序数。
oIsLimit :: CNF -> Bool
oIsLimit (CNF []) = False
oIsLimit (CNF ts) = not (oIsZero (fst (last ts)))

-- | 基本列第 n 项。约定：后继序数的基本列取常值（其前驱）。
oFS :: CNF -> Integer -> CNF
oFS a n
  | not (oIsLimit a) = oPred a
  | otherwise = oFSLimit a n

-- | 极限序数的基本列（下 ε₀ 的标准规则）。
oFSLimit :: CNF -> Integer -> CNF
oFSLimit (CNF ts) n =
  let prefix = CNF (init ts)
      (e, c) = last ts
  in if c >= 2
       then oAdd (CNF (init ts ++ [(e, c - 1)])) (oFS (oOmegaPow e) n)
       else if oIsLimit e
              then oAdd prefix (oOmegaPow (oFS e n))
              else oAdd prefix (CNF [(oPred e, n + 1)])

-- | 由一段严格递增的基本列前几项，反推它所属的极限序数（康托范式层）。
--
-- 只识别常见形态；识别不出就返回 Nothing。**调用方仍必须用基本列交叉验证**，
-- 所以这里「宁缺毋滥」，绝不硬猜。
--
-- 用到的性质：若所有项都共享加法前缀 q，则 sup(q + rᵢ) = q + sup(rᵢ)，
-- 因此剥掉公共前缀 q 后只需看尾部 rᵢ：
--
--   * 尾部都是同一个指数 e 的单体 ω^e·cᵢ（系数递增）→ 极限是 q + ω^(e+1)；
--   * 尾部都是单体 ω^{eᵢ}（指数严格递增）→ 极限是 q + ω^(sup eᵢ)（递归）。
--
-- ### 关于开头的「起点项」
--
-- BMS 的 `[0]` 得到的是**好部**（0 份复制），是展开的**起点**，通常不属于
-- 该极限序数的基本列。但**并非所有矩阵都会产生这个起点项**：
--
--     (0)(1)    = ω    [n] 序数 = 0, 1, 2, 3, …   ← 有起点项（那个 0）
--     (0)(0)(1) = ω    [n] 序数 = 1, 2, 3, 4, …   ← 没有起点项
--
-- 所以本函数在 `{0, 1}` 两个跳过量下**都试一遍**，返回第一个可识别的结果。
-- 调用方（Explore.hs）仍必须用**严格逐项**的基本列验证（无平移）来确认，
-- 所以这里放宽跳过量**不会**引入「猜」：最终采纳与否由严格验证决定。
--
-- （早先这里是「试 0/1/2 项」，既有 2 这个多余的候选，又缺少明确语义；
-- 现在收窄到 {0,1}，对应「有无起点项」这两种情形。）
oSupSeq :: [CNF] -> Maybe CNF
oSupSeq os = firstJust [ classify (drop k os) | k <- [0, 1] ]

-- | 显式指定跳过量（`oSupSeqFrom 0` == 不跳过）。默认请用 `oSupSeq`。
oSupSeqFrom :: Int -> [CNF] -> Maybe CNF
oSupSeqFrom skip os = classify (drop skip os)

firstJust :: [Maybe a] -> Maybe a
firstJust xs =
  case [ y | Just y <- xs ] of
    [] -> Nothing
    y : _ -> Just y

classify :: [CNF] -> Maybe CNF
classify os
  | length os < 2 = Nothing
  | otherwise =
      let q = commonPrefix os
          ts = map (stripAddPrefix q) os
      in case traverse singleTerm ts of
           Nothing -> Nothing
           Just terms ->
             let es = map fst terms
                 cs = map snd terms
             in if allSame es && strictlyIncrInts cs
                  then Just (oAdd q (oOmegaPow (oSucc (head es))))
                  else if strictlyIncr es
                         then fmap (\e -> oAdd q (oOmegaPow e)) (oSupSeq es)
                         else Nothing

-- | 单个加法项 ω^e·c 的 (e, c)；(CNF []) 与多项之和都返回 Nothing。
singleTerm :: CNF -> Maybe (CNF, Integer)
singleTerm (CNF [t]) = Just t
singleTerm _ = Nothing

-- | 所有项共有的最长加法前缀（要求项完全相等：指数与系数都相同）。
commonPrefix :: [CNF] -> CNF
commonPrefix os = CNF (foldr1 lcp (map termsOf os))
  where
    lcp xs ys = map fst (takeWhile (uncurry (==)) (zip xs ys))

-- | 从康托范式里剥掉一个加法前缀 q。
stripAddPrefix :: CNF -> CNF -> CNF
stripAddPrefix (CNF q) (CNF ts) = CNF (drop (length q) ts)

termsOf :: CNF -> [(CNF, Integer)]
termsOf (CNF ts) = ts

allSame :: Eq a => [a] -> Bool
allSame [] = True
allSame (x : xs) = all (== x) xs

strictlyIncr :: [CNF] -> Bool
strictlyIncr xs = and (zipWith (\a b -> oCmp a b == LT) xs (drop 1 xs))

strictlyIncrInts :: [Integer] -> Bool
strictlyIncrInts xs = and (zipWith (<) xs (drop 1 xs))

-- | 显示，例如 "ω^(ω) + ω·3 + 2"。
oShow :: CNF -> String
oShow (CNF []) = "0"
oShow (CNF ts) = intercalate " + " (map term ts)
  where
    term (e, c)
      | oIsZero e = show c
      | otherwise = pow e ++ if c == 1 then "" else "·" ++ show c
    pow e
      | oCmp e oOne == EQ = "ω"
      | otherwise = "ω^(" ++ oShow e ++ ")"
