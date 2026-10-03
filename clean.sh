#!/bin/sh
# MinBMS —— 清理构建产物（POSIX：Linux / macOS / Git Bash）
#
#   ./clean.sh          删除 *.hi *.o 与 Test / Demo / Explore
#   ./clean.sh dist     额外删除 cabal 的 dist-newstyle/
#
# 与 Makefile 的 clean / distclean 目标等价。可重复执行：
# 产物不存在时也不报错（`rm -f` + 未匹配的 glob 会被安全忽略）。

set -e

# 带/不带 .exe 都删：POSIX 上产物叫 Test，Windows（含 Git Bash）上叫 Test.exe。
# 只列本脚本会生成的三个名字，不碰 main.exe / main-windows.exe / main-linux 等。
rm -f -- *.hi *.o Test Demo Explore Test.exe Demo.exe Explore.exe

if [ "$1" = "dist" ] || [ "$1" = "--dist" ]; then
    rm -rf -- dist-newstyle
fi

echo "==> 已清理构建产物"
