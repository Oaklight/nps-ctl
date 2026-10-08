# Python Library

nps-ctl can be used as a Python library for programmatic NPS management.
This is useful for automation scripts, custom dashboards, or integrating
NPS operations into larger infrastructure tooling.

## NPSClient

`NPSClient` handles authenticated communication with a single NPS server.
Domain-specific operations live in separate modules that accept an
`NPSClient` instance as the first argument.

### Initialization

```python
from nps_ctl import NPSClient

nps = NPSClient("https://nps.example.com:8024", auth_key="your_auth_key")
```

!!! note
    `NPSClient` is a dataclass. All parameters beyond `base_url` are optional
    keyword arguments. See the [API Reference](../reference/api.md#npsclient)
    for the full parameter list.

### Client management

```python
from nps_ctl.client_mgmt import list_clients, add_client, del_client

# List all registered NPC clients
clients = list_clients(nps)
for c in clients:
    print(f"{c['Id']}: {c['Remark']} (connected={c['IsConnect']})")

# Add a new client
add_client(nps, remark="my-server", vkey="unique-key-123")
```

`list_clients` returns `list[ClientInfo]`. Each `ClientInfo` is a `TypedDict`
with keys like `Id`, `Remark`, `VerifyKey`, `Status`, `IsConnect`, `Addr`,
`RateLimit`, `MaxConn`, and `NowConn`.

### Host management

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

### Tunnel management

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

`NPSCluster` manages multiple NPS edge nodes from a single TOML config file.
It provides bulk queries and broadcast operations across all edges.

### Initialization

```python
from nps_ctl import NPSCluster

cluster = NPSCluster("~/.config/nps-ctl/edges.toml")
```

`NPSCluster` supports context manager usage to ensure proper cleanup of
SOCKS proxy connections:

```python
with NPSCluster("~/.config/nps-ctl/edges.toml") as cluster:
    clients = cluster.get_all_clients()
    # ... work with the cluster
```

### Querying all edges

`get_all_clients`, `get_all_tunnels`, and `get_all_hosts` fetch data from
every edge in parallel and return a dictionary keyed by edge name:

```python
# Returns dict[str, list[ClientInfo]]
all_clients = cluster.get_all_clients(max_workers=4)
for edge_name, clients in all_clients.items():
    print(f"{edge_name}: {len(clients)} clients")

# Same pattern for tunnels and hosts
all_hosts = cluster.get_all_hosts()
```

### Broadcasting operations

Broadcast methods apply the same operation to every edge:

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

### Syncing configuration

`sync_from` replicates clients, tunnels, and hosts from one edge to all
others:

```python
results = cluster.sync_from(
    source_name="nps-america",
    sync_clients=True,
    sync_tunnels=True,
    sync_hosts=True,
)
```

### Edge and client introspection

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

## Error handling

All API errors inherit from `NPSError`:

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

| Exception | When raised |
|-----------|-------------|
| `NPSError` | Base class for all NPS errors |
| `NPSAuthError` | Authentication or server-time retrieval failure |
| `NPSAPIError` | API request failure (has `status_code` attribute) |

## Proxy usage

Both `NPSClient` and `NPSCluster` accept proxy parameters for environments
where the NPS server is not directly reachable:

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

!!! warning
    SOCKS proxy support monkey-patches `socket.socket` globally for the
    lifetime of the `NPSClient`. Use the context manager (`with` statement)
    or call `nps.cleanup()` to restore the original socket when done.
