# MinBMS —— 构建 / 测试脚本（只用 GHC，不需要任何 cabal 包）
#
#   Unix / macOS / Git Bash :  make test
#   Windows                 :  mingw32-make test      （本机 make 不在 PATH 里，用这个）
#
# 不想记 make / mingw32-make 的名字？仓库根目录还有等价的跨平台便捷脚本
# （构建参数与下面的目标一致，CI 的 scripts job 会跑它们防漂移）：
#   Unix / macOS / Git Bash :  ./build.sh   ./clean.sh [dist]
#   Windows（cmd.exe）      :  build.cmd    clean.cmd  [dist]
#
# 为什么要有它：runghc 是解释执行，跑一遍 Test.hs 要 ~19.5 秒；
# 先编译再跑只要 ~0.37 秒（约 50 倍差）。下面的目标都是「先编译再执行」。
#
# 也可以用 cabal：cabal build --enable-tests all && cabal test all（见 minbms.cabal）。
#
# 产物直接放在仓库根目录（与仓库原本的做法一致，且 .gitignore 已忽略 *.hi/*.o/*.exe）。
# 之所以不塞进 .build/ 子目录：GHC 不会自建输出目录，那样就得依赖 mkdir，
# 而在 Windows 的原生 make（mingw32-make）里 mkdir 不一定可用。

GHC      ?= ghc
GHCFLAGS ?= -Wall -O1

# Windows 上可执行文件需要 .exe 后缀；其它平台留空。
ifeq ($(OS),Windows_NT)
EXEEXT ?= .exe
else
EXEEXT ?=
endif

# 公共模块（各可执行文件的 main 模块不在此列）
MODULES := BashicuMatrix.hs Ordinal.hs Version.hs

.PHONY: all build test demo explore clean distclean

all: build

build: Test$(EXEEXT) Demo$(EXEEXT) Explore$(EXEEXT)

Test$(EXEEXT): Test.hs $(MODULES)
	$(GHC) $(GHCFLAGS) -i. -o $@ $<

# Demo.hs 是 `module Demo (main)`，不是 Main，所以要显式指定入口。
Demo$(EXEEXT): Demo.hs $(MODULES)
	$(GHC) $(GHCFLAGS) -i. -main-is Demo.main -o $@ $<

Explore$(EXEEXT): Explore.hs $(MODULES)
	$(GHC) $(GHCFLAGS) -i. -o $@ $<

test: Test$(EXEEXT)
	./Test$(EXEEXT)

demo: Demo$(EXEEXT)
	./Demo$(EXEEXT)

# 默认只跑一组很小的参数（快）；换参数：make explore ARGS="2 4 4" 或 ARGS="--bm=BM3.3 1 4 3"
ARGS ?= 1 4 3
explore: Explore$(EXEEXT)
	./Explore$(EXEEXT) $(ARGS)

# 删除命令按平台选：
#   - Windows：用 `cmd /c del` / `cmd /c rmdir`（cmd 内置命令，纯 cmd 环境可用）。
#     之所以显式写 `cmd /c`：mingw32-make 在 PATH 上找到 sh.exe 时会改用它当
#     解释器，那时裸 `del` 会被当成不存在的 unix 命令；`cmd /c` 两种情况下都对。
#   - 其它平台：rm。
# del 在「无匹配文件」时返回非零，故配方行用 `-` 前缀让 make 忽略退出码
# （此时会打印一行 `Could Not Find ...`，属正常噪音，退出码仍为 0）。
# 注意：这里只能用普通赋值 `=`，不能用 `?=` —— GNU Make 内置了 `RM = rm -f`，
# 而 `?=` 只在变量「未定义」时生效，会被内置值挡掉（实测 Windows 上 clean 照旧跑 rm）。
# 命令行的 `make RM=...` 仍可覆盖。
ifeq ($(OS),Windows_NT)
RM      = cmd /c del /Q /F
RMDIR   = cmd /c rmdir /S /Q
else
RM      = rm -f
RMDIR   = rm -rf
endif

# 删掉构建产物（可重复执行：产物不存在时也不报错）。
clean:
	-$(RM) *.hi *.o Test$(EXEEXT) Demo$(EXEEXT) Explore$(EXEEXT)

# 在 clean 之上，再删 cabal 的构建目录（`cabal build` 的产物）。
distclean: clean
	-$(RMDIR) dist-newstyle
