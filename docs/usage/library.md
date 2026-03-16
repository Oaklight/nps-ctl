# 库的使用

## NPSClient — 单服务器

```python
from nps_ctl import NPSClient

client = NPSClient(
    base_url="https://nps.example.com",
    auth_key="your_auth_key"
)

# 列出所有客户端
clients = client.list_clients()
for c in clients:
    print(f"{c['Id']}: {c['VerifyKey']} ({c.get('Remark', '')})")

# 添加新客户端
client.add_client(remark="my-server", vkey="unique-key")

# 列出隧道
tunnels = client.list_tunnels()

# 添加域名映射
client.add_host(client_id=1, host="app.example.com", target=":8080")
```

## NPSCluster — 多节点

```python
from nps_ctl.cluster import NPSCluster

cluster = NPSCluster("config/")

# 从所有边缘节点获取客户端
all_clients = cluster.get_all_clients()
for edge_name, clients in all_clients.items():
    print(f"--- {edge_name} ---")
    for c in clients:
        print(f"  {c['Remark']}: {c['VerifyKey']}")

# 从一个边缘节点同步到其他所有节点
cluster.sync_from("nps-asia")

# 向所有边缘节点添加域名映射
cluster.broadcast_host(
    client_remark="my-server",
    host_domain="app.example.com",
    target=":8080"
)
```

## SOCKS5 代理

```python
client = NPSClient(
    base_url="https://nps.example.com",
    auth_key="your_auth_key",
    socks_proxy="127.0.0.1:1080"
)
```
