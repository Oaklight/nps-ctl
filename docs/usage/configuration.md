# 配置

nps-ctl 使用 TOML 配置文件，存放在 `config/` 目录下。

## 边缘节点 — `config/edges.toml`

定义 NPS 边缘服务器：

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

每个边缘节点需要以下字段：

| 字段       | 说明                |
| ---------- | ------------------- |
| `api_url`  | NPS 服务器 API 地址 |
| `auth_key` | API 认证密钥        |
| `region`   | 可读的区域标签      |

## NPC 客户端 — `config/clients.toml`

定义 NPC 客户端机器，用于部署和管理：

```toml
[clients.my-server]
ssh_host = "user@my-server.example.com"
vkey = "unique-verify-key"
edges = ["nps-asia", "nps-us"]
```

每个客户端需要以下字段：

| 字段       | 说明                        |
| ---------- | --------------------------- |
| `ssh_host` | SSH 连接字符串              |
| `vkey`     | NPS 客户端验证密钥          |
| `edges`    | 该客户端使用的边缘节点列表  |

## SOCKS5 代理

通过 SOCKS5 代理路由 API 请求，使用 `--socks-proxy` 参数：

```bash
nps-ctl --socks-proxy 127.0.0.1:1080 status
```

或使用 `--auto-proxy` 自动建立 SSH SOCKS 隧道。
