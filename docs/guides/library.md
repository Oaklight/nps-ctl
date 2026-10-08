# Python 库

nps-ctl 可以作为 Python 库使用，以编程方式管理 NPS。
这在自动化脚本、自定义仪表盘或将 NPS 操作集成到更大的基础设施工具链中时非常有用。

## NPSClient

`NPSClient` 负责与单个 NPS 服务器的认证通信。
特定领域的操作位于独立模块中，这些模块接受 `NPSClient` 实例作为第一个参数。

### 初始化

```python
from nps_ctl import NPSClient

nps = NPSClient("https://nps.example.com:8024", auth_key="your_auth_key")
```

!!! note "注意"
    `NPSClient` 是一个 dataclass。除 `base_url` 外，所有参数都是可选的关键字参数。
    完整参数列表请参阅 [API 参考](../reference/api.md#npsclient)。

### 客户端管理

```python
from nps_ctl.client_mgmt import list_clients, add_client, del_client

# List all registered NPC clients
clients = list_clients(nps)
for c in clients:
    print(f"{c['Id']}: {c['Remark']} (connected={c['IsConnect']})")

# Add a new client
add_client(nps, remark="my-server", vkey="unique-key-123")
```

`list_clients` 返回 `list[ClientInfo]`。每个 `ClientInfo` 是一个 `TypedDict`，
包含 `Id`、`Remark`、`VerifyKey`、`Status`、`IsConnect`、`Addr`、`RateLimit`、
`MaxConn` 和 `NowConn` 等键。

### 域名映射管理

```python
from nps_ctl.host import list_hosts, add_host, edit_host, del_host

# List all host (domain) mappings
hosts = list_hosts(nps)
for h in hosts:
    print(f"{h['Host']} -> {h['Target']}")

# Add a host mapping (client_id is the NPS-internal numeric ID)
add_host(nps, client_id=3, host="app.example.com", target="127.0.0.1:8080")

# Edit an existing host
edit_host(nps, host_id=7, client_id=3, host="app.example.com",
          target="127.0.0.1:9090")

# Delete a host mapping
del_host(nps, host_id=7)
```

### 隧道管理

```python
from nps_ctl.tunnel import list_tunnels, add_tunnel, del_tunnel

# List all tunnels (queries all types when tunnel_type is empty)
tunnels = list_tunnels(nps)

# List only TCP tunnels
tcp_tunnels = list_tunnels(nps, tunnel_type="tcp")

# Add a TCP tunnel
add_tunnel(nps, client_id=3, tunnel_type="tcp",
           port=18080, target="127.0.0.1:8080", remark="web")

# Delete a tunnel
del_tunnel(nps, tunnel_id=12)
```

## NPSCluster

`NPSCluster` 通过单个 TOML 配置文件管理多个 NPS 边缘节点，
提供跨所有边缘节点的批量查询和广播操作。

### 初始化

```python
from nps_ctl import NPSCluster

cluster = NPSCluster("~/.config/nps-ctl/edges.toml")
```

`NPSCluster` 支持上下文管理器用法，以确保正确清理 SOCKS 代理连接：

```python
with NPSCluster("~/.config/nps-ctl/edges.toml") as cluster:
    clients = cluster.get_all_clients()
    # ... work with the cluster
```

### 查询所有边缘节点

`get_all_clients`、`get_all_tunnels` 和 `get_all_hosts` 会并行从每个边缘节点获取数据，
返回以边缘节点名称为键的字典：

```python
# Returns dict[str, list[ClientInfo]]
all_clients = cluster.get_all_clients(max_workers=4)
for edge_name, clients in all_clients.items():
    print(f"{edge_name}: {len(clients)} clients")

# Same pattern for tunnels and hosts
all_hosts = cluster.get_all_hosts()
```

### 广播操作

广播方法将同一操作应用到每个边缘节点：

```python
# Add a host mapping to all edges at once
results = cluster.broadcast_host(
    client_remark="my-server",
    host_domain="app.example.com",
    target="127.0.0.1:8080",
)
# results: {"nps-america": True, "nps-asia": True, "nps-europe": True}

# Add a client to all edges
cluster.broadcast_client(remark="new-server", vkey="key-456")

# Add a tunnel to all edges
cluster.broadcast_tunnel(
    client_remark="my-server",
    tunnel_type="tcp",
    port=18080,
    target="127.0.0.1:8080",
)
```

### 同步配置

`sync_from` 将客户端、隧道和域名映射从一个边缘节点复制到所有其他节点：

```python
results = cluster.sync_from(
    source_name="nps-america",
    sync_clients=True,
    sync_tunnels=True,
    sync_hosts=True,
)
```

### 边缘节点与客户端查询

```python
# List configured edge names
print(cluster.edge_names)       # ["nps-america", "nps-asia", "nps-europe"]

# List configured NPC client names
print(cluster.npc_client_names) # ["cloud.usa1", "cloud.jpn1", ...]

# Get a specific edge config
edge = cluster.get_edge("nps-america")  # EdgeConfig or None

# Get the NPSClient for a specific edge
nps = cluster.get_client("nps-america") # NPSClient or None
```

## 错误处理

所有 API 错误都继承自 `NPSError`：

```python
from nps_ctl.exceptions import NPSError, NPSAuthError, NPSAPIError

try:
    clients = list_clients(nps)
except NPSAuthError:
    print("Authentication failed — check your auth_key")
except NPSAPIError as e:
    print(f"API error (HTTP {e.status_code}): {e}")
except NPSError as e:
    print(f"NPS error: {e}")
```

| 异常 | 触发条件 |
|------|----------|
| `NPSError` | 所有 NPS 错误的基类 |
| `NPSAuthError` | 认证失败或服务器时间获取失败 |
| `NPSAPIError` | API 请求失败（包含 `status_code` 属性） |

## 代理使用

`NPSClient` 和 `NPSCluster` 都接受代理参数，适用于无法直接访问 NPS 服务器的环境：

```python
# HTTP proxy
nps = NPSClient("https://nps.example.com", auth_key="key",
                 proxy="http://127.0.0.1:7890")

# SOCKS5 proxy (requires PySocks: pip install PySocks)
nps = NPSClient("https://nps.example.com", auth_key="key",
                 socks_proxy="localhost:1080")

# Cluster-wide proxy
cluster = NPSCluster("edges.toml", socks_proxy="localhost:1080")
```

!!! warning "警告"
    SOCKS 代理支持会在 `NPSClient` 的生命周期内全局 monkey-patch `socket.socket`。
    请使用上下文管理器（`with` 语句）或调用 `nps.cleanup()` 在完成后恢复原始 socket。
