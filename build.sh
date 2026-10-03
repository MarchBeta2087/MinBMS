#!/bin/sh
# MinBMS —— 构建脚本（POSIX：Linux / macOS / Git Bash）
#
#   ./build.sh
#
# 与 Makefile 的 build 目标等价：只编译 Test / Demo / Explore，只用 GHC，
# 不需要任何 cabal 包。构建参数必须与 Makefile 保持一致 ——
# CI 的 scripts job 会跑本脚本，用来防止脚本与 Makefile 漂移。
#
# Windows（cmd.exe）用户请用 build.cmd（见该文件）。

set -e

GHC="${GHC:-ghc}"
GHCFLAGS="${GHCFLAGS:--Wall -O1}"

# 与 Makefile 的 `ifeq ($(OS),Windows_NT)` 对应：Windows 上可执行文件带 .exe。
# （GHC 在 Windows 上其实会自动补 .exe，这里显式写出来是为了让输出名可预期。）
case "$(uname -s 2>/dev/null)" in
    MINGW*|MSYS*|CYGWIN*) EXEEXT=".exe" ;;
    *)                    EXEEXT="" ;;
esac

# shellcheck disable=SC2086  # GHCFLAGS 需要按空格拆成多个参数
echo "==> $GHC $GHCFLAGS -o Test$EXEEXT Test.hs"
# shellcheck disable=SC2086
"$GHC" $GHCFLAGS -i. -o Test$EXEEXT Test.hs

# Demo.hs 是 `module Demo (main)`，不是 Main，所以要显式指定入口。
echo "==> $GHC $GHCFLAGS -main-is Demo.main -o Demo$EXEEXT Demo.hs"
# shellcheck disable=SC2086
"$GHC" $GHCFLAGS -i. -main-is Demo.main -o Demo$EXEEXT Demo.hs

echo "==> $GHC $GHCFLAGS -o Explore$EXEEXT Explore.hs"
# shellcheck disable=SC2086
"$GHC" $GHCFLAGS -i. -o Explore$EXEEXT Explore.hs

echo "==> 构建完成：Test$EXEEXT Demo$EXEEXT Explore$EXEEXT"
