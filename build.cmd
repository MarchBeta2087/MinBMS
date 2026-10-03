@echo off
rem MinBMS -- 构建脚本（Windows / cmd.exe）
rem
rem   build.cmd
rem
rem 与 Makefile 的 build 目标等价：只编译 Test / Demo / Explore，只用 GHC，
rem 不需要任何 cabal 包，也不依赖 make（Windows 上 make 通常不在 PATH）。
rem 构建参数必须与 Makefile 保持一致 -- CI 的 scripts job 会跑本脚本防漂移。
rem
rem Linux / macOS / Git Bash 用户请用 build.sh（见该文件）。
setlocal

if "%GHC%"=="" set "GHC=ghc"
if "%GHCFLAGS%"=="" set "GHCFLAGS=-Wall -O1"

where %GHC% >nul 2>nul
if errorlevel 1 (
  echo [错误] 找不到 GHC：%GHC%
  echo        请安装 GHC 并确保它在 PATH 里（本项目实测 9.6.7）。
  exit /b 1
)

echo ==^> %GHC% %GHCFLAGS% -o Test.exe Test.hs
%GHC% %GHCFLAGS% -i. -o Test.exe Test.hs
if errorlevel 1 exit /b 1

rem Demo.hs 是 module Demo (main)，不是 Main，所以要显式指定入口。
echo ==^> %GHC% %GHCFLAGS% -main-is Demo.main -o Demo.exe Demo.hs
%GHC% %GHCFLAGS% -i. -main-is Demo.main -o Demo.exe Demo.hs
if errorlevel 1 exit /b 1

echo ==^> %GHC% %GHCFLAGS% -o Explore.exe Explore.hs
%GHC% %GHCFLAGS% -i. -o Explore.exe Explore.hs
if errorlevel 1 exit /b 1

echo ==^> 构建完成：Test.exe Demo.exe Explore.exe
endlocal
