{-# LANGUAGE FlexibleInstances #-}
{-# LANGUAGE GADTs #-}

module BashicuMatrix where

import Data.List (intercalate, transpose)

data GColumn xs where
    C :: [Integer] -> GColumn [Integer]

data GBashicuMatrix bms where
    BMS :: [GColumn [Integer]] -> GBashicuMatrix [GColumn [Integer]]

data GBashicuOrdinal bms where
    BO :: GBashicuMatrix [GColumn [Integer]] -> Integer -> GBashicuOrdinal [GColumn [Integer]]

instance Show (GBashicuOrdinal [GColumn [Integer]]) where
  show (BO matrix copies) = "BO {matrix = " ++ show matrix ++ ", copies = " ++ show copies ++ "}"

instance Show (GColumn [Integer]) where
  show (C values) = show values

instance Show (GBashicuMatrix [GColumn [Integer]]) where
  show (BMS columns) = "BMS " ++ show columns

renderBMS :: GBashicuMatrix bms -> String
renderBMS matrix =
  intercalate "\n" (map (unwords . map show) (transpose (matrixColumns matrix)))

-- 初始化 Bashicu 矩阵
-- [[a00,a01,a02,...,a0n],[a10,a11,a12,...,a1n],[a20,a21,a22,...,a2n],...,[am0,am1,am2,...,amn]] -> `GBashicuMatrix [GColumn [a00,a10,a20,...,am0],GColumn [a01,a11,a21,...,am1],GColumn [a02,a12,a22,...,am2],GColumn [a0n,a1n,a2n,...,amn]]`
initBMS :: [[Integer]] -> GBashicuMatrix [GColumn [Integer]]
initBMS mat = BMS (map C (transpose mat))

-- 安全访问（返回 Maybe）
safeIndex :: [a] -> Int -> Maybe a
safeIndex xs i 
  | i < 0     = Nothing
  | otherwise = foldr (\x acc k -> if k == 0 then Just x else acc (k-1)) (const Nothing) xs i

-- 获取列
getColumn :: GBashicuMatrix bms -> Int -> Maybe (GColumn [Integer])
getColumn (BMS m) columnIndex
  | columnIndex < 0 = Nothing
  | otherwise = safeIndex m columnIndex

-- 概念 1：第一行元素的父项为从该元素起，在该元素左边且小于该元素的第一个项
type Position = (Int, Int)

matrixColumns :: GBashicuMatrix bms -> [[Integer]]
matrixColumns (BMS columns) = map columnValues columns
  where
    columnValues :: GColumn [Integer] -> [Integer]
    columnValues (C values) = values

valueAt :: GBashicuMatrix bms -> Position -> Maybe Integer
valueAt matrix (columnIndex, rowIndex) = do
  column <- safeIndex (matrixColumns matrix) columnIndex
  safeIndex column rowIndex

fatherOfFirstRow :: GBashicuMatrix bms -> Int -> Maybe Position
fatherOfFirstRow matrix columnIndex = do
  currentValue <- valueAt matrix (columnIndex, 0)
  previousColumn <- findPreviousColumn columnIndex currentValue
  pure (previousColumn, 0)
  where
    findPreviousColumn candidate currentValue
      | candidate <= 0 = Nothing
      | otherwise =
          case valueAt matrix (candidate - 1, 0) of
            Just value
              | value < currentValue -> Just (candidate - 1)
            _ -> findPreviousColumn (candidate - 1) currentValue

-- 概念 2：元素的祖先项为元素的父项、父项的父项等元素

isAncestorOf :: GBashicuMatrix bms -> Position -> Position -> Bool
isAncestorOf matrix candidate target =
  candidate == target || maybe False (isAncestorOf matrix candidate) (fatherOf matrix target)

-- 概念 3：其余行元素的父项为从该元素起，在该元素左边，小于该元素，且其正上方的项是该元素正上方的项的祖先项的第一个项

fatherOf :: GBashicuMatrix bms -> Position -> Maybe Position
fatherOf matrix position@(_, 0) = fatherOfFirstRow matrix (fst position)
fatherOf matrix (columnIndex, rowIndex) = do
  currentValue <- valueAt matrix (columnIndex, rowIndex)
  abovePosition <- pure (columnIndex, rowIndex - 1)
  findPreviousColumn columnIndex currentValue abovePosition
  where
    findPreviousColumn candidate currentValue abovePosition
      | candidate <= 0 = Nothing
      | otherwise =
          let candidatePosition = (candidate - 1, rowIndex)
              candidateAbove = (candidate - 1, rowIndex - 1)
          in case (valueAt matrix candidatePosition, isAncestorOf matrix candidateAbove abovePosition) of
               (Just value, True)
                 | value < currentValue -> Just candidatePosition
               _ -> findPreviousColumn (candidate - 1) currentValue abovePosition

-- 概念 4：坏根为最后一列中从下往上数的第一个非零项的父项所在的列

badRoot :: GBashicuMatrix bms -> Maybe Int
badRoot matrix = fmap fst (badRootPosition matrix)

badRootPosition :: GBashicuMatrix bms -> Maybe Position
badRootPosition matrix = do
  lastColumnIndex <- lastIndex (matrixColumns matrix)
  lastColumn <- valueAtColumn matrix lastColumnIndex
  rowIndex <- lastNonZeroIndex lastColumn
  fatherOf matrix (lastColumnIndex, rowIndex)
  where
    lastIndex [] = Nothing
    lastIndex columns = Just (length columns - 1)

    valueAtColumn :: GBashicuMatrix bms -> Int -> Maybe [Integer]
    valueAtColumn (BMS columns) index =
      case safeIndex columns index of
        Just (C values) -> Just values
        Nothing -> Nothing

    lastNonZeroIndex values =
      case [index | (index, value) <- zip [0 ..] values, value /= 0] of
        [] -> Nothing
        indices -> Just (last indices)

-- 概念 5：坏部为坏根和末列之间的部分，包含坏根，但是不包含末列
badPart :: GBashicuMatrix bms -> Maybe (GBashicuMatrix [GColumn [Integer]])
badPart matrix = do
  rootColumn <- badRoot matrix
  let columns = matrixColumns matrix
  pure (BMS (map C (take (length columns - rootColumn - 1) (drop rootColumn columns))))

-- 概念 6：好部为坏根之前的部分，不包含坏根
goodPart :: GBashicuMatrix bms -> Maybe (GBashicuMatrix [GColumn [Integer]])
goodPart matrix = do
  rootColumn <- badRoot matrix
  pure (BMS (map C (take rootColumn (matrixColumns matrix))))

-- 概念 7：阶差向量为末列和坏根的差值，但是其最后一项始终为零。特别地，如果末列中的第 i+1 行元素为零，则阶差向量的第 i 行元素也为零
differenceVector :: GBashicuMatrix bms -> Maybe [Integer]
differenceVector matrix = do
  rootColumn <- badRoot matrix
  columns <- pure (matrixColumns matrix)
  lastColumn <- safeIndex columns (length columns - 1)
  rootValues <- safeIndex columns rootColumn
  pure (buildDifference lastColumn rootValues)
  where
    buildDifference lastValues rootValues =
      [ if rowIndex == length lastValues - 1 || nextValue == 0
          then 0
          else currentValue - valueAtOrZero rootValues rowIndex
      | rowIndex <- [0 .. length lastValues - 1]
      , let currentValue = valueAtOrZero lastValues rowIndex
      , let nextValue = valueAtOrZero lastValues (rowIndex + 1)
      ]

    valueAtOrZero values index =
      case safeIndex values index of
        Just value -> value
        Nothing -> 0

-- 条件 1：第一列上的数字必须全部为 0，或者是空矩阵
isAllZeroInThisColumn :: [Integer] -> Bool
isAllZeroInThisColumn = all (== 0)

isAllZeroInFirstColumn :: GBashicuMatrix bms -> Bool
isAllZeroInFirstColumn (BMS []) = True
isAllZeroInFirstColumn m = maybe False (\(C xs) -> isAllZeroInThisColumn xs) (getColumn m 0)

-- 条件 2：同列中下面的项不能大于上面的项
isThisColumnMonoDescNonStrictly :: [Integer] -> Bool
isThisColumnMonoDescNonStrictly xs = and (zipWith (>=) xs (drop 1 xs))

isAllColumnsMonoDescNonStrictly :: GBashicuMatrix bms -> Bool
isAllColumnsMonoDescNonStrictly (BMS columns) =
  all (\(C xs) -> isThisColumnMonoDescNonStrictly xs) columns

-- 条件 3：每一个非零项至多为其父项 +1
isAllNonZeroNotBiggerThanFatherPlusOne :: GBashicuMatrix bms -> Bool
isAllNonZeroNotBiggerThanFatherPlusOne matrix =
  all validElement (allPositions matrix)
  where
    validElement position =
      case valueAt matrix position of
        Nothing -> True
        Just 0 -> True
        Just value ->
          case fatherOf matrix position >>= valueAt matrix of
            Just fatherValue -> value <= fatherValue + 1
            Nothing -> False

allPositions :: GBashicuMatrix bms -> [Position]
allPositions matrix =
  [ (columnIndex, rowIndex)
  | (columnIndex, column) <- zip [0 ..] (matrixColumns matrix)
  , rowIndex <- [0 .. length column - 1]
  ]

isBasicBMS :: GBashicuMatrix m -> Bool
isBasicBMS matrix =
  isAllZeroInFirstColumn matrix
    && isAllColumnsMonoDescNonStrictly matrix
      && isAllNonZeroNotBiggerThanFatherPlusOne matrix

hasNonZeroLastColumn :: GBashicuMatrix bms -> Bool
hasNonZeroLastColumn matrix =
  case reverse (matrixColumns matrix) of
    [] -> False
    lastColumn : _ -> any (/= 0) lastColumn

mkOrdinal :: GBashicuMatrix [GColumn [Integer]] -> Integer -> Maybe (GBashicuOrdinal [GColumn [Integer]])
mkOrdinal matrix copies
  | copies < 0 = Nothing
  | not (isBasicBMS matrix) = Nothing
  | not (hasNonZeroLastColumn matrix) = Nothing
  | otherwise = Just (BO matrix copies)

ordinalCopies :: GBashicuOrdinal bms -> Integer
ordinalCopies (BO _ copies) = copies

ordinalMatrix :: GBashicuOrdinal bms -> GBashicuMatrix [GColumn [Integer]]
ordinalMatrix (BO matrix _) = matrix

expandedBMS :: GBashicuOrdinal bms -> Maybe (GBashicuMatrix [GColumn [Integer]])
expandedBMS (BO matrix copies) = expandBMS matrix copies

ordinalSequence :: GBashicuMatrix [GColumn [Integer]] -> Maybe [GBashicuOrdinal [GColumn [Integer]]]
ordinalSequence matrix
  | not (isBasicBMS matrix) || not (hasNonZeroLastColumn matrix) = Nothing
  | otherwise = Just (map (BO matrix) [0 ..])

expandBMS :: GBashicuMatrix bms -> Integer -> Maybe (GBashicuMatrix [GColumn [Integer]])
expandBMS matrix copies
  | copies < 0 = Nothing
  | otherwise = do
      rootPosition <- badRootPosition matrix
      difference <- differenceVector matrix
      rootColumn <- pure (fst rootPosition)
      let columns = matrixColumns matrix
          goodColumns = take rootColumn columns
          badColumns = take (length columns - rootColumn - 1) (drop rootColumn columns)
          expandedBad = concatMap (shiftedCopies rootPosition difference copies) (zip [rootColumn ..] badColumns)
      pure (BMS (map C (goodColumns ++ expandedBad)))
  where
    shiftedCopies rootPosition difference count (columnIndex, values) =
      [ [if shouldShift rootPosition (columnIndex, rowIndex)
           then value + count * valueAtOrZero difference rowIndex
           else value
        | (rowIndex, value) <- zip [0 ..] values
        ]
      | _ <- [1 .. count]
      ]

    shouldShift rootPosition position = isAncestorOf matrix rootPosition position

    valueAtOrZero values index =
      case safeIndex values index of
        Just value -> value
        Nothing -> 0