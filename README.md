# nps-ctl

A Python library and CLI tool for managing [NPS](https://github.com/ehang-io/nps) (ehang-io/nps) servers.

## Features

- **API Client**: Type-safe Python wrapper for NPS HTTP API
- **Multi-node Support**: Manage multiple NPS servers from a single interface
- **CLI Tool**: Command-line interface for common operations
- **Zero Dependencies**: Uses only Python standard library

## Installation

```bash
pip install nps-ctl
```

## Quick Start

### As a Library

```python
from nps_ctl import NPSClient

# Connect to a single NPS server
client = NPSClient(
    base_url="https://nps.example.com",
    auth_key="your_auth_key"
)

# List all clients
clients = client.list_clients()
for c in clients:
    print(f"{c['Id']}: {c['VerifyKey']}")

# Add a new client
client.add_client(remark="my-server", vkey="unique-key")
```

### As a CLI Tool

```bash
# View all edge nodes status
nps-ctl status

# List clients on a specific edge
nps-ctl clients --edge nps-asia

# Sync configuration from one edge to all others
nps-ctl sync --from nps-asia

# Add a host mapping to all edges
nps-ctl add-host --domain app.example.com --client my-server --target :8080
```

## Configuration

Create a `config/edges.toml` file:

```toml
[edges.nps-asia]
api_url = "https://nps-asia.example.com"
auth_key = "your_auth_key"

[edges.nps-usa]
api_url = "https://nps-usa.example.com"
auth_key = "your_auth_key"
```

## API Reference

### NPSClient

Single NPS server client.

- `list_clients()` - Get all clients
- `add_client()` - Add a new client
- `edit_client()` - Modify a client
- `del_client()` - Delete a client
- `list_tunnels()` - Get all tunnels
- `add_tunnel()` - Add a new tunnel
- `list_hosts()` - Get all host mappings
- `add_host()` - Add a new host mapping

### NPSCluster

Multi-node manager.

- `get_all_clients()` - Get clients from all nodes
- `sync_clients()` - Sync clients across nodes
- `broadcast_host()` - Add host to all nodes

## License

MIT