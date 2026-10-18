# nps-ctl

[![PyPI version](https://img.shields.io/pypi/v/nps-ctl?color=green)](https://pypi.org/project/nps-ctl/)
[![CI](https://github.com/Oaklight/nps-ctl/actions/workflows/ci.yml/badge.svg)](https://github.com/Oaklight/nps-ctl/actions/workflows/ci.yml)
[![License: GPL-3.0](https://img.shields.io/badge/License-GPL--3.0-green.svg)](https://www.gnu.org/licenses/gpl-3.0)

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

# 读取命令默认作用于所有边缘节点；-e 缩小到单个节点
nps-ctl client list
nps-ctl client list --edge nps-asia

# 从一个边缘节点同步配置到其他节点
nps-ctl edge sync --from nps-asia -y

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

读取命令（`client list`、`host list`、`tunnel list`）默认作用于所有已配置的边缘节点。`-e/--edge` 缩小到单个节点，`-a/--all` 显式表示所有节点。写入命令（`host/tunnel add|del|edit`、`client del`）必须提供 `-e` 或 `-a` 之一，不存在静默的全集群默认行为。

输出到管道时不包含 ANSI 样式。在终端中可用 `--no-color` 显式关闭颜色。`edge list`、`edge status` 以及 `client/host/tunnel list` 支持 `--json`。

## 配置

创建 `config/edges.toml` 文件：

```toml
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

`auto` 会探测一次 `/api/system/health`，失败时回退到旧版接口。现代模式的列表请求使用 `/api/*` 并自动获取所有分页；列出隧道不再需要按七种类型分别请求。

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
- `sync_from()` - 从源边缘节点同步配置到目标节点
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

## 许可证

GPL-3.0 — 详见 [LICENSE](LICENSE)。
