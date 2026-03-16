# Configuration

nps-ctl uses TOML configuration files stored in the `config/` directory.

## Edge Nodes — `config/edges.toml`

Define your NPS edge servers:

```toml
[edges.nps-asia]
api_url = "https://nps-asia.example.com"
auth_key = "your_auth_key"
region = "Asia"

[edges.nps-us]
api_url = "https://nps-us.example.com"
auth_key = "your_auth_key"
region = "US"
```

Each edge entry requires:

| Field      | Description                        |
| ---------- | ---------------------------------- |
| `api_url`  | NPS server API URL                 |
| `auth_key` | API authentication key             |
| `region`   | Human-readable region label        |

## NPC Clients — `config/clients.toml`

Define NPC client machines for deployment and management:

```toml
[clients.my-server]
ssh_host = "user@my-server.example.com"
vkey = "unique-verify-key"
edges = ["nps-asia", "nps-us"]
```

Each client entry requires:

| Field      | Description                              |
| ---------- | ---------------------------------------- |
| `ssh_host` | SSH connection string                    |
| `vkey`     | NPS client verify key                    |
| `edges`    | List of edge names this client uses      |

## SOCKS5 Proxy

To route API requests through a SOCKS5 proxy, pass `--socks-proxy` to CLI commands:

```bash
nps-ctl --socks-proxy 127.0.0.1:1080 status
```

Or use `--auto-proxy` to automatically set up an SSH SOCKS tunnel.
