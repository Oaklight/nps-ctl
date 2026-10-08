# 配置

nps-ctl 从 TOML 文件读取配置。主配置文件是 `edges.toml`，定义所有 NPS 边缘节点和共享设置。同一目录下的可选文件 `clients.toml` 用于定义 NPC 客户端机器的部署信息。

## 配置文件位置

nps-ctl 按以下顺序搜索 `edges.toml`：

1. `./config/edges.toml`（项目本地）
2. `~/.config/nps-ctl/edges.toml`（用户配置）
3. `/etc/nps-ctl/edges.toml`（系统级配置）

使用自定义路径：

```bash
nps-ctl --config /path/to/edges.toml edge status
```

## edges.toml

配置文件使用 TOML 的 `[[edges]]` 表数组语法。每个 `[[edges]]` 块定义一个 NPS 边缘节点。

### 最小示例

包含两个边缘节点和旧版 API 认证的可用配置：

```toml
auth_crypt_key = "1234567890abcdef"
public_vkey = "my-public-vkey"

[web]
username = "admin"
password = "s3cret"

[[edges]]
name = "nps-us"
api_url = "https://nps-us.example.com"
auth_key = "your_auth_key_here"
region = "US"
ssh_host = "cloud.usa1"

[[edges]]
name = "nps-asia"
api_url = "https://nps-asia.example.com"
auth_key = "your_auth_key_here"
region = "Asia"
ssh_host = "cloud.jpn1"
```

### 完整示例

所有可用字段及其默认值：

```toml
# AES encryption key for NPS auth, exactly 16 characters.
# Shared across all edges — must match nps.conf on each server.
auth_crypt_key = "1234567890abcdef"

# Public verification key for client registration.
public_vkey = "my-public-vkey"

# Web UI credentials, shared across all edges.
[web]
username = "admin"
password = "s3cret"

# Port configuration (optional, defaults shown).
[ports]
http_proxy = 30080    # NPS HTTP reverse proxy port
bridge_tcp = 51234    # NPC ↔ NPS bridge (TCP)
bridge_tls = 51235    # NPC ↔ NPS bridge (TLS)
web = 25412           # NPS web management UI port

# Edge definitions — one [[edges]] block per NPS server node.
[[edges]]
name = "nps-us"                            # Required: unique identifier
api_url = "https://nps-us.example.com"     # Required: NPS server URL
auth_key = "your_auth_key_here"            # Legacy API auth key
region = "US"                              # Human-readable region label
ssh_host = "cloud.usa1"                    # SSH host for deploy commands

# Modern API fields (v0.35.0+, optional)
username = ""              # Web login username
password = ""              # Web login password
platform_token = ""        # Platform API token
api_mode = "auto"          # "legacy", "modern", or "auto" (probe server)

[[edges]]
name = "nps-asia"
api_url = "https://nps-asia.example.com"
auth_key = "your_auth_key_here"
region = "Asia"
ssh_host = "cloud.jpn1"
```

### 顶层字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `auth_crypt_key` | string | AES 加密密钥（16 个字符）。必须与所有边缘节点上的 `nps.conf` 一致。 |
| `public_vkey` | string | NPC 客户端的公共注册密钥。 |

### `[web]` 部分

| 字段 | 默认值 | 说明 |
|------|--------|------|
| `username` | `"admin"` | Web UI 登录用户名，所有边缘节点共享。 |
| `password` | `"admin"` | Web UI 登录密码，所有边缘节点共享。 |

### `[ports]` 部分

所有端口均为可选，默认值为 NPS 标准值。这些端口在通过 `edge install` 或 `edge reconfig` 部署 NPS 时使用。

| 字段 | 默认值 | 说明 |
|------|--------|------|
| `http_proxy` | `30080` | HTTP 反向代理端口。 |
| `bridge_tcp` | `51234` | NPC 到 NPS 的桥接端口（TCP）。 |
| `bridge_tls` | `51235` | NPC 到 NPS 的桥接端口（TLS）。 |
| `web` | `25412` | Web 管理界面端口。 |

### `[[edges]]` 条目

| 字段 | 必填 | 默认值 | 说明 |
|------|------|--------|------|
| `name` | 是 | — | 唯一的边缘节点标识符（用于 `-e` 参数）。 |
| `api_url` | 是 | — | NPS 服务端 URL（例如 `https://nps-us.example.com`）。 |
| `auth_key` | 否 | `""` | API 认证密钥（旧版 API）。 |
| `region` | 否 | `""` | 人类可读的区域标签。 |
| `ssh_host` | 否 | `""` | 用于部署命令的 SSH 主机别名。 |
| `username` | 否 | `""` | Web 登录用户名（新版 API，v0.35.0+）。 |
| `password` | 否 | `""` | Web 登录密码（新版 API，v0.35.0+）。 |
| `platform_token` | 否 | `""` | 平台 API 令牌（新版 API，v0.35.0+）。 |
| `api_mode` | 否 | `"auto"` | API 模式：`"legacy"`、`"modern"` 或 `"auto"`。 |

!!! tip "提示"
    当 `api_mode` 为 `"auto"`（默认值）时，nps-ctl 会探测服务端以确定可用的 API 版本。如果已知 NPS 版本，可以显式设置：`"legacy"` 适用于使用 `auth_key` 的旧版本，`"modern"` 适用于使用 `username`/`password` 或 `platform_token` 的 v0.35.0+ 版本。

## clients.toml

NPC 客户端定义可以作为 `[[clients]]` 条目写在 `edges.toml` 中，也可以放在同一目录下的单独 `clients.toml` 文件中。如果两者都存在，`clients.toml` 优先。

```toml
[[clients]]
name = "my-server"
ssh_host = "10.0.0.5"
vkey = "unique-verify-key"
edges = ["nps-us", "nps-asia"]
remark = "My backend server"
conn_type = "tls"
ssh_user = "root"
http_proxy = ""

[[clients]]
name = "home-nas"
ssh_host = "oaklight.oasis"
vkey = "another-verify-key"
edges = ["nps-us", "nps-asia"]
```

### `[[clients]]` 条目

| 字段 | 必填 | 默认值 | 说明 |
|------|------|--------|------|
| `name` | 是 | — | 客户端标识符（用于 `-c` 参数）。 |
| `ssh_host` | 是 | — | 用于 NPC 部署的 SSH 主机。 |
| `edges` | 否 | `[]` | 该客户端连接的边缘节点名称列表。 |
| `vkey` | 否 | `""` | 验证密钥（为空时自动生成）。 |
| `remark` | 否 | 与 `name` 相同 | 在 NPS Web UI 中显示的人类可读标签。 |
| `conn_type` | 否 | `"tls"` | 桥接连接类型：`"tls"`、`"tcp"` 或 `"kcp"`。 |
| `ssh_user` | 否 | `""` | SSH 登录用户（覆盖 SSH 配置中的默认值）。 |
| `http_proxy` | 否 | `""` | 安装时下载 NPC 二进制文件所用的 HTTP 代理。 |

## 代理配置

nps-ctl 支持在边缘节点不可直接访问时，通过代理路由 API 请求。

```bash
# HTTP proxy
nps-ctl --proxy http://127.0.0.1:8080 edge status

# SOCKS5 proxy (requires PySocks: pip install PySocks)
nps-ctl --socks-proxy 127.0.0.1:1080 edge status

# Auto-create an SSH SOCKS tunnel through a jump host
nps-ctl --auto-proxy jump-host edge status
```

| 参数 | 说明 |
|------|------|
| `--proxy URL` | 通过 HTTP 代理路由 API 请求。 |
| `--socks-proxy HOST:PORT` | 通过 SOCKS5 代理路由 API 请求。 |
| `--auto-proxy HOST` | 通过指定主机自动创建 SSH SOCKS 隧道。 |

!!! note "注意"
    `--auto-proxy` 会启动一个后台 SSH 隧道，命令结束时自动清理。当边缘节点只能通过特定跳板机访问时，该选项非常实用。
