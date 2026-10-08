# basmat 运行环境（Docker）

在容器里**编译并运行** [basmat](https://github.com/kyodaisuu/basmat)（Bashicu Matrix Calculator）。

basmat 是一个**独立的第三方程序**，用来把 BMS 的计算过程一步步打印出来、并给出序数
（记法用 `w` = ω、`e` = ε、`p` = Bashicu 的 ψ）。本目录把它装进一个自包含的镜像，
供 `tools/` 下的 Python 工具当作「**oracle**」调用：

- 给 `Explore.hs` 标 `unresolved` 的矩阵补序数（尤其是 ≥ ε₀、超出本仓库 `Ordinal.hs` 表示力的那些）；
- 复核 MinBMS 已定序的结果（**交叉验证**，不是替换）。

---

## 快速开始

```bash
# 构建（首次，或改了 Dockerfile 之后）
docker compose -f docker/compose.yaml build

# 跑一条（参数原样传给 basmat，注意给方括号加引号）
docker compose -f docker/compose.yaml run --rm basmat -d "(0)(1)(2)[3]"
docker compose -f docker/compose.yaml run --rm basmat -o 2 -s 100000 "(0,0)(1,1)[3]"
docker compose -f docker/compose.yaml run --rm basmat -h

# 批处理：一次容器启动跑几百条（Windows / Docker Desktop 上快一个数量级）
docker compose -f docker/compose.yaml run --rm -T basmat-batch < queries.txt
```

`queries.txt` 每行一个 `ini`（即 `BM[n]`，不用加引号）：

```
# 以 # 开头是注释，空行忽略
(0)(1)(2)[3]
(0,0)(1,1)[3]
```

批处理的选项由环境变量 `BASMAT_ARGS` 控制，默认 `-d -t 1`
（`-d` 出详细过程；`-t 1` 只算一步 —— 读初始矩阵的序数时这最省）。换版本：

```bash
docker compose -f docker/compose.yaml run --rm -T -e BASMAT_ARGS='-v 3.3 -d -t 1' basmat-batch < queries.txt
```

不想用 compose、只用 `docker`：

```bash
docker build --platform linux/amd64 -t minbms/basmat:4.0-f2f0125 docker/
docker run --rm minbms/basmat:4.0-f2f0125 -d "(0)(1)(2)[3]"
docker run --rm -i --entrypoint basmat-batch minbms/basmat:4.0-f2f0125 < queries.txt
```

---

## 镜像里有什么

| 内容 | 说明 |
|---|---|
| `/usr/local/bin/basmat` | 上游 `basmat.c` 编译出的可执行文件（`gcc -O2 -Wall -o basmat basmat.c -lm`） |
| `/usr/local/bin/basmat-batch` | 本仓库的批处理驱动（POSIX sh，见该文件头部注释） |
| 用户 / 工作目录 | 非 root（`runner`，uid 1000）/ `/work` |
| 网络 | 运行**不需要**网络；只有**构建**时要访问上游仓库 |

镜像分三阶段（`fetch` → `build` → `runtime`，见 `Dockerfile`），运行层里
**没有编译器、没有 git、没有源码**，只留一个可执行文件。

---

## 许可证

**这是使用本镜像前必须知道的一件事。**

- basmat 是 **GPL-3.0** 的第三方程序（Copyright © Fish、Bashicu、koteitan、Nish、rpakr、Ecl1psed 等，
  见上游 `AUTHORS` / `COPYING`）。本项目是 **BSD-3-Clause**。
- 本仓库**不包含** basmat 的源码，也不包含编译产物，只有一份「配方」（`Dockerfile` + compose + 批处理脚本）。
- **本地构建、本地运行不需要做任何额外的事。** 用子进程 + stdin/stdout 跟 GPL 程序交互
  不构成衍生作品，本仓库的 Haskell / Python / shell 代码仍按 BSD-3-Clause 授权。
- **但如果你把这个镜像发布出去**（推到 Docker Hub / GHCR、或拷贝给别人），那就是在
  **分发 basmat 的目标码**，GPL-3.0 的义务随之生效：需要随附或书面提供**对应源码**，
  并保留其许可证与版权声明。本仓库的做法让这件事很容易做到 —— 构建参数里已经写死了
  源码出处：

  > 对应源码 = <https://github.com/kyodaisuu/basmat> @ `f2f0125b6618a1a298f53b63464ebdcec137ff92`（tag `v4.0`），GPL-3.0

- 另外，**不要把 basmat 的源码或二进制提交进本仓库**（`.gitignore` 也只放行了 `docker/` 这个目录，
  构建上下文同样是 `docker/`，不存在把源码带进来的路径）。
- 与 `CONTRIBUTING.md` 的铁律二一致：解析它的输出（互操作性、数学事实）没问题，
  但不要把它的**文案**当自己的文档搬过来。

---

## 如何升级上游版本

三个 `ARG` 都在 `Dockerfile` 顶部（compose 里可用环境变量覆盖）：

```bash
# 1. 看上游现在到哪了
git ls-remote https://github.com/kyodaisuu/basmat.git refs/heads/master refs/tags/*

# 2. 把 vX.Y 对应的 sha 填进 Dockerfile 的 BASMAT_TAG / BASMAT_SHA，同步改：
#    - compose.yaml 里的 image 标签（形如 4.0-<sha 前 7 位>）
#    - compose.yaml 里 BASMAT_TAG / BASMAT_SHA 的默认值
#    - 本节上面「对应源码」那一行

# 3. 重新构建并跑冒烟 + 校准（校准会判断行为有没有变）
docker compose -f docker/compose.yaml build
docker compose -f docker/compose.yaml run --rm basmat -h
python ../tools/calibrate.py     # 需要 Docker；详见 tools/README.md
```

**为什么钉 sha 而不只钉 tag**：tag 可以被上游移动（甚至删除后重建）。
Dockerfile 里用 `git rev-parse HEAD` 比对 sha，对不上就让**构建失败** ——
宁可构建不出来，也不要静默地跑一份来历不明的代码。

---

## 构建很慢？（实测提醒）

首次 `build` 要跑两次 Debian 的 `apt-get`（装 git/gcc）。**实测**在
`deb.debian.org` 只有约 390 kB/s 的网络上，`apt-get update` 一条就花 25 秒，
整次构建可能到 **10–15 分钟**。这不是卡死，是在下载。

想快一点：

```bash
# 1) 先把基础镜像拉好（buildkit 会命中本地缓存）
docker pull debian:bookworm-slim

# 2) 想让 apt 走更快的镜像源：在 Dockerfile 里那两处 `apt-get update` 之前
#    临时插一行（bookworm 用的是 deb822 格式的源文件）：
#      RUN sed -i 's|deb.debian.org|<你信任的镜像源>|g' /etc/apt/sources.list.d/debian.sources

# 3) 构建一次之后，基础镜像与各层都在本地缓存里，重复构建几乎瞬间完成
```

镜像本身很小（**114 MB**），慢的只是首次构建时的那两次 apt。

---

## 设计取舍（为什么这么做）

- **直接 `gcc`，不走 `./configure && make`。** 上游 `Makefile.am` 只有一个源文件、只链 `-lm`
  （`basmat_SOURCES=basmat.c`、`basmat_LDADD=-lm`），直接编译与它等价；而仓库里签入的
  `configure` / `Makefile.in` 与 `configure.ac` 的版本号并不一致，走 autotools 可能触发
  automake 自动重建（撞上 `missing` 脚本而失败）。少一层，少一个坑。
- **base 用 `debian:bookworm-slim`（不是 alpine）。** build 与 runtime 同为 bookworm，
  glibc 完全一致；不选 alpine 是为了避免 glibc/musl 的差异带来任何意外。
- **构建范围 = `docker/`。** 上下文只有几个小文件，根目录因此不需要 `.dockerignore`。
- **批处理。** Windows / Docker Desktop 上每开一个容器要 0.3–1 秒，逐条 `docker run`
  在搜索场景下开销过大；`basmat-batch` 让一个容器跑完整批。
- **构建期冒烟。** `basmat -h` + 一次真实计算，把「拉错 commit / 编出坏二进制」挡在构建阶段。
