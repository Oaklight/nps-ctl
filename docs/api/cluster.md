# NPSCluster

`nps_ctl.cluster.NPSCluster` — Multi-node NPS cluster manager.

## Constructor

```python
NPSCluster(config_dir: str | Path)
```

Loads edge configurations from `config_dir/edges.toml` and optionally client configurations from `config_dir/clients.toml`.

## Properties

| Property           | Type         | Description                     |
| ------------------ | ------------ | ------------------------------- |
| `edge_names`       | `list[str]`  | Names of all configured edges   |
| `npc_client_names` | `list[str]`  | Names of all NPC clients        |

## Edge Methods

| Method                   | Returns             | Description                       |
| ------------------------ | ------------------- | --------------------------------- |
| `get_edge(name)`         | `EdgeConfig | None` | Get edge configuration            |
| `get_client(name)`       | `NPSClient | None`  | Get API client for an edge        |
| `get_npc_client(name)`   | `NPCClientConfig | None` | Get NPC client config       |

## Data Retrieval

| Method               | Returns                          | Description                  |
| -------------------- | -------------------------------- | ---------------------------- |
| `get_all_clients()`  | `dict[str, list[ClientInfo]]`    | Clients from all edges       |
| `get_all_tunnels()`  | `dict[str, list[TunnelInfo]]`    | Tunnels from all edges       |
| `get_all_hosts()`    | `dict[str, list[HostInfo]]`      | Hosts from all edges         |

## Sync Operations

| Method                                          | Description                              |
| ------------------------------------------------ | ---------------------------------------- |
| `sync_from(source, targets=None, ...)`           | Sync config from source to target edges  |
| `broadcast_host(client_remark, host, target)`    | Add host to all edges                    |
