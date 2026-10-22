# nps-ctl

[![PyPI version](https://img.shields.io/pypi/v/nps-ctl?color=green)](https://pypi.org/project/nps-ctl/)
[![CI](https://github.com/Oaklight/nps-ctl/actions/workflows/ci.yml/badge.svg)](https://github.com/Oaklight/nps-ctl/actions/workflows/ci.yml)
[![License: GPL-3.0](https://img.shields.io/badge/License-GPL--3.0-green.svg)](https://www.gnu.org/licenses/gpl-3.0)
[![Docker Hub](https://img.shields.io/docker/v/oaklight/nps-ctl?sort=semver&label=docker%20hub&color=green)](https://hub.docker.com/r/oaklight/nps-ctl)
[![Docker pulls](https://img.shields.io/docker/pulls/oaklight/nps-ctl?label=docker%20pulls)](https://hub.docker.com/r/oaklight/nps-ctl)

[English](README_en.md) | [中文](README_zh.md)

一个用于管理 [NPS](https://github.com/djylb/nps) 代理服务器的 Python 库和命令行工具。

> **注意：** 本项目基于 [djylb/nps](https://github.com/djylb/nps)，这是原版 [ehang-io/nps](https://github.com/ehang-io/nps)（自 2021 年起停止维护）的活跃维护分支。API 兼容两个分支，但推荐使用 djylb/nps。

> 本项目会根据需求持续迭代，我也无意搞开源再闭源，请不要为了存档而 fork。如果觉得好用，欢迎加个 Star。

## 功能特性

- **API 客户端**：类型安全的 NPS HTTP API Python 封装
- **多节点支持**：通过统一界面管理多台 NPS 边缘服务器
- **集群同步**：跨边缘节点同步客户端、隧道和域名映射
- **NPC 部署**：通过 SSH 安装、配置和管理 NPC 客户端
- **命令行工具**：Rich 终端界面，支持所有操作
- **Web 管理面板**：默认只读；可选用 `--allow-writes` 启用新增/同步/编辑/删除与添加边缘节点，带 CSRF、同源校验以及 viewer/operator 角色
- **机器可读输出**：JSON 模式和无终端环境的表格输出，便于脚本和 Agent 使用
- **最小依赖**：仅需 [rich](https://github.com/Textualize/rich) 用于终端输出

## 安装

```bash
pip install nps-ctl
```

### 可选：SOCKS5 代理支持

```bash
pip install nps-ctl PySocks
```

## 快速开始

### 作为库使用

```python
from nps_ctl import NPSClient, client_mgmt

# 连接到单台 NPS 服务器
client = NPSClient(
    base_url="https://nps.example.com",
    auth_key="your_auth_key"
)

# 列出所有客户端
for c in client_mgmt.list_clients(client):
    print(f"{c['Id']}: {c['VerifyKey']}")

# 添加新客户端
client_mgmt.add_client(client, remark="my-server", vkey="unique-key")
```

### 作为命令行工具

```bash
# 列出所有已配置的边缘节点（不访问网络）
nps-ctl edge list

# 检查所有边缘节点状态
nps-ctl edge status

# 检查单个边缘节点（客户端、域名映射和隧道）
nps-ctl edge status -e nps-asia

# 检查单个边缘节点的客户端在线状态与域名映射清单
nps-ctl host status -e nps-asia

# 检查单个边缘节点的隧道清单
nps-ctl tunnel status -e nps-asia

# 读取命令默认作用于所有边缘节点；-e 缩小到单个节点
nps-ctl client list
nps-ctl client list --edge nps-asia

# 从一个边缘节点同步配置到其他节点
nps-ctl edge sync --from nps-asia -y

# 或设置 primary 后直接从它同步；--prune 会删除目标节点上多余的资源
nps-ctl edge primary nps-asia
nps-ctl edge sync -y
nps-ctl edge sync --prune -y          # 破坏性操作：请先确认目标节点列表

# 向 edges.toml 添加边缘节点（auth key 从 NPS_EDGE_AUTH_KEY 或隐藏提示读取）
nps-ctl edge add nps-eu --api-url https://nps-eu.example.com --ssh-host cloud.deu1

# 添加客户端并一步推送到它配置的边缘节点
nps-ctl client add --name my-server --ssh-host user@host --edges nps-asia --push -y

# 写入命令必须显式指定目标：-a 表示所有节点，-e 表示单个节点
nps-ctl host add -a -d app.example.com -c my-server -T :8080
nps-ctl host add -e nps-asia -d app.example.com -c my-server -T :8080

# 从 clients.toml 推送客户端配置到边缘节点
nps-ctl client push

# 检查各机器上的 NPC 客户端状态
nps-ctl client status

# 机器可读的节点清单
nps-ctl edge list --json
```

读取命令（`client list`、`edge status`、`host list`、`host status`、`tunnel list`、`tunnel status`）默认作用于所有已配置的边缘节点。`-e/--edge` 缩小到单个节点，`-a/--all` 显式表示所有节点。写入命令（`host/tunnel add|del|edit`、`client del`）必须提供 `-e` 或 `-a` 之一，不存在静默的全集群默认行为。`edge status` 会抓取客户端、域名映射和隧道清单，因此任一抓取失败都会以 1 退出，而不只是在边缘节点不可达时。

输出到管道时不包含 ANSI 样式。在终端中可用 `--no-color` 显式关闭颜色。`edge list`、`edge status`、`host status`、`tunnel status` 以及 `client/host/tunnel list` 支持 `--json`。

## Web 管理面板

`nps-ctl web` 为所有已配置边缘节点提供管理面板。默认只读，只有传入
`--allow-writes` 才会启用变更操作：

```bash
# 单用户
export NPS_WEB_PASSWORD='choose-a-password'
nps-ctl web --username admin --allow-writes

# 多用户与角色
nps-ctl util hash-password          # 输出 PBKDF2 哈希，不打印密码
cat > web-users.toml <<'EOF'
[[users]]
name = "admin"
password_hash = "pbkdf2_sha256$260000$...$..."
role = "operator"

[[users]]
name = "viewer"
password_hash = "pbkdf2_sha256$260000$...$..."
role = "viewer"
EOF
nps-ctl web --users-file web-users.toml --allow-writes
# http://127.0.0.1:8080/
```

启用 `--allow-writes` 后，operator 可以同步边缘节点（可选 `prune`）、添加
客户端/隧道/域名映射、向 `edges.toml` 添加边缘节点，以及在单个节点上编辑或
删除客户端、隧道和域名映射。每个操作都使用显式目标列表、确认步骤、每次进程
独立的 CSRF token、同源/Host 校验和单写入锁。viewer 始终只能看到只读页面；
未启用 `--allow-writes` 时所有变更接口返回 403。

默认只监听 `127.0.0.1`。未配置凭据时绑定到非回环地址会被拒绝，除非传入
`--insecure`；网络绑定且无认证时始终拒绝写入。面板展示边缘节点健康状态
（`online`/`partial`/`offline`）和资源数量，并可逐个节点查看客户端、隧道和
域名映射；不可用的数量以 `null` 返回，JSON 输出会隐藏凭据（客户端验证密钥、
隧道密码和 Basic Auth）。内置服务器只提供 HTTP，如需暴露到回环地址之外，请
在前置代理上终止 TLS；可直接使用的 systemd 与 Caddy 配置见
[`deploy/web`](deploy/web)。

### Docker

镜像发布在 Docker Hub
[`oaklight/nps-ctl`](https://hub.docker.com/r/oaklight/nps-ctl)：

| 标签 | 基础镜像 | 说明 |
| --- | --- | --- |
| `latest`、`latest-python` | `python:3.12-slim` | 安装 wheel，包含完整 CLI |
| `<version>-alpine` | `alpine` | Nuitka musl 二进制，不含 Python 运行时 |
| `<version>-glibc` | `scratch` + glibc 运行时 | Nuitka glibc 二进制，不含 Python 运行时 |

启动面板：

```bash
docker run -d --name nps-ctl-web \
  -p 8080:8080 \
  -v "$PWD/config:/config" \
  -e NPS_WEB_USERNAME=admin \
  -e NPS_WEB_PASSWORD='choose-a-password' \
  oaklight/nps-ctl:latest
```

容器读取 `/config/edges.toml`，并要求提供 `/config/web-users.toml` 或
`NPS_WEB_USERNAME`/`NPS_WEB_PASSWORD`。追加 `--allow-writes` 可启用变更操作。
其他命令会自动在前面加上 `--config /config/edges.toml`：

```bash
docker run --rm -v "$PWD/config:/config" oaklight/nps-ctl:latest edge status
```

Compose 文件、环境变量和本地构建方式见
[`docker/README.md`](docker/README.md)。两个二进制镜像体积都很小：glibc 版本
基于 `scratch`，只包含其二进制所需的运行库。

## 配置

创建 `config/edges.toml` 文件：

```toml
primary = "nps-asia"   # `edge sync` 的默认源节点

[[edges]]
name = "nps-asia"
api_url = "https://nps-asia.example.com"
auth_key = "your_auth_key"
region = "Asia"
ssh_host = "cloud.jpn1"

[[edges]]
name = "nps-us"
api_url = "https://nps-us.example.com"
auth_key = "your_auth_key"
region = "US"
ssh_host = "cloud.usa1"
```

可选的顶层 `primary` 指定 `edge sync` 的默认源节点。使用
`edge primary NAME` 设置；使用 `edge add NAME --api-url URL` 追加新节点
（auth key 从 `NPS_EDGE_AUTH_KEY` 或隐藏提示读取，绝不出现在 argv 中）。
两种编辑都会保留文件中的注释。

当边缘节点配置了凭据且服务端支持时，会自动使用现代 `/api/*` 管理接口。在节点条目中添加 `username`/`password`（或 `platform_token`）：

```toml
[[edges]]
name = "nps-asia"
api_url = "https://nps-asia.example.com"
auth_key = "your_auth_key"
username = "admin"
password = "your_password"
# platform_token = "..."   # username/password 的替代方案
api_mode = "auto"           # "auto" | "modern" | "legacy"
```

`auto` 会探测一次 `/api/system/health`，失败时回退到旧版接口。现代模式的列表请求使用 `/api/*` 并自动获取所有分页；旧版接口列出隧道仍会按八种模式分别请求，其中包括 djylb/nps 用来存储 socks5 与 httpProxy 隧道的 `mixProxy`。

可选，创建 `config/clients.toml` 用于 NPC 客户端管理：

```toml
[[clients]]
name = "my-server"
ssh_host = "user@my-server.example.com"
vkey = "unique-verify-key"
edges = ["nps-asia", "nps-us"]
```

配置目录按 `./config`、`~/.config/nps-ctl`、`/etc/nps-ctl` 的顺序查找。使用 `--config` 可以指定具体的 `edges.toml`。

## API 参考

### NPSClient

单节点 NPS 服务器客户端。

- `list_clients()` - 获取所有客户端
- `add_client()` - 添加新客户端
- `edit_client()` - 修改客户端
- `del_client()` - 删除客户端
- `list_tunnels()` - 获取所有隧道
- `add_tunnel()` - 添加新隧道
- `list_hosts()` - 获取所有域名映射
- `add_host()` - 添加新域名映射

### NPSCluster

多节点管理器。

- `edge_names` - 按文件顺序返回已配置的边缘节点名称
- `get_all_clients()` / `get_all_tunnels()` / `get_all_hosts()` - 从所有节点获取数据。返回 `EdgeResults` 映射；失败的节点对应空列表，原因记录在 `.errors` 中
- `sync_from(..., prune=False)` - 从源边缘节点同步配置到目标节点。`prune=True` 还会删除源节点上不存在的资源，并在源数据无法完整读取时中止
- `reload()` - 就地重新加载 `edges.toml`（供面板的“Add edge”操作使用）
- `broadcast_host()` - 向所有节点添加域名映射

## 开发

```bash
# 安装开发依赖
pip install -e ".[dev,test]"

# 代码检查和类型检查
make lint

# 运行测试
make test

# 构建包
make build
```

### 二进制构建

`make build-binary` 生成原生 Nuitka 二进制；在 Linux 上链接 glibc。
`make build-binary-musl` 在 Alpine 中构建并链接 musl，因此该产物可在 musl
发行版（如 Alpine）上运行，但无法直接在 Debian、Arch 等 glibc 系统上运行。
如需构建完整平台矩阵并下载产物，请使用 _Nuitka Binary Build_ workflow。

## 致谢

- `client status` 与 `edge sync` 的部分失败退出码（#35）来自
  [@dannyward630](https://github.com/dannyward630) 的
  [`fix/35-partial-failure-exit-codes`](https://github.com/dannyward630/nps-ctl/tree/fix/35-partial-failure-exit-codes)
  分支。

## 许可证

GPL-3.0 — 详见 [LICENSE](LICENSE)。
