# 快速开始

5 分钟内完成 nps-ctl 的配置并运行。

## 第 1 步 — 创建配置文件

nps-ctl 从 TOML 文件中读取配置。默认搜索路径为：

1. `./config/edges.toml`
2. `~/.config/nps-ctl/edges.toml`
3. `/etc/nps-ctl/edges.toml`

创建 `~/.config/nps-ctl/edges.toml`，至少包含一个 edge：

```toml
auth_crypt_key = "your_16char_key"
public_vkey = "your_public_vkey"

[web]
username = "admin"
password = "your_password"

[[edges]]
name = "nps-main"
api_url = "https://nps.example.com"
auth_key = "your_auth_key"
region = "US"
ssh_host = "cloud.example"
```

| 字段 | 说明 |
|-------|----------------|
| `auth_crypt_key` | NPS 与 NPC 共享的 16 字符加密密钥 |
| `public_vkey` | 用于 NPC 客户端注册的公开验证密钥 |
| `[web]` | NPS Web 管理面板凭据（部署命令使用） |
| `[[edges]]` | 每个需要管理的 NPS 服务器节点对应一个块 |
| `name` | 此 edge 的唯一标识符 |
| `api_url` | NPS 服务器 API URL（使用 HTTPS） |
| `auth_key` | 在 NPS 服务器上配置的 API 认证密钥 |
| `region` | 人类可读的区域标签 |
| `ssh_host` | 用于部署命令的 SSH 主机别名 |

!!! note "注意"
    你可以定义多个 `[[edges]]` 块，通过单个配置文件管理多节点集群。

## 第 2 步 — 检查 edge 状态

验证 nps-ctl 是否能连接到你的 NPS 服务器：

```bash
nps-ctl edge status
```

示例输出：

```
           NPS Edge Status
┏━━━━━━━━━━━━┳━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━┓
┃ Edge       ┃ Region ┃ API URL                     ┃ Status     ┃
┡━━━━━━━━━━━━╇━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━┩
│ nps-main   │ US     │ https://nps.example.com     │ ✓ Online   │
└────────────┴────────┴─────────────────────────────┴────────────┘
```

## 第 3 步 — 列出客户端

查看 edge 上注册的所有 NPC 客户端：

```bash
nps-ctl client list
```

示例输出：

```
┏━━━━┳━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━┳━━━━━━┓
┃ ID ┃ Remark      ┃ VKey          ┃ Status       ┃ Conn ┃
┡━━━━╇━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━╇━━━━━━┩
│ 1  │ my-server   │ abc123def456  │ Connected    │    3 │
│ 2  │ home-nas    │ xyz789uvw012  │ Disconnected │    0 │
└────┴─────────────┴───────────────┴──────────────┴──────┘
```

## 第 4 步 — 添加主机映射

通过 NPS 将域名路由到运行在某个 NPC 客户端上的后端服务：

```bash
nps-ctl host add -d app.example.com -c my-server -T :8080
```

此命令会在所有 edge 上创建一条 HTTP 主机映射，将 `app.example.com` 的请求转发到名为 `my-server` 的 NPC 客户端的 8080 端口。

## 第 5 步 — 验证主机映射

列出所有主机映射以确认创建成功：

```bash
nps-ctl host list
```

你应该能在输出中看到 `app.example.com`，并映射到正确的客户端和目标端口。

## 后续步骤

- **[配置](../get-started/configuration.md)** — `edges.toml` 字段、NPC 客户端定义和代理设置的完整参考
- **[CLI 参考](../guides/cli.md)** — 所有命令组（`edge`、`client`、`host`、`tunnel`、`util`）的完整文档
- **[库用法](../guides/library.md)** — 在你自己的 Python 脚本中使用 `NPSCluster` 和 `NPSClient`
