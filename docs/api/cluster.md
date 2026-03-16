# NPSCluster

`nps_ctl.cluster.NPSCluster` — 多节点 NPS 集群管理器。

## 构造函数

```python
NPSCluster(config_dir: str | Path)
```

从 `config_dir/edges.toml` 加载边缘节点配置，可选从 `config_dir/clients.toml` 加载客户端配置。

## 属性

| 属性               | 类型         | 说明                     |
| ------------------ | ------------ | ------------------------ |
| `edge_names`       | `list[str]`  | 所有已配置边缘节点的名称 |
| `npc_client_names` | `list[str]`  | 所有 NPC 客户端的名称    |

## 边缘节点方法

| 方法                     | 返回类型             | 说明                   |
| ------------------------ | -------------------- | ---------------------- |
| `get_edge(name)`         | `EdgeConfig | None`  | 获取边缘节点配置       |
| `get_client(name)`       | `NPSClient | None`   | 获取边缘节点的 API 客户端 |
| `get_npc_client(name)`   | `NPCClientConfig | None` | 获取 NPC 客户端配置 |

## 数据获取

| 方法                 | 返回类型                         | 说明                     |
| -------------------- | -------------------------------- | ------------------------ |
| `get_all_clients()`  | `dict[str, list[ClientInfo]]`    | 从所有边缘节点获取客户端 |
| `get_all_tunnels()`  | `dict[str, list[TunnelInfo]]`    | 从所有边缘节点获取隧道   |
| `get_all_hosts()`    | `dict[str, list[HostInfo]]`      | 从所有边缘节点获取域名映射 |

## 同步操作

| 方法                                            | 说明                               |
| ------------------------------------------------ | ---------------------------------- |
| `sync_from(source, targets=None, ...)`           | 从源边缘节点同步配置到目标节点     |
| `broadcast_host(client_remark, host, target)`    | 向所有边缘节点添加域名映射         |
