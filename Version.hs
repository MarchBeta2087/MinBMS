-- | BMS 的版本注册表。
--
-- 各版本的差别**只有一处**：坏部复制时，哪些位置的项要加上阶差向量。
-- 好部 / 坏部 / 坏根 / 阶差向量的定义在所有版本中完全相同，
-- 因此一个版本就是一条 `Ascension` 规则（见 BashicuMatrix.hs）。
--
-- 想加新版本？见 VERSIONS.md 的「如何添加一个新版本」。
module Version
  ( Version(..)
  , bm4
  , bm33
  , ascendBM33
  , versions
  , lookupVersion
  , expandWith
  ) where

import BashicuMatrix

import Data.List (foldl')
import qualified Data.Map.Strict as Map

-- | 一个 BMS 版本 = 名字 + 「哪些项加阶差」的判定规则。
data Version = Version
  { versionName   :: String
  , versionAscend :: Ascension
  }

instance Show Version where
  show = versionName

------------------------------------------------------------------------
-- BM4（现行版本，Bashicu 官方，2018-09）
------------------------------------------------------------------------

-- | BM4：坏部中的项加阶差，当且仅当它在**同行的祖先链**包含坏根列上的对应项。
-- 规则直接取自 BashicuMatrix.hs 的 `ascendBM4`。
bm4 :: Version
bm4 = Version "BM4" ascendBM4

------------------------------------------------------------------------
-- BM3.3（Ecl1psed & Rpakr，2019-03；试图模仿「理想无提升 BMS」）
------------------------------------------------------------------------

-- | BM3.3：在 BM4 的判定之外，再多两类项也不加阶差。
--
-- 设 A 是坏部中位于第 y 行的一项：
--
--   * 规则 2：若 A **正下方**的项已被判为不加阶差，且 A 的父项位于坏根列，
--     且 A 的值不小于同一行末项的值，则 A 也不加阶差；
--   * 规则 3：若某项 B 的祖先项（含自身，见下）中存在满足规则 2 的项，
--     则 B 也不加阶差。
--
-- 因为规则 2 要用到「正下方那一项」的最终判定，所以必须**自下而上**逐行计算。
bm33 :: Version
bm33 = Version "BM3.3" ascendBM33

ascendBM33 :: Ascension
ascendBM33 matrix rootColumn =
  \pos -> not (Map.findWithDefault False pos (noDeltaBM33 matrix rootColumn))

-- | 计算 BM3.3 中「不加阶差」的项集合：(列, 行) -> 是否不加阶差。
--
-- 只覆盖坏部（坏根列 .. 倒数第二列）与所有行；坏部之外的项不会被查询。
noDeltaBM33 :: BMatrix -> Int -> Map.Map Position Bool
noDeltaBM33 matrix rootColumn = foldl' stepRow Map.empty [height - 1, height - 2 .. 0]
  where
    columns = matrixColumns matrix
    nCols = length columns
    height = maximum (0 : map length columns)
    lastColIndex = nCols - 1
    badCols = [rootColumn .. nCols - 2]

    valOrZero pos = maybe 0 id (valueAt matrix pos)

    -- BM4 的基准判定：同行的祖先链不含坏根列 → 不加阶差
    base pos@(_, y) = not (isAncestorOf matrix (rootColumn, y) pos)

    -- A 的父项是否位于坏根列
    parentInRoot pos =
      case fatherOf matrix pos of
        Just (parentCol, _) -> parentCol == rootColumn
        Nothing             -> False

    -- 规则 2（done 里已算完的行 = 当前行下方的所有行）
    rule2 done pos@(_, y) =
      Map.findWithDefault False (fst pos, y + 1) done
        && parentInRoot pos
        && valOrZero pos >= valOrZero (lastColIndex, y)

    -- 同一行内沿父项链向上，含自身（与本项目 isAncestorOf 的「自身也算祖先」一致）
    ancestorsOf pos@(_, y) =
      pos : case fatherOf matrix pos of
              Just above@(_, ay) | ay == y -> ancestorsOf above
              _                            -> []

    -- 规则 2 + 规则 3：自身或任一祖先满足规则 2 → 不加阶差
    stepRow done y =
      let r2 = Map.fromList [ (p, rule2 done p) | c <- badCols, let p = (c, y) ]
          noDelta p =
            base p || any (\a -> Map.findWithDefault False a r2) (ancestorsOf p)
          row = Map.fromList [ (p, noDelta p) | c <- badCols, let p = (c, y) ]
      in Map.union done row

------------------------------------------------------------------------
-- 注册表
------------------------------------------------------------------------

-- | 本仓库支持的所有版本。加新版本时把它加进这个列表即可。
versions :: [Version]
versions = [bm4, bm33]

-- | 按名字查版本（大小写敏感；匹配不到返回 Nothing）。
lookupVersion :: String -> Maybe Version
lookupVersion name =
  case [ v | v <- versions, versionName v == name ] of
    (v : _) -> Just v
    []      -> Nothing

-- | 按指定版本展开矩阵。
expandWith :: Version -> BMatrix -> Integer -> Maybe BMatrix
expandWith v = expandBMSWith (versionAscend v)
