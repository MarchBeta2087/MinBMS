@echo off
rem MinBMS -- 清理构建产物（Windows / cmd.exe）
rem
rem   clean.cmd          删除 *.hi *.o 与 Test.exe / Demo.exe / Explore.exe
rem   clean.cmd dist     额外删除 cabal 的 dist-newstyle 目录
rem
rem 与 Makefile 的 clean / distclean 目标等价，且可重复执行：
rem 产物不存在时不会报错（逐项 if exist 判断）。
rem
rem Linux / macOS / Git Bash 用户请用 clean.sh（见该文件）。
setlocal

for %%f in (*.hi *.o) do if exist "%%f" del /Q /F "%%f"
for %%f in (Test.exe Demo.exe Explore.exe) do if exist "%%f" del /Q /F "%%f"

if /I "%1"=="dist" if exist "dist-newstyle" rmdir /S /Q "dist-newstyle"

echo ==^> 已清理构建产物
endlocal
