# syntax=docker/dockerfile:1
#
# basmat 运行环境（Bashicu Matrix Calculator）
# ==========================================
#
# 在容器内**编译并运行** https://github.com/kyodaisuu/basmat —— 本仓库只提供这份配方，
# 不包含 basmat 的源码或二进制。
#
#   docker compose -f docker/compose.yaml build
#   docker compose -f docker/compose.yaml run --rm basmat -d "(0)(1)(2)[3]"
#
# 为什么是「构建时从上游拉取」而不是 vendoring：basmat 是 **GPL-3.0** 的第三方程序，
# 本项目是 BSD-3-Clause。把源码/二进制放进本仓库会让许可证边界变复杂；
# 只在构建时按固定 commit 拉取，本仓库就始终只有自己的代码。详见 docker/README.md。
#
# 为什么不用 ./configure && make：上游 Makefile.am 只有一个源文件、只链 -lm
# （`basmat_SOURCES=basmat.c`、`basmat_LDADD=-lm`），直接 gcc 与它等价；
# 而仓库签入的 configure / Makefile.in 与 configure.ac 的版本号并不一致，
# 走 autotools 可能触发 automake 自动重建（撞上 missing 脚本而失败）。
# 目标自包含、无网络、非 root。

# ------------------------------------------------------------------ 构建参数
ARG BASMAT_REPO=https://github.com/kyodaisuu/basmat.git
# 上游 tag（= 当前 master = v4.0）。升级流程见 docker/README.md「如何升级上游版本」。
ARG BASMAT_TAG=v4.0
# tag 是**可移动**的，所以再钉一次 commit sha：对不上就让构建失败，绝不静默跑别的代码。
ARG BASMAT_SHA=f2f0125b6618a1a298f53b63464ebdcec137ff92

# ------------------------------------------------------------------ 1) fetch
FROM debian:bookworm-slim AS fetch
ARG BASMAT_REPO
ARG BASMAT_TAG
ARG BASMAT_SHA
RUN apt-get update \
 && apt-get install -y --no-install-recommends git ca-certificates \
 && rm -rf /var/lib/apt/lists/*
WORKDIR /src
RUN git clone --depth 1 --branch "$BASMAT_TAG" "$BASMAT_REPO" basmat \
 && test "$(git -C basmat rev-parse HEAD)" = "$BASMAT_SHA" \
 && rm -rf basmat/.git

# ------------------------------------------------------------------ 2) build
FROM fetch AS build
RUN apt-get update \
 && apt-get install -y --no-install-recommends gcc libc6-dev \
 && rm -rf /var/lib/apt/lists/*
WORKDIR /src/basmat
RUN gcc -O2 -Wall -o /usr/local/bin/basmat basmat.c -lm

# ------------------------------------------------------------------ 3) runtime
# 与 build 阶段同为 bookworm：glibc 完全一致，不会有「编译在 A、运行在 B」的问题。
FROM debian:bookworm-slim AS runtime

# 非 root 运行（默认 uid/gid 1000）。容器除了自己的参数不需要任何输入输出，
# 也不联网 —— 要用文件时由调用方自行挂载。
RUN useradd --create-home --uid 1000 runner

COPY --from=build /usr/local/bin/basmat /usr/local/bin/basmat
COPY basmat-batch /usr/local/bin/basmat-batch
RUN chmod 0755 /usr/local/bin/basmat-batch

# 构建期冒烟：镜像一造出来就能用（帮助 + 一次真实计算 + 批处理）。
# 把冒烟放在这里，是为了让「拉错 commit / 编译出坏二进制 / 批处理脚本的行尾符坏了」
# 在构建时就暴露 —— 而不是等你跑了半天搜索才发现。
#
# 行尾符为什么会被冒烟抓出来：basmat-batch 是容器内的 POSIX sh 脚本，
# 若以 CRLF 结尾，dash 会报 `/bin/sh^M: bad interpreter`。
# .gitattributes 里已把 `docker/basmat-batch` 钉成 `eol=lf`（clone 出来就是 LF），
# 所以正常流程不会踩到；这里只是不留死角。不用 grep，纯 /bin/sh 内建即可。
RUN basmat -h > /dev/null \
 && basmat "(0)(1)(2)[3]" > /dev/null \
 && out="$(printf '(0)(1)[2]\n' | basmat-batch)" \
 && case "$out" in *"=== DONE 1 ==="*) ;; *) echo "basmat-batch 冒烟失败，输出：$out"; exit 1 ;; esac

USER runner
WORKDIR /work
ENTRYPOINT ["basmat"]
# 不带参数时打印帮助。
CMD ["-h"]
