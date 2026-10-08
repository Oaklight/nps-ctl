# Configuration

nps-ctl reads its configuration from TOML files. The primary config file is `edges.toml`, which defines all NPS edge nodes and shared settings. An optional `clients.toml` in the same directory defines NPC client machines for deployment.

## Config file location

nps-ctl searches for `edges.toml` in the following order:

1. `./config/edges.toml` (project-local)
2. `~/.config/nps-ctl/edges.toml` (user config)
3. `/etc/nps-ctl/edges.toml` (system-wide)

To use a custom path:

```bash
nps-ctl --config /path/to/edges.toml edge status
```

## edges.toml

The config file uses TOML's `[[edges]]` array-of-tables syntax. Each `[[edges]]` block defines one NPS edge node.

### Minimal example

A working config with two edges and legacy API authentication:

```toml
auth_crypt_key = "1234567890abcdef"
public_vkey = "my-public-vkey"

[web]
username = "admin"
password = "s3cret"

[[edges]]
name = "nps-us"
api_url = "https://nps-us.example.com"
auth_key = "your_auth_key_here"
region = "US"
ssh_host = "cloud.usa1"

[[edges]]
name = "nps-asia"
api_url = "https://nps-asia.example.com"
auth_key = "your_auth_key_here"
region = "Asia"
ssh_host = "cloud.jpn1"
```

### Full example

All available fields with their defaults:

```toml
# AES encryption key for NPS auth, exactly 16 characters.
# Shared across all edges — must match nps.conf on each server.
auth_crypt_key = "1234567890abcdef"

# Public verification key for client registration.
public_vkey = "my-public-vkey"

# Web UI credentials, shared across all edges.
[web]
username = "admin"
password = "s3cret"

# Port configuration (optional, defaults shown).
[ports]
http_proxy = 30080    # NPS HTTP reverse proxy port
bridge_tcp = 51234    # NPC ↔ NPS bridge (TCP)
bridge_tls = 51235    # NPC ↔ NPS bridge (TLS)
web = 25412           # NPS web management UI port

# Edge definitions — one [[edges]] block per NPS server node.
[[edges]]
name = "nps-us"                            # Required: unique identifier
api_url = "https://nps-us.example.com"     # Required: NPS server URL
auth_key = "your_auth_key_here"            # Legacy API auth key
region = "US"                              # Human-readable region label
ssh_host = "cloud.usa1"                    # SSH host for deploy commands

# Modern API fields (v0.35.0+, optional)
username = ""              # Web login username
password = ""              # Web login password
platform_token = ""        # Platform API token
api_mode = "auto"          # "legacy", "modern", or "auto" (probe server)

[[edges]]
name = "nps-asia"
api_url = "https://nps-asia.example.com"
auth_key = "your_auth_key_here"
region = "Asia"
ssh_host = "cloud.jpn1"
```

### Top-level fields

| Field | Type | Description |
|-------|------|-------------|
| `auth_crypt_key` | string | AES encryption key (16 characters). Must match `nps.conf` on all edges. |
| `public_vkey` | string | Public registration key for NPC clients. |

### `[web]` section

| Field | Default | Description |
|-------|---------|-------------|
| `username` | `"admin"` | Web UI login username, shared across edges. |
| `password` | `"admin"` | Web UI login password, shared across edges. |

### `[ports]` section

All ports are optional and default to standard NPS values. These are used when deploying NPS via `edge install` or `edge reconfig`.

| Field | Default | Description |
|-------|---------|-------------|
| `http_proxy` | `30080` | HTTP reverse proxy port. |
| `bridge_tcp` | `51234` | NPC-to-NPS bridge port (TCP). |
| `bridge_tls` | `51235` | NPC-to-NPS bridge port (TLS). |
| `web` | `25412` | Web management UI port. |

### `[[edges]]` entries

| Field | Required | Default | Description |
|-------|----------|---------|-------------|
| `name` | Yes | — | Unique edge identifier (used in `-e` flags). |
| `api_url` | Yes | — | NPS server URL (e.g., `https://nps-us.example.com`). |
| `auth_key` | No | `""` | API authentication key (legacy API). |
| `region` | No | `""` | Human-readable region label. |
| `ssh_host` | No | `""` | SSH host alias for deployment commands. |
| `username` | No | `""` | Web login username (modern API, v0.35.0+). |
| `password` | No | `""` | Web login password (modern API, v0.35.0+). |
| `platform_token` | No | `""` | Platform API token (modern API, v0.35.0+). |
| `api_mode` | No | `"auto"` | API mode: `"legacy"`, `"modern"`, or `"auto"`. |

!!! tip "Legacy vs. modern API"
    When `api_mode` is `"auto"` (the default), nps-ctl probes the server to determine which API is available. Set it explicitly if you know your NPS version: `"legacy"` for older versions using `auth_key`, or `"modern"` for v0.35.0+ using `username`/`password` or `platform_token`.

## clients.toml

NPC client definitions can live either as `[[clients]]` entries inside `edges.toml` or in a separate `clients.toml` file in the same directory. If both exist, `clients.toml` takes precedence.

```toml
[[clients]]
name = "my-server"
ssh_host = "10.0.0.5"
vkey = "unique-verify-key"
edges = ["nps-us", "nps-asia"]
remark = "My backend server"
conn_type = "tls"
ssh_user = "root"
http_proxy = ""

[[clients]]
name = "home-nas"
ssh_host = "oaklight.oasis"
vkey = "another-verify-key"
edges = ["nps-us", "nps-asia"]
```

### `[[clients]]` entries

| Field | Required | Default | Description |
|-------|----------|---------|-------------|
| `name` | Yes | — | Client identifier (used in `-c` flags). |
| `ssh_host` | Yes | — | SSH host for NPC deployment. |
| `edges` | No | `[]` | List of edge names this client connects to. |
| `vkey` | No | `""` | Verification key (auto-generated if empty). |
| `remark` | No | Same as `name` | Human-readable label shown in NPS web UI. |
| `conn_type` | No | `"tls"` | Bridge connection type: `"tls"`, `"tcp"`, or `"kcp"`. |
| `ssh_user` | No | `""` | SSH login user (overrides SSH config default). |
| `http_proxy` | No | `""` | HTTP proxy for NPC binary download during install. |

## Proxy configuration

nps-ctl supports routing API requests through a proxy when edges are not directly reachable.

```bash
# HTTP proxy
nps-ctl --proxy http://127.0.0.1:8080 edge status

# SOCKS5 proxy (requires PySocks: pip install PySocks)
nps-ctl --socks-proxy 127.0.0.1:1080 edge status

# Auto-create an SSH SOCKS tunnel through a jump host
nps-ctl --auto-proxy jump-host edge status
```

| Flag | Description |
|------|-------------|
| `--proxy URL` | Route API requests through an HTTP proxy. |
| `--socks-proxy HOST:PORT` | Route API requests through a SOCKS5 proxy. |
| `--auto-proxy HOST` | Automatically create an SSH SOCKS tunnel via the specified host. |

!!! note
    `--auto-proxy` starts a background SSH tunnel that is cleaned up when the command finishes. It is useful when your edges are only reachable from a specific jump host.
