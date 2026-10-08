# API 参考

## NPSClient

::: nps_ctl.base.NPSClient

单个 NPS 服务器的 API 客户端。负责处理认证、重试和 HTTP 通信。领域相关操作位于独立模块中（`nps_ctl.client_mgmt`、`nps_ctl.host`、`nps_ctl.tunnel`），这些模块的函数以 `NPSClient` 实例作为第一个参数。

`NPSClient` 是一个 `@dataclass`。

### 构造函数

```python
NPSClient(
    base_url: str,
    auth_key: str = "",
    timeout: int = 30,
    verify_ssl: bool = True,
    max_retries: int = 3,
    retry_backoff: float = 1.0,
    proxy: str | None = None,
    socks_proxy: str | None = None,
    username: str = "",
    password: str = "",
    platform_token: str = "",
    api_mode: str = "auto",
)
```

| 参数 | 类型 | 默认值 | 描述 |
|------|------|--------|------|
| `base_url` | `str` | *（必填）* | NPS 服务器 URL（例如 `https://nps.example.com:8024`） |
| `auth_key` | `str` | `""` | 旧版 API 认证密钥（来自 `nps.conf`） |
| `timeout` | `int` | `30` | 请求超时时间（秒） |
| `verify_ssl` | `bool` | `True` | 是否验证 SSL 证书 |
| `max_retries` | `int` | `3` | 每个请求的最大重试次数 |
| `retry_backoff` | `float` | `1.0` | 基础退避间隔（秒），每次重试翻倍 |
| `proxy` | `str \| None` | `None` | HTTP/HTTPS 代理 URL |
| `socks_proxy` | `str \| None` | `None` | SOCKS5 代理地址（`host:port`） |
| `username` | `str` | `""` | 新版 API 认证用户名（v0.35.0+） |
| `password` | `str` | `""` | 新版 API 认证密码（v0.35.0+） |
| `platform_token` | `str` | `""` | 新版 API 静态平台令牌（v0.35.0+） |
| `api_mode` | `str` | `"auto"` | API 模式：`"legacy"`、`"modern"` 或 `"auto"` |

### 方法

| 方法 | 描述 |
|------|------|
| `request(endpoint, method="GET", data=None)` | 发起经过认证的旧版 API 请求。返回解析后的 JSON `dict`。 |
| `api_request(method, endpoint, data=None, params=None)` | 发起经过认证的新版 API 请求（JSON 请求体）。返回解析后的 JSON `dict`。 |
| `cleanup()` | 如果使用了 SOCKS 代理，则恢复原始 socket。通过上下文管理器自动调用。 |
| `is_modern` | 属性。如果服务器支持新版 `/api/*` 管理 API，则返回 `True`。 |

---

## 领域模块

### nps_ctl.client_mgmt

NPC 客户端管理函数。

#### list_clients

```python
list_clients(
    nps: NPSClient,
    search: str = "",
    order: str = "asc",
    offset: int = 0,
    limit: int = 100,
) -> list[ClientInfo]
```

列出 NPS 服务器上的所有客户端。

| 参数 | 类型 | 默认值 | 描述 |
|------|------|--------|------|
| `nps` | `NPSClient` | *（必填）* | API 客户端实例 |
| `search` | `str` | `""` | 过滤搜索关键词 |
| `order` | `str` | `"asc"` | 排序方式（`"asc"` 或 `"desc"`） |
| `offset` | `int` | `0` | 分页偏移量 |
| `limit` | `int` | `100` | 最大返回数量 |

**返回值：** `list[ClientInfo]`

#### get_client

```python
get_client(nps: NPSClient, client_id: int) -> ClientInfo | None
```

通过数字 ID 获取单个客户端。未找到时返回 `None`。

#### add_client

```python
add_client(
    nps: NPSClient,
    remark: str,
    vkey: str = "",
    basic_username: str = "",
    basic_password: str = "",
    rate_limit: int = 0,
    max_conn: int = 0,
    web_username: str = "",
    web_password: str = "",
) -> bool
```

添加新的 NPC 客户端。

| 参数 | 类型 | 默认值 | 描述 |
|------|------|--------|------|
| `nps` | `NPSClient` | *（必填）* | API 客户端实例 |
| `remark` | `str` | *（必填）* | 客户端备注/名称 |
| `vkey` | `str` | `""` | 唯一验证密钥（为空时自动生成） |
| `basic_username` | `str` | `""` | HTTP Basic Auth 用户名 |
| `basic_password` | `str` | `""` | HTTP Basic Auth 密码 |
| `rate_limit` | `int` | `0` | 速率限制（KB/s，0 = 不限） |
| `max_conn` | `int` | `0` | 最大连接数（0 = 不限） |
| `web_username` | `str` | `""` | Web 界面用户名 |
| `web_password` | `str` | `""` | Web 界面密码 |

**返回值：** 成功时返回 `True`。

#### edit_client

```python
edit_client(
    nps: NPSClient,
    client_id: int,
    remark: str,
    vkey: str = "",
    basic_username: str = "",
    basic_password: str = "",
    rate_limit: int = 0,
    max_conn: int = 0,
    web_username: str = "",
    web_password: str = "",
) -> bool
```

编辑已有客户端。参数与 `add_client` 相同，外加 `client_id`。

**返回值：** 成功时返回 `True`。

#### del_client

```python
del_client(nps: NPSClient, client_id: int) -> bool
```

通过数字 ID 删除客户端。

**返回值：** 成功时返回 `True`。

---

### nps_ctl.host

主机（域名）映射管理函数。

#### list_hosts

```python
list_hosts(
    nps: NPSClient,
    client_id: int | None = None,
    search: str = "",
    offset: int = 0,
    limit: int = 100,
) -> list[HostInfo]
```

列出所有主机映射。可选按 `client_id` 过滤。

| 参数 | 类型 | 默认值 | 描述 |
|------|------|--------|------|
| `nps` | `NPSClient` | *（必填）* | API 客户端实例 |
| `client_id` | `int \| None` | `None` | 按客户端 ID 过滤（`None` 表示全部） |
| `search` | `str` | `""` | 搜索关键词 |
| `offset` | `int` | `0` | 分页偏移量 |
| `limit` | `int` | `100` | 最大返回数量 |

**返回值：** `list[HostInfo]`

#### get_host

```python
get_host(nps: NPSClient, host_id: int) -> HostInfo | None
```

通过数字 ID 获取单个主机。未找到时返回 `None`。

#### add_host

```python
add_host(
    nps: NPSClient,
    client_id: int,
    host: str,
    target: str,
    remark: str = "",
    location: str = "",
    scheme: str = "all",
    header_change: str = "",
    host_change: str = "",
    auth: str = "",
) -> bool
```

添加新的主机映射。

| 参数 | 类型 | 默认值 | 描述 |
|------|------|--------|------|
| `nps` | `NPSClient` | *（必填）* | API 客户端实例 |
| `client_id` | `int` | *（必填）* | NPC 客户端 ID |
| `host` | `str` | *（必填）* | 域名（例如 `app.example.com`） |
| `target` | `str` | *（必填）* | 目标地址（例如 `127.0.0.1:8080`） |
| `remark` | `str` | `""` | 主机备注 |
| `location` | `str` | `""` | URL 路径前缀（例如 `/api`） |
| `scheme` | `str` | `"all"` | URL 协议：`"http"`、`"https"` 或 `"all"` |
| `header_change` | `str` | `""` | 请求头修改规则 |
| `host_change` | `str` | `""` | Host 头修改 |
| `auth` | `str` | `""` | HTTP Basic Auth（`"user1=pass1\nuser2=pass2"`） |

**返回值：** 成功时返回 `True`。

#### edit_host

```python
edit_host(
    nps: NPSClient,
    host_id: int,
    client_id: int,
    host: str,
    target: str,
    remark: str = "",
    location: str = "",
    scheme: str = "all",
    header_change: str = "",
    host_change: str = "",
    auth: str = "",
) -> bool
```

编辑已有的主机映射。参数与 `add_host` 相同，外加 `host_id`。

**返回值：** 成功时返回 `True`。

#### del_host

```python
del_host(nps: NPSClient, host_id: int) -> bool
```

通过数字 ID 删除主机映射。

**返回值：** 成功时返回 `True`。

---

### nps_ctl.tunnel

隧道管理函数。

#### list_tunnels

```python
list_tunnels(
    nps: NPSClient,
    client_id: int | None = None,
    tunnel_type: str = "",
    search: str = "",
    offset: int = 0,
    limit: int = 100,
) -> list[TunnelInfo]
```

列出隧道。当 `tunnel_type` 为空时，查询所有已知类型（`tcp`、`udp`、`socks5`、`httpProxy`、`secret`、`p2p`、`file`）并合并结果。

| 参数 | 类型 | 默认值 | 描述 |
|------|------|--------|------|
| `nps` | `NPSClient` | *（必填）* | API 客户端实例 |
| `client_id` | `int \| None` | `None` | 按客户端 ID 过滤（`None` 表示全部） |
| `tunnel_type` | `str` | `""` | 按类型过滤（空 = 所有类型） |
| `search` | `str` | `""` | 搜索关键词 |
| `offset` | `int` | `0` | 分页偏移量 |
| `limit` | `int` | `100` | 每种类型的最大返回数量 |

**返回值：** `list[TunnelInfo]`

#### get_tunnel

```python
get_tunnel(nps: NPSClient, tunnel_id: int) -> TunnelInfo | None
```

通过数字 ID 获取单个隧道。未找到时返回 `None`。

#### add_tunnel

```python
add_tunnel(
    nps: NPSClient,
    client_id: int,
    tunnel_type: str,
    port: int = 0,
    target: str = "",
    remark: str = "",
    password: str = "",
    server_ip: str = "",
    flow_limit: str = "",
    time_limit: str = "",
    local_proxy: int = 0,
    local_path: str = "",
    strip_pre: str = "",
) -> bool
```

添加新隧道。

| 参数 | 类型 | 默认值 | 描述 |
|------|------|--------|------|
| `nps` | `NPSClient` | *（必填）* | API 客户端实例 |
| `client_id` | `int` | *（必填）* | NPC 客户端 ID |
| `tunnel_type` | `str` | *（必填）* | 类型：`"tcp"`、`"udp"`、`"socks5"`、`"httpProxy"`、`"secret"`、`"p2p"`、`"file"` |
| `port` | `int` | `0` | 服务器端口（0 或负数表示自动分配） |
| `target` | `str` | `""` | 目标地址（例如 `127.0.0.1:8080`）。多个目标用换行符分隔。 |
| `remark` | `str` | `""` | 隧道备注 |
| `password` | `str` | `""` | 隧道密码（用于 socks5/httpProxy） |
| `server_ip` | `str` | `""` | 服务器 IP 地址 |
| `flow_limit` | `str` | `""` | 流量限制（MB，空 = 不限） |
| `time_limit` | `str` | `""` | 时间限制（空 = 不限） |
| `local_proxy` | `int` | `0` | 启用本地代理（0=否，1=是） |
| `local_path` | `str` | `""` | 本地路径（用于文件服务） |
| `strip_pre` | `str` | `""` | URL 前缀剥离 |

**返回值：** 成功时返回 `True`。

#### edit_tunnel

```python
edit_tunnel(
    nps: NPSClient,
    tunnel_id: int,
    client_id: int,
    tunnel_type: str,
    port: int = 0,
    target: str = "",
    remark: str = "",
    password: str = "",
    server_ip: str = "",
    flow_limit: str = "",
    time_limit: str = "",
    local_proxy: int = 0,
    local_path: str = "",
    strip_pre: str = "",
) -> bool
```

编辑已有隧道。参数与 `add_tunnel` 相同，外加 `tunnel_id`。

**返回值：** 成功时返回 `True`。

#### del_tunnel

```python
del_tunnel(nps: NPSClient, tunnel_id: int) -> bool
```

通过数字 ID 删除隧道。

**返回值：** 成功时返回 `True`。

#### start_tunnel

```python
start_tunnel(nps: NPSClient, tunnel_id: int) -> bool
```

启动已停止的隧道。

#### stop_tunnel

```python
stop_tunnel(nps: NPSClient, tunnel_id: int) -> bool
```

停止运行中的隧道。

---

## NPSCluster

多个 NPS 边缘节点的管理器。从 TOML 文件加载配置，提供批量查询和广播操作。

### 构造函数

```python
NPSCluster(
    config_path: str | Path,
    proxy: str | None = None,
    socks_proxy: str | None = None,
)
```

| 参数 | 类型 | 默认值 | 描述 |
|------|------|--------|------|
| `config_path` | `str \| Path` | *（必填）* | `edges.toml` 配置文件路径 |
| `proxy` | `str \| None` | `None` | 应用于所有边缘节点的 HTTP/HTTPS 代理 URL |
| `socks_proxy` | `str \| None` | `None` | 应用于所有边缘节点的 SOCKS5 代理地址 |

### 属性

| 属性 | 类型 | 描述 |
|------|------|------|
| `edge_names` | `list[str]` | 所有已配置边缘节点的名称 |
| `npc_client_names` | `list[str]` | 所有已配置 NPC 客户端的名称 |

### 方法

#### get_edge

```python
get_edge(name: str) -> EdgeConfig | None
```

按名称获取边缘节点配置。

#### get_client

```python
get_client(name: str) -> NPSClient | None
```

获取指定边缘节点的 `NPSClient` 实例。

#### get_all_clients

```python
get_all_clients(max_workers: int = 4) -> dict[str, list[ClientInfo]]
```

并行获取所有边缘节点的客户端。返回以边缘节点名称为键的字典。

#### get_all_tunnels

```python
get_all_tunnels(max_workers: int = 4) -> dict[str, list[TunnelInfo]]
```

并行获取所有边缘节点的隧道。

#### get_all_hosts

```python
get_all_hosts(max_workers: int = 4) -> dict[str, list[HostInfo]]
```

并行获取所有边缘节点的主机映射。

#### broadcast_client

```python
broadcast_client(
    remark: str,
    vkey: str = "",
    **kwargs,
) -> dict[str, bool]
```

向所有边缘节点添加客户端。返回 `{边缘节点名称: 是否成功}`。

#### broadcast_host

```python
broadcast_host(
    client_remark: str,
    host_domain: str,
    target: str,
    **kwargs,
) -> dict[str, bool]
```

向所有边缘节点添加主机映射。在每个边缘节点上通过备注查找客户端。返回 `{边缘节点名称: 是否成功}`。

#### broadcast_tunnel

```python
broadcast_tunnel(
    client_remark: str,
    tunnel_type: str,
    port: int = 0,
    target: str = "",
    remark: str = "",
    **kwargs,
) -> dict[str, bool]
```

向所有边缘节点添加隧道。在每个边缘节点上通过备注查找客户端。返回 `{边缘节点名称: 是否成功}`。

#### sync_from

```python
sync_from(
    source_name: str,
    sync_clients: bool = True,
    sync_tunnels: bool = True,
    sync_hosts: bool = True,
    target_edges: list[str] | None = None,
    show_progress: bool = False,
    max_workers: int = 4,
    parallel: bool = False,
    quiet: bool = False,
) -> dict[str, dict[str, bool]]
```

将配置从一个边缘节点同步到所有其他节点（或指定的目标节点）。

| 参数 | 类型 | 默认值 | 描述 |
|------|------|--------|------|
| `source_name` | `str` | *（必填）* | 源边缘节点名称 |
| `sync_clients` | `bool` | `True` | 同步客户端条目 |
| `sync_tunnels` | `bool` | `True` | 同步隧道条目 |
| `sync_hosts` | `bool` | `True` | 同步主机映射 |
| `target_edges` | `list[str] \| None` | `None` | 目标边缘节点（`None` = 所有其他节点） |
| `show_progress` | `bool` | `False` | 显示进度条 |
| `max_workers` | `int` | `4` | 处理条目的并行工作线程数 |
| `parallel` | `bool` | `False` | 并行同步到各边缘节点 |
| `quiet` | `bool` | `False` | 抑制进度输出 |

**返回值：** `{目标边缘节点: {操作: 是否成功}}`

#### cleanup

```python
cleanup() -> None
```

清理所有 `NPSClient` 实例。通过上下文管理器自动调用。

---

## 数据类型

### ClientInfo

`TypedDict`（通过 `total=False` 使所有键可选）。

| 键 | 类型 | 描述 |
|----|------|------|
| `Id` | `int` | 客户端 ID |
| `VerifyKey` | `str` | 验证密钥 |
| `Addr` | `str` | 客户端地址 |
| `Remark` | `str` | 客户端名称/备注 |
| `Status` | `bool` | 启用状态 |
| `IsConnect` | `bool` | 当前是否已连接 |
| `RateLimit` | `int` | 速率限制（KB/s） |
| `MaxConn` | `int` | 最大连接数 |
| `NowConn` | `int` | 当前连接数 |
| `Flow` | `dict` | 流量数据 |
| `WebUserName` | `str` | Web 界面用户名 |
| `WebPassword` | `str` | Web 界面密码 |
| `ConfigConnAllow` | `bool` | 是否允许连接 |
| `Cnf` | `dict` | 附加配置 |

### TunnelInfo

`TypedDict`（通过 `total=False` 使所有键可选）。

| 键 | 类型 | 描述 |
|----|------|------|
| `Id` | `int` | 隧道 ID |
| `Port` | `int` | 服务器端口 |
| `ServerIp` | `str` | 服务器 IP |
| `Mode` | `str` | 隧道类型/模式 |
| `Status` | `bool` | 启用状态 |
| `RunStatus` | `bool` | 当前是否运行中 |
| `Client` | `ClientInfo` | 关联的客户端 |
| `Ports` | `str` | 端口范围 |
| `Flow` | `dict` | 流量数据 |
| `Password` | `str` | 隧道密码 |
| `Remark` | `str` | 隧道备注 |
| `TargetAddr` | `str` | 目标地址 |
| `NoStore` | `bool` | 无存储标志 |
| `LocalPath` | `str` | 本地文件路径 |
| `StripPre` | `str` | URL 前缀剥离 |
| `Target` | `dict` | 目标详情 |

### HostInfo

`TypedDict`（通过 `total=False` 使所有键可选）。

| 键 | 类型 | 描述 |
|----|------|------|
| `Id` | `int` | 主机 ID |
| `Host` | `str` | 域名 |
| `HeaderChange` | `str` | 请求头修改规则 |
| `HostChange` | `str` | Host 头修改 |
| `Location` | `str` | URL 路径前缀 |
| `Remark` | `str` | 主机备注 |
| `Scheme` | `str` | URL 协议 |
| `CertFilePath` | `str` | TLS 证书路径 |
| `KeyFilePath` | `str` | TLS 密钥路径 |
| `NoStore` | `bool` | 无存储标志 |
| `IsClose` | `bool` | 已关闭/已禁用 |
| `Flow` | `dict` | 流量数据 |
| `Client` | `ClientInfo` | 关联的客户端 |
| `Target` | `dict` | 目标详情 |
| `AutoHttps` | `bool` | 自动 HTTPS 重定向 |

### EdgeConfig

`@dataclass`，表示单个 NPS 边缘节点的配置。

| 字段 | 类型 | 默认值 | 描述 |
|------|------|--------|------|
| `name` | `str` | *（必填）* | 边缘节点名称 |
| `api_url` | `str` | *（必填）* | NPS API URL |
| `auth_key` | `str` | `""` | 旧版认证密钥 |
| `region` | `str` | `""` | 地理区域 |
| `ssh_host` | `str` | `""` | 用于部署的 SSH 主机 |
| `username` | `str` | `""` | 新版 API 用户名 |
| `password` | `str` | `""` | 新版 API 密码 |
| `platform_token` | `str` | `""` | 新版 API 平台令牌 |
| `api_mode` | `str` | `"auto"` | `"legacy"`、`"modern"` 或 `"auto"` |

### NPCClientConfig

`@dataclass`，表示 NPC 客户端的部署配置。

| 字段 | 类型 | 默认值 | 描述 |
|------|------|--------|------|
| `name` | `str` | *（必填）* | 客户端名称 |
| `ssh_host` | `str` | *（必填）* | 用于部署的 SSH 主机 |
| `edges` | `list[str]` | *（必填）* | 该客户端连接的边缘节点名称 |
| `vkey` | `str` | `""` | 验证密钥 |
| `remark` | `str` | `""` | 备注（默认为 `name`） |
| `conn_type` | `str` | `"tls"` | 连接类型：`"tls"`、`"tcp"`、`"kcp"` |
| `ssh_user` | `str` | `""` | SSH 用户名 |
| `http_proxy` | `str` | `""` | NPC 使用的 HTTP 代理 |

---

## 异常

所有异常定义在 `nps_ctl.exceptions` 中。

| 异常 | 父类 | 描述 |
|------|------|------|
| `NPSError` | `Exception` | 所有 NPS 错误的基类 |
| `NPSAuthError` | `NPSError` | 认证失败（错误的认证密钥、无法访问服务器时间端点） |
| `NPSAPIError` | `NPSError` | API 请求失败。包含 `status_code: int | None` 属性。 |
