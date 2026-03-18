# nps-ctl

[![PyPI version](https://img.shields.io/pypi/v/nps-ctl?color=green)](https://pypi.org/project/nps-ctl/)
[![CI](https://github.com/Oaklight/nps-ctl/actions/workflows/ci.yml/badge.svg)](https://github.com/Oaklight/nps-ctl/actions/workflows/ci.yml)
[![License: GPL-3.0](https://img.shields.io/badge/License-GPL--3.0-green.svg)](https://www.gnu.org/licenses/gpl-3.0)

[English](README_en.md) | [中文](README_zh.md)

A Python library and CLI tool for managing [NPS](https://github.com/djylb/nps) proxy servers.

> **Note:** This project targets [djylb/nps](https://github.com/djylb/nps), the actively maintained fork of the original [ehang-io/nps](https://github.com/ehang-io/nps) (unmaintained since 2021). The API is compatible with both forks, but djylb/nps is recommended.

## Features

- **API Client**: Type-safe Python wrapper for the NPS HTTP API
- **Multi-node Support**: Manage multiple NPS edge servers from a single interface
- **Cluster Sync**: Synchronize clients, tunnels, and hosts across edge nodes
- **NPC Deployment**: Install, configure, and manage NPC clients via SSH
- **CLI Tool**: Rich terminal interface for all operations
- **Minimal Dependencies**: Only requires [rich](https://github.com/Textualize/rich) for CLI output

## Installation

```bash
pip install nps-ctl
```

### Optional: SOCKS5 Proxy Support

```bash
pip install nps-ctl PySocks
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
nps-ctl client list --edge nps-asia

# Sync configuration from one edge to all others
nps-ctl sync --from nps-asia

# Add a host mapping to all edges
nps-ctl add-host --domain app.example.com --client my-server --target :8080

# Push client configs from clients.toml to edges
nps-ctl npc client-push

# Check NPC client status across machines
nps-ctl npc status
```

## Configuration

Create a `config/edges.toml` file:

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

Optionally, create `config/clients.toml` for NPC client management:

```toml
[clients.my-server]
ssh_host = "user@my-server.example.com"
vkey = "unique-verify-key"
edges = ["nps-asia", "nps-us"]
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
- `sync_from()` - Sync configuration from a source edge to targets
- `broadcast_host()` - Add a host mapping to all nodes

## Development

```bash
# Install dev dependencies
pip install -e ".[dev,test]"

# Lint and type check
make lint

# Run tests
make test

# Build package
make build
```

## License

GPL-3.0 — see [LICENSE](LICENSE) for details.
