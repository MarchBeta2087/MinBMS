-- | 用「定义」枚举标准 BMS，并**交叉验证**地给出序数（康托范式）。
--
-- 运行方式（在与本文件相同的目录下）：
--
--   runghc Explore.hs 1 5 3      -- 1 行、列数 ≤ 5、数值 ≤ 3（快）
--   runghc Explore.hs 2 4 4      -- 2 行、列数 ≤ 4、数值 ≤ 4
--   runghc Explore.hs 1 5 3 3    -- 第 4 个参数是基本列深度 k（默认 4）
--   runghc Explore.hs 1 6 5 4 200000   -- 第 5 个参数是每矩阵燃料（默认 2000）
--
-- 指定 BMS 版本（默认 BM4；名字必须是 `versions` 里登记过的，例如 BM3.3）：
--   runghc Explore.hs --bm=BM3.3 1 5 3
--
-- 内部有三道闸，任一触发都直接标 unresolved（不烧燃料），从而避免卡死：
--   1. 每矩阵燃料（步数预算，逐矩阵独立）；
--   2. 矩阵列数上限（maxAnalyzedCols）；
--   3. 表示力闸门：序数引擎（Ordinal.hs）只能表示 < ε₀ 的序数，故任何在第 2 行
--      及以下含非零项的标准矩阵（序数 ≥ ε₀，如 (0,0)(1,1)）都直接放弃。
--
-- 铁律：序号一栏只写「能通过基本列交叉验证」的结果；
-- 验证不通过的矩阵一律标 unresolved，并原样打印其基本列供人工分析。
module Main (main) where

import BashicuMatrix
import Ordinal
import Version

import Control.Monad (replicateM, when)
import Data.List (foldl', intercalate, minimumBy, nubBy, partition, transpose)
import qualified Data.Map.Strict as Map
import System.Environment (getArgs)
import System.IO
  ( BufferMode (LineBuffering)
  , hPutStrLn
  , hSetBuffering
  , stderr
  , stdout
  )

-- BMatrix / Position 等类型别名统一由 BashicuMatrix 导出，此处不再重复定义。

type Key = [[Integer]]

-- | 矩阵 -> 序数 的记忆表。
type Memo = Map.Map Key (Maybe CNF)

-- | 计算上下文：两张记忆表 + 燃料（步数预算）+ 当前版本。
--
-- 燃料**逐矩阵独立**（见 main 的 step）：每分析一个新矩阵都会重置燃料，
-- 但记忆表跨矩阵保留。燃料耗尽后一律返回 Nothing（unresolved），
-- 从而保证**永不卡死**：宁可少给结果，也绝不挂住。
--
-- 一个 Ctx **绑定一个版本**：记忆表的键只有矩阵，不含版本，
-- 所以不要在同一个 Ctx 里混用两个版本（本工具一次运行只用一个版本）。
data Ctx = Ctx
  { cMatrixMemo :: Memo
  , cOrdMemo :: Map.Map [CNF] (Maybe CNF)
  , cFuel :: Int
  , cVersion :: Version
  }

freshCtx :: Version -> Int -> Ctx
freshCtx version fuel = Ctx Map.empty Map.empty fuel version

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

-- | 「基本列对齐」判定（**严格版**）。
--
-- ### 本仓库的「第 n 项」约定（统一，与行数无关）
--
--   `[n]` = 好部 + n 份坏部（第 k 份加 k·Δ，k = 0..n-1），
--   所以 `(0)(1)[n]` 与 `(0,0)(1,0)[n]` **都是 n 份**（实测确认，见 Test.hs）。
--
-- ### 为什么要「跳过起点项」，以及为什么跳过量不固定为 1
--
-- BMS 的 `[0]` 得到的是**好部**（0 份复制），它是展开的**起点**，
-- 通常**不属于该极限序数的基本列**。例：
--
--     (0)(1)   = ω     [n] 序数 = 0, 1, 2, 3, …   ← 多一个起点项 0（省略）
--     (0)(0)(1)= ω     [n] 序数 = 1, 2, 3, 4, …   ← 没有那个起点项
--     (0)(1)(2)= ω^ω   [n] 序数 = 1, ω, ω², …     ← 多一个起点项 1
--
-- 所以「跳过量」不是恒为 1，**取决于该矩阵的 `[0]` 是否给出了额外的起点项**
-- （判据：好部非空 / `[0]` 展开后仍留下内容）。
--
-- ### 为什么这不是「猜」
--
-- 这里只在 `skip ∈ {0, 1}` 中取那个**能通过严格逐项验证**的（无平移、逐项相等）。
-- 注意 `t` 是**同一个**，只是拿它去对「跳 0 项」或「跳 1 项」两种起点约定；
-- 这与早先 `any d ∈ [-3..3]` 有本质区别：
--
--   * 早先是**对同一个 skip 搜索平移量**，用平移把对不上的序列硬凑上 —— 那是掩盖 bug；
--   * 现在是**在两个有明确语义的起点约定中选一个**，且选中的那个必须
--     **逐项严格相等**（`oFS t n` 对 `known[n+skip]`）。语义清晰、可验证、无自由度。
--
-- 两种约定至多一种能通过（否则同一 `t` 会有两套不同的基本列，自相矛盾），
-- 所以这不是「宁滥勿缺」，而是「确定唯一」。
--
-- ⚠️ 上面「至多一种」要求**序列严格递增**（极限序数的基本列必然如此）。
-- 若拿一个**常值**序列（如 `[1,1,1,…]`，那是后继序数的基本列）来算，
-- 两种 skip 都会通过 —— 但这不影响本程序：`solveFS` / `solveFSLenient`
-- 只在 `strictlyIncreasing known` 成立时被调用（见 ordOf）。
aligns :: CNF -> [CNF] -> Bool
aligns t os = any (\s -> alignsFromEither s 3 t os) [0, 1]

-- | 放宽版：只要求至少 2 对匹配。**仅用于「可解析前缀」那条路**
-- （solveFSLenient）。同样在 `{0,1}` 中取通过者。
alignsLenient :: CNF -> [CNF] -> Bool
alignsLenient t os = any (\s -> alignsFromEither s 2 t os) [0, 1]

-- | `nMin` 为「至少要匹配多少对」。`skip` = 跳过的起点项个数（见上）。
alignsFromEither :: Int -> Int -> CNF -> [CNF] -> Bool
alignsFromEither skip nMin t os0 =
  let os = drop skip os0
      pairs = [ (o, oFS t (toInteger n))
              | (n, o) <- zip [0 ..] os :: [(Integer, CNF)] ]
  in length pairs >= min nMin (length os)
       && all (\(a, b) -> a == b) pairs

-- | 生成候选序数（**候选生成器**，不是判据）。
--
-- ### 它与 `aligns` 的关系：生成 vs 判定
--
-- 这里产出的只是**候选集**，最终采纳哪一个一律由 `aligns` 决定（见 solveFS）。
-- 因此本函数的「起点项」约定**不必**与 `oSupSeq` / `aligns` 逐字一致 ——
-- 它只影响候选集的**大小**，不影响最终答案（若不同约定给出的候选集都包含正确解）。
--
--     * 早先这里是 `dropUpTo maxDrop`（分别丢 0/1/2 项，宁滥勿缺），
--       结果是候选集被放大、「丢几项」成了一个自由参数；
--     * 上一版改成固定 `drop 1`，但它与 `oSupSeq` / `aligns` 的 `{0,1}` 不一致，
--       注释却写「必须一致」，容易误导后来者（实测二者**输出完全相同**：
--       因为候选集不同但都含正确解，且被判据 `aligns` 过滤后收敛到同一答案）；
--     * 现在统一为 `{0,1}`，与 `oSupSeq` / `aligns` 用**同一个起点项约定**，
--       消除这处「看起来必须同步、实则不必」的隐患。
candidates :: Int -> [CNF] -> Ctx -> (Ctx, [CNF])
candidates depth os ctx0 = go [ drop k os | k <- [0, 1] ] ctx0 []
  where
    go [] ctx acc = (ctx, nubBy (==) (reverse acc))
    go (os' : rest) ctx acc
      | null os' = go rest ctx acc
      | otherwise =
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

-- | 由基本列序列反推序数：在所有候选里取「能对齐的最小序数」。
--
-- 找不到、或燃料耗尽 → Nothing（绝不猜）。depth 为递归深度上限。
solveFS :: Int -> [CNF] -> Ctx -> (Ctx, Maybe CNF)
solveFS depth os ctx
  | depth <= 0 = (ctx, Nothing)
  | null os = (ctx, Nothing)
  | Just cached <- Map.lookup os (cOrdMemo ctx) = (ctx, cached)
  | otherwise =
      -- 先试 oSupSeq 的结构化结论（几乎零成本）。命中就**完全跳过**后面指数级的
      -- candidates 搜索 —— 后者会烧掉大量燃料，正是深层用例 FUEL-OUT 的主因。
      -- 注意：这里同样必须通过 aligns 交叉验证，绝不直接采信。
      let supCands = [ t | t <- maybe [] (: []) (oSupSeq os), aligns t os ]
      in case supCands of
           (t : _) -> (rememberOrd os (Just t) ctx, Just t)
           [] ->
             let (ctx1, ok) = burn ctx
             in if not ok
                  then (ctx, Nothing)
                  else
                    let (ctx2, cands) = candidates depth os ctx1
                    in case [ t | t <- cands, aligns t os ] of
                         [] -> (rememberOrd os Nothing ctx2, Nothing)
                         hits ->
                           let t = minimumBy (\a b -> oCmp a b) hits
                           in (rememberOrd os (Just t) ctx2, Just t)

-- | 「可解析前缀」版：当完整基本列里有项定不出来时（见 ordOf 里的说明），
-- 退而用**已知前缀** + oSupSeq 反推极限。
--
-- 取舍（与维护者确认过）：验证只覆盖**已知项**（alignsLenient，≥2 对），
-- 因此这条路比严格路径弱。为压低误判风险，这里只采信 oSupSeq 的结构化结论，
-- 不再叠加松散的 candidates。结果照常写入记忆表，供上层使用。
solveFSLenient :: [CNF] -> Ctx -> (Ctx, Maybe CNF)
solveFSLenient os ctx
  | null os = (ctx, Nothing)
  | Just cached <- Map.lookup os (cOrdMemo ctx) = (ctx, cached)
  | otherwise =
      let (ctx1, ok) = burn ctx
      in if not ok
           then (ctx, Nothing)
           else case [ t | t <- maybe [] (: []) (oSupSeq os), alignsLenient t os ] of
                  [] -> (rememberOrd os Nothing ctx1, Nothing)
                  hits ->
                    let t = minimumBy (\a b -> oCmp a b) hits
                    in (rememberOrd os (Just t) ctx1, Just t)

rememberOrd :: [CNF] -> Maybe CNF -> Ctx -> Ctx
rememberOrd os v ctx = ctx { cOrdMemo = Map.insert os v (cOrdMemo ctx) }

------------------------------------------------------------------------
-- 表示力闸门：康托范式（Ordinal.hs）只能表示 < ε₀ 的序数
------------------------------------------------------------------------

-- | 该矩阵的序数能否用康托范式表示（即其序数是否 < ε₀）。
--
-- 一个标准矩阵的序数 < ε₀，当且仅当它在第 2 行及以下全是 0：
-- 此时它等价于只保留第 1 行的「1 行 BMS」，而 1 行 BMS 的极限正是 ε₀。
-- 反过来，只要任一列在第 2 行及以下出现非零项，序数就 ≥ ε₀
-- （最小的例子是 (0,0)(1,1) = ε₀），康托范式表示不出来。
--
-- 有了它，这类矩阵可以**不烧燃料**地直接判 unresolved，
-- 而不是让 solveFS 白搜满 2000 步。Phase 3 升级到 Veblen 范式后，
-- 这个闸门会放宽为「超出新表示法」。
representableInCNF :: [[Integer]] -> Bool
representableInCNF = all (\c -> all (== 0) (drop 1 c))

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
  | not (representableInCNF cols) =
      -- 序数 ≥ ε₀：超出康托范式的表示范围，直接放弃（不烧燃料，见上方说明）。
      (rememberMat cols Nothing ctx, Nothing)
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
              fsList = [ fmap matrixColumns (expandWith (cVersion ctx) m n)
                       | n <- [0 .. toInteger k] ]
          in case sequence fsList of
               Nothing -> (c, Nothing)
               Just fss ->
                 -- 逐项定序，遇到第一个「定不出来」的项立即停止：既不浪费燃料去展开
                 -- 更后面（列数会爆炸）的项，又正好得到「可解析前缀」。
                 let (c1, known, allOk) = collectKnown fss c
                 in if allOk && strictlyIncreasing known
                      -- 完整基本列都能定序且严格递增：走严格验证（铁律不变）。
                      then solveFS 5 known c1
                      else if length known >= 3 && strictlyIncreasing known
                             then solveFSLenient known c1
                             else (c1, Nothing)

    -- 逐项定序，遇到第一个 Nothing 就停。返回 (新 ctx, 已知项, 是否全项都成功)。
    collectKnown :: [Key] -> Ctx -> (Ctx, [CNF], Bool)
    collectKnown [] cx = (cx, [], True)
    collectKnown (x : xs) cx =
      let (cx1, y) = ordOf k (depth - 1) x cx
      in case y of
           Nothing -> (cx1, [], False)
           Just o ->
             let (cx2, rest, ok) = collectKnown xs cx1
             in (cx2, o : rest, ok)

rememberMat :: Key -> Maybe CNF -> Ctx -> Ctx
rememberMat cols v ctx = ctx { cMatrixMemo = Map.insert cols v (cMatrixMemo ctx) }

strictlyIncreasing :: [CNF] -> Bool
strictlyIncreasing os = and (zipWith (\a b -> oCmp a b == LT) os (drop 1 os))

------------------------------------------------------------------------
-- 主程序
------------------------------------------------------------------------

main :: IO ()
main = do
  hSetBuffering stdout LineBuffering
  hSetBuffering stderr LineBuffering
  args <- getArgs
  -- 形如 --bm=BM3.3 的开关可以放在任意位置；其余的是位置参数。
  let (flags, positional) = partition isFlag args
      isFlag a = take 2 a == "--"
      versionArg = case [ drop 5 f | f <- flags, take 5 f == "--bm=" ] of
                     (v : _) -> v
                     []      -> versionName bm4
  version <- case lookupVersion versionArg of
    Just v  -> pure v
    Nothing -> do
      hPutStrLn stderr ("未知版本：" ++ versionArg)
      hPutStrLn stderr ("可用版本：" ++ intercalate ", " (map versionName versions))
      ioError (userError "unknown BMS version")
  let (rows, maxCols, maxVal, k, fuel) = case positional of
        [a, b, c]       -> (read a, read b, read c, 4, fuelBudget)
        [a, b, c, d]    -> (read a, read b, read c, read d, fuelBudget)
        [a, b, c, d, e] -> (read a, read b, read c, read d, read e)
        _               -> (1, 5, 3, 4, fuelBudget)
  putStrLn ("序数分析：版本 = " ++ versionName version
            ++ "，行数 = " ++ show rows
            ++ "，列数 ≤ " ++ show maxCols
            ++ "，数值 ≤ " ++ show maxVal
            ++ "，基本列深度 n = 0.." ++ show k
            ++ "，燃料 = " ++ show fuel)
  putStrLn "unresolved = 本工具无法用基本列交叉验证的结果；绝不猜测。"
  let ms = enumerate rows maxCols maxVal
  putStrLn ("枚举到 " ++ show (length ms) ++ " 个标准矩阵：")
  let step (ctx, acc) cols =
        -- 每个矩阵独立预算：重置燃料，但保留跨矩阵的记忆表。
        -- 这样「前面的矩阵把燃料吃光、后面的矩阵凭空 unresolved」就不会发生。
        let ctx0 = ctx { cFuel = fuel }
            (ctx', r) = ordOf k 20 cols ctx0
        in (ctx', (cols, r) : acc)
      (_, revResults) = foldl' step (freshCtx version fuel, []) ms
      results = reverse revResults
      total = length results
  -- 进度打到 stderr，不污染 stdout 的结果格式；每 10 个（以及最后一个）报一次，
  -- 这样即使某个矩阵稍慢，也能看出程序在往前走。
  mapM_ (\(i, r) -> do
            when (i `mod` 10 == 0 || i == total) $
              hPutStrLn stderr ("  [进度] 已分析 " ++ show i ++ "/" ++ show total)
            report version k r)
        (zip [1 ..] results)
  let ok = length [ () | (_, Just _) <- results ]
  putStrLn ("---- 已定序 " ++ show ok ++ " 个；unresolved "
            ++ show (length results - ok) ++ " 个 ----")
  putStrLn ("每个矩阵的燃料预算：" ++ show fuel
            ++ "（该矩阵内燃料/深度耗尽即标 unresolved —— 这是为了永不卡死）")
  putStrLn "提示：把 unresolved 的矩阵发到 issue / PR，任何人都可以帮忙补。"
  putStrLn "（期望值必须能由本仓库的定义 + 基本列交叉验证得到；不得搬运外部资料的「表达」，）"
  putStrLn "（数学事实可用，但请标注出处。详见 CONTRIBUTING.md 铁律二。）"

-- | **每个矩阵**的步数预算（逐矩阵独立，不是全局总量）。
-- 调大可提高覆盖率，但会更慢；调小则更快、更多 unresolved。
-- 注意：每一步可能包含一次 expandBMS + 若干次 oFS，所以这个数不要太大，
-- 否则单个矩阵就可能跑很久。经验值（2000 步/矩阵）：
--   `Explore.hs 1 5 3` 可定序 44 项（unresolved 19 项）；
--   `Explore.hs 2 4 4` 可定序 20 项（unresolved 82 项）—— 其余大多是 ≥ ε₀，
--   已被表示力闸门直接挡下，因此不会再烧燃料。
fuelBudget :: Int
fuelBudget = 2000

-- | 单个矩阵参与分析的**最大列数**。超过就直接放弃（标 unresolved）。
--
-- 为什么必须有它：深层展开会让列数爆炸（把坏部复制 n 份，而坏部本身
-- 在下一层又变长）。没有这道闸，单步代价会无限增长，
-- 「有燃料上限也照样卡死」。取值要足够大到能覆盖 ω^ω 那一档。
maxAnalyzedCols :: Int
maxAnalyzedCols = 200

report :: Version -> Int -> ([[Integer]], Maybe CNF) -> IO ()
report _ _ (cols, Just t) =
  putStrLn ("  " ++ pad (prettyCols cols) ++ "= " ++ oShow t)
report version k (cols, Nothing)
  | length cols > maxAnalyzedCols = do
      putStrLn ("  " ++ pad (prettyColsCapped maxShownCols cols) ++ "= unresolved")
      putStrLn ("      （矩阵列数 " ++ show (length cols) ++ " > "
                ++ show maxAnalyzedCols ++ "，已略去基本列以免展示爆炸）")
  | otherwise = do
      let m = fromCols cols
          fsList = [ fmap matrixColumns (expandWith version m n) | n <- [0 .. toInteger k] ]
          shown = case sequence fsList of
                    Just fss -> intercalate " , " (map (prettyColsCapped maxShownCols) fss)
                    Nothing  -> "<展开失败>"
      putStrLn ("  " ++ pad (prettyCols cols) ++ "= unresolved")
      putStrLn ("      n=0.." ++ show k ++ ": " ++ shown)

-- | 基本列**展示**时的列数上限（只影响打印，不影响分析）。
-- 深层展开会让列数爆炸（坏部被复制 n 份，坏部自身在下一层又更长），
-- 所以打印前先截断，避免「展示」本身把时间 / 内存吃光。
maxShownCols :: Int
maxShownCols = 64

-- | 超过上限就截断，并标出省略了多少列。
prettyColsCapped :: Int -> [[Integer]] -> String
prettyColsCapped limit cs
  | length cs > limit =
      prettyCols (take limit cs) ++ "…(+" ++ show (length cs - limit) ++ " 列)"
  | otherwise = prettyCols cs

pad :: String -> String
pad s = s ++ replicate (max 1 (30 - length s)) ' '
