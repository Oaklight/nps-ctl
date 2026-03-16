# Library Usage

## NPSClient — Single Server

```python
from nps_ctl import NPSClient

client = NPSClient(
    base_url="https://nps.example.com",
    auth_key="your_auth_key"
)

# List all clients
clients = client.list_clients()
for c in clients:
    print(f"{c['Id']}: {c['VerifyKey']} ({c.get('Remark', '')})")

# Add a new client
client.add_client(remark="my-server", vkey="unique-key")

# List tunnels
tunnels = client.list_tunnels()

# Add a host mapping
client.add_host(client_id=1, host="app.example.com", target=":8080")
```

## NPSCluster — Multi-node

```python
from nps_ctl.cluster import NPSCluster

cluster = NPSCluster("config/")

# Get clients from all edges
all_clients = cluster.get_all_clients()
for edge_name, clients in all_clients.items():
    print(f"--- {edge_name} ---")
    for c in clients:
        print(f"  {c['Remark']}: {c['VerifyKey']}")

# Sync from one edge to all others
cluster.sync_from("nps-asia")

# Add a host to all edges
cluster.broadcast_host(
    client_remark="my-server",
    host_domain="app.example.com",
    target=":8080"
)
```

## SOCKS5 Proxy

```python
client = NPSClient(
    base_url="https://nps.example.com",
    auth_key="your_auth_key",
    socks_proxy="127.0.0.1:1080"
)
```
