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
from nps_ctl import NPSClient

# 连接到单台 NPS 服务器
client = NPSClient(
    base_url="https://nps.example.com",
    auth_key="your_auth_key"
)

# 列出所有客户端
clients = client.list_clients()
for c in clients:
    print(f"{c['Id']}: {c['VerifyKey']}")

# 添加新客户端
client.add_client(remark="my-server", vkey="unique-key")
```

### 作为命令行工具

```bash
# 查看所有边缘节点状态
nps-ctl status

# 列出指定边缘节点的客户端
nps-ctl client list --edge nps-asia

# 从一个边缘节点同步配置到其他所有节点
nps-ctl sync --from nps-asia

# 向所有边缘节点添加域名映射
nps-ctl add-host --domain app.example.com --client my-server --target :8080

# 从 clients.toml 推送客户端配置到边缘节点
nps-ctl npc client-push

# 检查各机器上的 NPC 客户端状态
nps-ctl npc status
```

## 配置

创建 `config/edges.toml` 文件：

```toml
[edges.nps-asia]
api_url = "https://nps-asia.example.com"
auth_key = "your_auth_key"
region = "Asia"

[edges.nps-us]
api_url = "https://nps-us.example.com"
auth_key = "your_auth_key"
region = "US"
```

可选，创建 `config/clients.toml` 用于 NPC 客户端管理：

```toml
[clients.my-server]
ssh_host = "user@my-server.example.com"
vkey = "unique-verify-key"
edges = ["nps-asia", "nps-us"]
```

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

- `get_all_clients()` - 从所有节点获取客户端
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
