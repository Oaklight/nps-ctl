# API Reference

## NPSClient

::: nps_ctl.base.NPSClient

API client for a single NPS server. Handles authentication, retries, and
HTTP communication. Domain-specific operations are in separate modules
(`nps_ctl.client_mgmt`, `nps_ctl.host`, `nps_ctl.tunnel`) that take an
`NPSClient` instance as their first argument.

`NPSClient` is a `@dataclass`.

### Constructor

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

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `base_url` | `str` | *(required)* | NPS server URL (e.g. `https://nps.example.com:8024`) |
| `auth_key` | `str` | `""` | Authentication key for legacy API (from `nps.conf`) |
| `timeout` | `int` | `30` | Request timeout in seconds |
| `verify_ssl` | `bool` | `True` | Verify SSL certificates |
| `max_retries` | `int` | `3` | Maximum retry attempts per request |
| `retry_backoff` | `float` | `1.0` | Base backoff interval in seconds (doubles per retry) |
| `proxy` | `str \| None` | `None` | HTTP/HTTPS proxy URL |
| `socks_proxy` | `str \| None` | `None` | SOCKS5 proxy address (`host:port`) |
| `username` | `str` | `""` | Username for modern API auth (v0.35.0+) |
| `password` | `str` | `""` | Password for modern API auth (v0.35.0+) |
| `platform_token` | `str` | `""` | Static platform token for modern API (v0.35.0+) |
| `api_mode` | `str` | `"auto"` | API mode: `"legacy"`, `"modern"`, or `"auto"` |

### Methods

| Method | Description |
|--------|-------------|
| `request(endpoint, method="GET", data=None)` | Make an authenticated legacy API request. Returns parsed JSON `dict`. |
| `api_request(method, endpoint, data=None, params=None)` | Make an authenticated modern API request (JSON body). Returns parsed JSON `dict`. |
| `cleanup()` | Restore original socket if SOCKS proxy was used. Called automatically via context manager. |
| `is_modern` | Property. `True` if the server supports the modern `/api/*` management API. |

---

## Domain modules

### nps_ctl.client_mgmt

NPC client management functions.

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

List all clients on the NPS server.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `nps` | `NPSClient` | *(required)* | API client instance |
| `search` | `str` | `""` | Search keyword for filtering |
| `order` | `str` | `"asc"` | Sort order (`"asc"` or `"desc"`) |
| `offset` | `int` | `0` | Pagination offset |
| `limit` | `int` | `100` | Maximum number of results |

**Returns:** `list[ClientInfo]`

#### get_client

```python
get_client(nps: NPSClient, client_id: int) -> ClientInfo | None
```

Get a single client by numeric ID. Returns `None` if not found.

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

Add a new NPC client.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `nps` | `NPSClient` | *(required)* | API client instance |
| `remark` | `str` | *(required)* | Client remark/name |
| `vkey` | `str` | `""` | Unique verification key (auto-generated if empty) |
| `basic_username` | `str` | `""` | HTTP basic auth username |
| `basic_password` | `str` | `""` | HTTP basic auth password |
| `rate_limit` | `int` | `0` | Rate limit in KB/s (0 = unlimited) |
| `max_conn` | `int` | `0` | Maximum connections (0 = unlimited) |
| `web_username` | `str` | `""` | Web interface username |
| `web_password` | `str` | `""` | Web interface password |

**Returns:** `True` if successful.

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

Edit an existing client. Same parameters as `add_client` plus `client_id`.

**Returns:** `True` if successful.

#### del_client

```python
del_client(nps: NPSClient, client_id: int) -> bool
```

Delete a client by numeric ID.

**Returns:** `True` if successful.

---

### nps_ctl.host

Host (domain) mapping management functions.

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

List all host mappings. Optionally filter by `client_id`.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `nps` | `NPSClient` | *(required)* | API client instance |
| `client_id` | `int \| None` | `None` | Filter by client ID (`None` for all) |
| `search` | `str` | `""` | Search keyword |
| `offset` | `int` | `0` | Pagination offset |
| `limit` | `int` | `100` | Maximum number of results |

**Returns:** `list[HostInfo]`

#### get_host

```python
get_host(nps: NPSClient, host_id: int) -> HostInfo | None
```

Get a single host by numeric ID. Returns `None` if not found.

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

Add a new host mapping.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `nps` | `NPSClient` | *(required)* | API client instance |
| `client_id` | `int` | *(required)* | NPC client ID |
| `host` | `str` | *(required)* | Domain name (e.g. `app.example.com`) |
| `target` | `str` | *(required)* | Target address (e.g. `127.0.0.1:8080`) |
| `remark` | `str` | `""` | Host remark |
| `location` | `str` | `""` | URL path prefix (e.g. `/api`) |
| `scheme` | `str` | `"all"` | URL scheme: `"http"`, `"https"`, or `"all"` |
| `header_change` | `str` | `""` | Header modification rules |
| `host_change` | `str` | `""` | Host header modification |
| `auth` | `str` | `""` | HTTP Basic Auth (`"user1=pass1\nuser2=pass2"`) |

**Returns:** `True` if successful.

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

Edit an existing host mapping. Same parameters as `add_host` plus `host_id`.

**Returns:** `True` if successful.

#### del_host

```python
del_host(nps: NPSClient, host_id: int) -> bool
```

Delete a host mapping by numeric ID.

**Returns:** `True` if successful.

---

### nps_ctl.tunnel

Tunnel management functions.

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

List tunnels. When `tunnel_type` is empty, queries all known types
(`tcp`, `udp`, `socks5`, `httpProxy`, `secret`, `p2p`, `file`) and merges
the results.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `nps` | `NPSClient` | *(required)* | API client instance |
| `client_id` | `int \| None` | `None` | Filter by client ID (`None` for all) |
| `tunnel_type` | `str` | `""` | Filter by type (empty = all types) |
| `search` | `str` | `""` | Search keyword |
| `offset` | `int` | `0` | Pagination offset |
| `limit` | `int` | `100` | Maximum number of results per type |

**Returns:** `list[TunnelInfo]`

#### get_tunnel

```python
get_tunnel(nps: NPSClient, tunnel_id: int) -> TunnelInfo | None
```

Get a single tunnel by numeric ID. Returns `None` if not found.

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

Add a new tunnel.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `nps` | `NPSClient` | *(required)* | API client instance |
| `client_id` | `int` | *(required)* | NPC client ID |
| `tunnel_type` | `str` | *(required)* | Type: `"tcp"`, `"udp"`, `"socks5"`, `"httpProxy"`, `"secret"`, `"p2p"`, `"file"` |
| `port` | `int` | `0` | Server port (0 or negative for auto-assign) |
| `target` | `str` | `""` | Target address (e.g. `127.0.0.1:8080`). Multiple targets separated by newlines. |
| `remark` | `str` | `""` | Tunnel remark |
| `password` | `str` | `""` | Tunnel password (for socks5/httpProxy) |
| `server_ip` | `str` | `""` | Server IP address |
| `flow_limit` | `str` | `""` | Flow limit in MB (empty = unlimited) |
| `time_limit` | `str` | `""` | Time limit (empty = unlimited) |
| `local_proxy` | `int` | `0` | Enable local proxy (0=no, 1=yes) |
| `local_path` | `str` | `""` | Local path (for file service) |
| `strip_pre` | `str` | `""` | URL prefix stripping |

**Returns:** `True` if successful.

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

Edit an existing tunnel. Same parameters as `add_tunnel` plus `tunnel_id`.

**Returns:** `True` if successful.

#### del_tunnel

```python
del_tunnel(nps: NPSClient, tunnel_id: int) -> bool
```

Delete a tunnel by numeric ID.

**Returns:** `True` if successful.

#### start_tunnel

```python
start_tunnel(nps: NPSClient, tunnel_id: int) -> bool
```

Start a stopped tunnel.

#### stop_tunnel

```python
stop_tunnel(nps: NPSClient, tunnel_id: int) -> bool
```

Stop a running tunnel.

---

## NPSCluster

Manager for multiple NPS edge nodes. Loads configuration from a TOML file
and provides bulk query and broadcast operations.

### Constructor

```python
NPSCluster(
    config_path: str | Path,
    proxy: str | None = None,
    socks_proxy: str | None = None,
)
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `config_path` | `str \| Path` | *(required)* | Path to `edges.toml` configuration file |
| `proxy` | `str \| None` | `None` | HTTP/HTTPS proxy URL applied to all edges |
| `socks_proxy` | `str \| None` | `None` | SOCKS5 proxy address applied to all edges |

### Properties

| Property | Type | Description |
|----------|------|-------------|
| `edge_names` | `list[str]` | Names of all configured edges |
| `npc_client_names` | `list[str]` | Names of all configured NPC clients |

### Methods

#### get_edge

```python
get_edge(name: str) -> EdgeConfig | None
```

Get edge configuration by name.

#### get_client

```python
get_client(name: str) -> NPSClient | None
```

Get the `NPSClient` instance for a specific edge.

#### get_all_clients

```python
get_all_clients(max_workers: int = 4) -> dict[str, list[ClientInfo]]
```

Fetch clients from all edges in parallel. Returns a dict keyed by edge name.

#### get_all_tunnels

```python
get_all_tunnels(max_workers: int = 4) -> dict[str, list[TunnelInfo]]
```

Fetch tunnels from all edges in parallel.

#### get_all_hosts

```python
get_all_hosts(max_workers: int = 4) -> dict[str, list[HostInfo]]
```

Fetch hosts from all edges in parallel.

#### broadcast_client

```python
broadcast_client(
    remark: str,
    vkey: str = "",
    **kwargs,
) -> dict[str, bool]
```

Add a client to all edges. Returns `{edge_name: success}`.

#### broadcast_host

```python
broadcast_host(
    client_remark: str,
    host_domain: str,
    target: str,
    **kwargs,
) -> dict[str, bool]
```

Add a host mapping to all edges. Finds the client by remark on each edge.
Returns `{edge_name: success}`.

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

Add a tunnel to all edges. Finds the client by remark on each edge.
Returns `{edge_name: success}`.

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

Sync configuration from one edge to all others (or specific targets).

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `source_name` | `str` | *(required)* | Source edge name |
| `sync_clients` | `bool` | `True` | Sync client entries |
| `sync_tunnels` | `bool` | `True` | Sync tunnel entries |
| `sync_hosts` | `bool` | `True` | Sync host mappings |
| `target_edges` | `list[str] \| None` | `None` | Target edges (`None` = all others) |
| `show_progress` | `bool` | `False` | Show progress bar |
| `max_workers` | `int` | `4` | Parallel workers for items |
| `parallel` | `bool` | `False` | Sync to edges in parallel |
| `quiet` | `bool` | `False` | Suppress progress output |

**Returns:** `{target_edge: {operation: success}}`

#### cleanup

```python
cleanup() -> None
```

Clean up all `NPSClient` instances. Called automatically via context manager.

---

## Data types

### ClientInfo

`TypedDict` (all keys optional via `total=False`).

| Key | Type | Description |
|-----|------|-------------|
| `Id` | `int` | Client ID |
| `VerifyKey` | `str` | Verification key |
| `Addr` | `str` | Client address |
| `Remark` | `str` | Client name/remark |
| `Status` | `bool` | Enabled status |
| `IsConnect` | `bool` | Currently connected |
| `RateLimit` | `int` | Rate limit (KB/s) |
| `MaxConn` | `int` | Maximum connections |
| `NowConn` | `int` | Current connections |
| `Flow` | `dict` | Traffic flow data |
| `WebUserName` | `str` | Web interface username |
| `WebPassword` | `str` | Web interface password |
| `ConfigConnAllow` | `bool` | Connection allowed |
| `Cnf` | `dict` | Additional configuration |

### TunnelInfo

`TypedDict` (all keys optional via `total=False`).

| Key | Type | Description |
|-----|------|-------------|
| `Id` | `int` | Tunnel ID |
| `Port` | `int` | Server port |
| `ServerIp` | `str` | Server IP |
| `Mode` | `str` | Tunnel type/mode |
| `Status` | `bool` | Enabled status |
| `RunStatus` | `bool` | Currently running |
| `Client` | `ClientInfo` | Associated client |
| `Ports` | `str` | Port range |
| `Flow` | `dict` | Traffic flow data |
| `Password` | `str` | Tunnel password |
| `Remark` | `str` | Tunnel remark |
| `TargetAddr` | `str` | Target address |
| `NoStore` | `bool` | No-store flag |
| `LocalPath` | `str` | Local file path |
| `StripPre` | `str` | URL prefix stripping |
| `Target` | `dict` | Target details |

### HostInfo

`TypedDict` (all keys optional via `total=False`).

| Key | Type | Description |
|-----|------|-------------|
| `Id` | `int` | Host ID |
| `Host` | `str` | Domain name |
| `HeaderChange` | `str` | Header modification rules |
| `HostChange` | `str` | Host header modification |
| `Location` | `str` | URL path prefix |
| `Remark` | `str` | Host remark |
| `Scheme` | `str` | URL scheme |
| `CertFilePath` | `str` | TLS certificate path |
| `KeyFilePath` | `str` | TLS key path |
| `NoStore` | `bool` | No-store flag |
| `IsClose` | `bool` | Closed/disabled |
| `Flow` | `dict` | Traffic flow data |
| `Client` | `ClientInfo` | Associated client |
| `Target` | `dict` | Target details |
| `AutoHttps` | `bool` | Auto HTTPS redirect |

### EdgeConfig

`@dataclass` representing a single NPS edge node configuration.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `name` | `str` | *(required)* | Edge name |
| `api_url` | `str` | *(required)* | NPS API URL |
| `auth_key` | `str` | `""` | Legacy auth key |
| `region` | `str` | `""` | Geographic region |
| `ssh_host` | `str` | `""` | SSH host for deployment |
| `username` | `str` | `""` | Modern API username |
| `password` | `str` | `""` | Modern API password |
| `platform_token` | `str` | `""` | Modern API platform token |
| `api_mode` | `str` | `"auto"` | `"legacy"`, `"modern"`, or `"auto"` |

### NPCClientConfig

`@dataclass` representing an NPC client deployment configuration.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `name` | `str` | *(required)* | Client name |
| `ssh_host` | `str` | *(required)* | SSH host for deployment |
| `edges` | `list[str]` | *(required)* | Edge names this client connects to |
| `vkey` | `str` | `""` | Verification key |
| `remark` | `str` | `""` | Remark (defaults to `name`) |
| `conn_type` | `str` | `"tls"` | Connection type: `"tls"`, `"tcp"`, `"kcp"` |
| `ssh_user` | `str` | `""` | SSH username |
| `http_proxy` | `str` | `""` | HTTP proxy for NPC |

---

## Exceptions

All exceptions are defined in `nps_ctl.exceptions`.

| Exception | Parent | Description |
|-----------|--------|-------------|
| `NPSError` | `Exception` | Base class for all NPS errors |
| `NPSAuthError` | `NPSError` | Authentication failure (bad auth key, unreachable server time endpoint) |
| `NPSAPIError` | `NPSError` | API request failure. Has a `status_code: int | None` attribute. |
