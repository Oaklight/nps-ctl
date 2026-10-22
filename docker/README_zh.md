# Docker 镜像

[English](README_en.md) | [返回 Docker 目录](README.md)

三种镜像发布在 Docker Hub
[`oaklight/nps-ctl`](https://hub.docker.com/r/oaklight/nps-ctl)：

| 标签 | 基础镜像 | 大小 | 说明 |
| --- | --- | --- | --- |
| `latest`、`latest-python`、`<version>`、`<version>-python` | `python:3.12-slim` | ~130 MB | 从 PyPI 安装 wheel，包含完整 CLI |
| `<version>-alpine`（发布时同时更新 `latest-alpine`） | `alpine` | ~22 MB | Nuitka musl 二进制，不含 Python 运行时 |
| `<version>-glibc`（发布时同时更新 `latest-glibc`） | `scratch` + glibc 运行时 | ~28 MB | Nuitka glibc 二进制，不含 Python 运行时 |

所有镜像以非 root 用户（uid 10001）运行，监听 `8080`，配置保存在 `/config`。
`latest` 指向 Python 镜像；发布时与 `latest-python`、`latest-alpine`、
`latest-glibc` 一起更新。

glibc 版本基于 `scratch` 组装：镜像只包含其二进制所链接的 Ubuntu 24.04 glibc
运行时组件、zlib、CA 证书，以及用于入口脚本的静态 busybox。体积接近 Alpine
镜像，同时可在 glibc 系统上运行。musl 系统请用 `-alpine`，glibc 系统用
`-glibc`；需要最通用的版本时使用默认的 Python 镜像。

## 快速开始

创建配置目录，放入 `edges.toml`；如需认证，再放入用户文件：

```bash
mkdir -p config
cp /etc/nps-ctl/edges.toml config/
nps-ctl util hash-password          # 将输出粘贴到 config/web-users.toml

docker run -d --name nps-ctl-web \
  -p 8080:8080 \
  -v "$PWD/config:/config" \
  oaklight/nps-ctl:latest
```

然后打开 `http://127.0.0.1:8080/`，用用户文件中的账号登录。

面板绑定到非回环地址时**必须认证**，因此没有 `/config/web-users.toml` 时
必须提供 `NPS_WEB_USERNAME`/`NPS_WEB_PASSWORD`，否则容器拒绝启动：

```bash
docker run -d --name nps-ctl-web \
  -p 8080:8080 \
  -v "$PWD/config:/config" \
  -e NPS_WEB_USERNAME=admin \
  -e NPS_WEB_PASSWORD='choose-a-password' \
  oaklight/nps-ctl:latest
```

## 写操作

面板默认只读。传入 `--allow-writes` 可启用同步、添加边缘节点以及编辑/删除
操作；入口脚本会把参数追加到默认的 `web` 命令后：

```bash
docker run ... oaklight/nps-ctl:latest --allow-writes
```

容器用户必须能写入 `/config/edges.toml`（“添加边缘节点”会追加内容）。
可在宿主机执行 `chown -R 10001:10001 config`，或使用
`--user "$(id -u):$(id -g)"` 运行容器。

## 其他命令

传给容器的任何内容都会作为 `nps-ctl` 执行，并自动在前面加上
`--config /config/edges.toml`：

```bash
docker run --rm -v "$PWD/config:/config" oaklight/nps-ctl:latest edge status
docker run --rm oaklight/nps-ctl:latest --version
```

## Compose

[`compose.example.yaml`](compose.example.yaml) 是带注释的起点：

```bash
docker compose -f docker/compose.example.yaml up -d
```

环境变量：`IMAGE_TAG`、`NPS_CTL_PORT`、`NPS_CTL_CONFIG`、
`NPS_WEB_USERNAME`、`NPS_WEB_PASSWORD`。取消 `command:` 的注释即可带上
`--allow-writes`。

从工作区本地构建：

```bash
python -m build
LOCAL_WHEEL=$(basename "$(ls dist/*.whl | head -1)") \
  docker compose -f docker/compose.dev.yaml up --build
```

## TLS

镜像与 systemd 部署一样只提供 HTTP。请在发布端口前用反向代理
（Caddy、nginx、Traefik）终止 TLS；应用本身已发送 CSP、
`X-Frame-Options: DENY`、`Cache-Control: no-store` 和 `nosniff`。

## 构建二进制镜像

二进制镜像使用 Nuitka 产物，先构建：

```bash
make build-binary          # glibc
make build-binary-musl     # musl（需要 Docker）
make build-docker-alpine   # 或：make build-docker-glibc
```

Docker 相关目标见 `make help`。发布流程
（`.github/workflows/docker.yml`）会为 amd64 与 arm64 构建并推送所有变体，
并对每个镜像执行 `--version` 冒烟测试。
