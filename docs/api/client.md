# NPSClient

`nps_ctl.base.NPSClient` — Single NPS server API client.

## Constructor

```python
NPSClient(
    base_url: str,
    auth_key: str,
    socks_proxy: str | None = None,
    proxy: str | None = None,
    timeout: int = 10,
)
```

| Parameter     | Description                                      |
| ------------- | ------------------------------------------------ |
| `base_url`    | NPS server URL (e.g., `https://nps.example.com`) |
| `auth_key`    | API authentication key                           |
| `socks_proxy` | Optional SOCKS5 proxy (`host:port`)              |
| `proxy`       | Optional HTTP proxy URL                          |
| `timeout`     | Request timeout in seconds (default: 10)         |

## Client Methods

| Method                            | Description             |
| --------------------------------- | ----------------------- |
| `list_clients(search="")`         | List all clients        |
| `add_client(remark, vkey, ...)`   | Add a new client        |
| `edit_client(id, remark, ...)`    | Edit an existing client |
| `del_client(id)`                  | Delete a client         |

## Tunnel Methods

| Method                                        | Description          |
| --------------------------------------------- | -------------------- |
| `list_tunnels(client_id=None, type="")`        | List tunnels         |
| `add_tunnel(client_id, type, port, target)`   | Add a tunnel         |
| `edit_tunnel(id, ...)`                         | Edit a tunnel        |
| `del_tunnel(id)`                               | Delete a tunnel      |

## Host Methods

| Method                                       | Description          |
| -------------------------------------------- | -------------------- |
| `list_hosts()`                               | List host mappings   |
| `add_host(client_id, host, target, ...)`     | Add a host mapping   |
| `edit_host(id, ...)`                         | Edit a host mapping  |
| `del_host(id)`                               | Delete a host mapping|
