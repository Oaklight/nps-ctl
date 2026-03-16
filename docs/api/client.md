# NPSClient

`nps_ctl.base.NPSClient` — 单节点 NPS 服务器 API 客户端。

## 构造函数

```python
NPSClient(
    base_url: str,
    auth_key: str,
    socks_proxy: str | None = None,
    proxy: str | None = None,
    timeout: int = 10,
)
```

| 参数          | 说明                                             |
| ------------- | ------------------------------------------------ |
| `base_url`    | NPS 服务器地址（如 `https://nps.example.com`）   |
| `auth_key`    | API 认证密钥                                     |
| `socks_proxy` | 可选 SOCKS5 代理（`host:port`）                  |
| `proxy`       | 可选 HTTP 代理地址                               |
| `timeout`     | 请求超时时间（秒，默认 10）                      |

## 客户端方法

| 方法                              | 说明         |
| --------------------------------- | ------------ |
| `list_clients(search="")`         | 列出所有客户端 |
| `add_client(remark, vkey, ...)`   | 添加新客户端   |
| `edit_client(id, remark, ...)`    | 编辑客户端     |
| `del_client(id)`                  | 删除客户端     |

## 隧道方法

| 方法                                          | 说明       |
| --------------------------------------------- | ---------- |
| `list_tunnels(client_id=None, type="")`        | 列出隧道   |
| `add_tunnel(client_id, type, port, target)`   | 添加隧道   |
| `edit_tunnel(id, ...)`                         | 编辑隧道   |
| `del_tunnel(id)`                               | 删除隧道   |

## 域名映射方法

| 方法                                         | 说明           |
| -------------------------------------------- | -------------- |
| `list_hosts()`                               | 列出域名映射   |
| `add_host(client_id, host, target, ...)`     | 添加域名映射   |
| `edit_host(id, ...)`                         | 编辑域名映射   |
| `del_host(id)`                               | 删除域名映射   |
