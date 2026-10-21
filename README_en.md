# nps-ctl

[![PyPI version](https://img.shields.io/pypi/v/nps-ctl?color=green)](https://pypi.org/project/nps-ctl/)
[![CI](https://github.com/Oaklight/nps-ctl/actions/workflows/ci.yml/badge.svg)](https://github.com/Oaklight/nps-ctl/actions/workflows/ci.yml)
[![License: GPL-3.0](https://img.shields.io/badge/License-GPL--3.0-green.svg)](https://www.gnu.org/licenses/gpl-3.0)

[English](README_en.md) | [中文](README_zh.md)

A Python library and CLI tool for managing [NPS](https://github.com/djylb/nps) proxy servers.

> **Note:** This project targets [djylb/nps](https://github.com/djylb/nps), the actively maintained fork of the original [ehang-io/nps](https://github.com/ehang-io/nps) (unmaintained since 2021). The API is compatible with both forks, but djylb/nps is recommended.

> This project is actively maintained and will continue to evolve. I have no intention of going closed-source — please don't fork just to archive it. If you find it useful, a Star is appreciated.

## Features

- **API Client**: Type-safe Python wrapper for the NPS HTTP API
- **Multi-node Support**: Manage multiple NPS edge servers from a single interface
- **Cluster Sync**: Synchronize clients, tunnels, and hosts across edge nodes
- **NPC Deployment**: Install, configure, and manage NPC clients via SSH
- **CLI Tool**: Rich terminal interface for all operations
- **Web Dashboard**: Read-only by default; opt-in add/sync/edit/delete and add-edge actions, with CSRF/same-origin guards and viewer/operator roles
- **Machine-readable Output**: JSON mode and non-TTY-safe tables for scripts and agents
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
from nps_ctl import NPSClient, client_mgmt

# Connect to a single NPS server
client = NPSClient(
    base_url="https://nps.example.com",
    auth_key="your_auth_key"
)

# List all clients
for c in client_mgmt.list_clients(client):
    print(f"{c['Id']}: {c['VerifyKey']}")

# Add a new client
client_mgmt.add_client(client, remark="my-server", vkey="unique-key")
```

### As a CLI Tool

```bash
# List every configured edge without contacting it
nps-ctl edge list

# Check every edge
nps-ctl edge status

# Check one edge (clients, hosts, and tunnels)
nps-ctl edge status -e nps-asia

# Check client liveness and host inventory for one edge
nps-ctl host status -e nps-asia

# Check tunnel inventory for one edge
nps-ctl tunnel status -e nps-asia

# Read commands default to all edges; -e narrows to one
nps-ctl client list
nps-ctl client list --edge nps-asia

# Sync configuration from one edge to the others
nps-ctl edge sync --from nps-asia -y

# Or set a primary and sync from it; --prune also deletes extras on targets
nps-ctl edge primary nps-asia
nps-ctl edge sync -y
nps-ctl edge sync --prune -y          # destructive: confirm the target list

# Add an edge entry to edges.toml (auth key from NPS_EDGE_AUTH_KEY or a prompt)
nps-ctl edge add nps-eu --api-url https://nps-eu.example.com --ssh-host cloud.deu1

# Add a client to clients.toml and push it to its edges in one step
nps-ctl client add --name my-server --ssh-host user@host --edges nps-asia --push -y

# Write commands require an explicit target: -a for all edges, -e for one
nps-ctl host add -a -d app.example.com -c my-server -T :8080
nps-ctl host add -e nps-asia -d app.example.com -c my-server -T :8080

# Push client configs from clients.toml to edges
nps-ctl client push

# Check NPC client status across machines
nps-ctl client status

# Machine-readable inventory
nps-ctl edge list --json
```

Read commands (`client list`, `edge status`, `host list`, `host status`, `tunnel list`, `tunnel status`) default to all configured edges. `-e/--edge` narrows to one edge; `-a/--all` is an explicit all-edges alias. Mutating commands (`host/tunnel add|del|edit`, `client del`) require one of `-e` or `-a`; there is no silent cluster-wide default. `edge status` fetches client, host, and tunnel inventories, so it exits 1 if any of those fetches fails, not only when an edge is unreachable.

Piped output has no ANSI styling. Add `--no-color` to disable color on a terminal. `--json` is available on `edge list`, `edge status`, `host status`, `tunnel status`, and `client/host/tunnel list`.

## Web dashboard

`nps-ctl web` serves a dashboard for all configured edges. It is read-only
unless started with `--allow-writes`:

```bash
# Single operator
export NPS_WEB_PASSWORD='choose-a-password'
nps-ctl web --username admin --allow-writes

# Several users and roles
nps-ctl util hash-password          # prints a PBKDF2 hash, never the password
cat > web-users.toml <<'EOF'
[[users]]
name = "admin"
password_hash = "pbkdf2_sha256$260000$...$..."
role = "operator"

[[users]]
name = "viewer"
password_hash = "pbkdf2_sha256$260000$...$..."
role = "viewer"
EOF
nps-ctl web --users-file web-users.toml --allow-writes
# http://127.0.0.1:8080/
```

With `--allow-writes`, operators can sync edges (optionally with `prune`),
add clients/tunnels/hosts, add an edge to `edges.toml`, and edit or delete a
client, tunnel, or host on one edge. Every action uses an explicit target
list, a review step, a per-process CSRF token, same-origin/Host checks, and a
single-writer lock. Viewers always get a read-only page. Without
`--allow-writes` every mutation endpoint returns 403.

The server binds to `127.0.0.1` by default. Binding to a non-loopback address
without credentials is refused unless `--insecure` is passed; writes are
always refused on a network bind without authentication. The dashboard shows
edge health (`online`/`partial`/`offline`) and resource counts, and lets you
browse clients, tunnels and hosts per edge; unavailable counts are reported
as `null`, and credentials (client verification keys, tunnel passwords, and
Basic Auth) are redacted from its JSON output. The built-in server speaks
plain HTTP, so terminate TLS in front of it before exposing it beyond
loopback; ready-to-use systemd and Caddy files are in
[`deploy/web`](deploy/web).

### Docker

Images are published to Docker Hub as
[`oaklight/nps-ctl`](https://hub.docker.com/r/oaklight/nps-ctl):

| Tag | Base | Notes |
| --- | --- | --- |
| `latest`, `latest-python` | `python:3.12-slim` | Installs the wheel; full CLI |
| `<version>-alpine` | `alpine` | Nuitka musl binary; no Python runtime |
| `<version>-glibc` | `ubuntu:24.04` | Nuitka glibc binary; no Python runtime |

Start the dashboard with:

```bash
docker run -d --name nps-ctl-web \
  -p 8080:8080 \
  -v "$PWD/config:/config" \
  -e NPS_WEB_USERNAME=admin \
  -e NPS_WEB_PASSWORD='choose-a-password' \
  oaklight/nps-ctl:latest
```

The container reads `/config/edges.toml` and requires either
`/config/web-users.toml` or `NPS_WEB_USERNAME`/`NPS_WEB_PASSWORD`. Append
`--allow-writes` to enable actions. Other commands run with
`--config /config/edges.toml` prepended:

```bash
docker run --rm -v "$PWD/config:/config" oaklight/nps-ctl:latest edge status
```

See [`docker/README.md`](docker/README.md) for Compose files, environment
variables, and local image builds. The glibc variant needs a base at least
as new as its build runner, so the Alpine image is the small one.

## Configuration

Create a `config/edges.toml` file:

```toml
primary = "nps-asia"   # default source for `edge sync`

[[edges]]
name = "nps-asia"
api_url = "https://nps-asia.example.com"
auth_key = "your_auth_key"
region = "Asia"
ssh_host = "cloud.jpn1"

[[edges]]
name = "nps-us"
api_url = "https://nps-us.example.com"
auth_key = "your_auth_key"
region = "US"
ssh_host = "cloud.usa1"
```

The optional top-level `primary` names the default source edge for
`edge sync`. Set it with `edge primary NAME`; append a new edge with
`edge add NAME --api-url URL` (the auth key comes from `NPS_EDGE_AUTH_KEY` or
a hidden prompt, never argv). Both edits preserve comments in the file.

The modern `/api/*` management API is used when an edge has credentials and
the server supports it. Add `username`/`password` (or a `platform_token`) to
an edge entry:

```toml
[[edges]]
name = "nps-asia"
api_url = "https://nps-asia.example.com"
auth_key = "your_auth_key"
username = "admin"
password = "your_password"
# platform_token = "..."   # alternative to username/password
api_mode = "auto"           # "auto" | "modern" | "legacy"
```

`auto` probes `/api/system/health` once and falls back to the legacy API.
Modern listings use `/api/*` endpoints and fetch every page; legacy listings
fan out over the eight tunnel modes, including `mixProxy`, which djylb/nps
uses to store socks5 and httpProxy tunnels.

Optionally, create `config/clients.toml` for NPC client management:

```toml
[[clients]]
name = "my-server"
ssh_host = "user@my-server.example.com"
vkey = "unique-verify-key"
edges = ["nps-asia", "nps-us"]
```

The config directory is resolved from `./config`, then `~/.config/nps-ctl`, then `/etc/nps-ctl`. Use `--config` to point at a specific `edges.toml`.

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

- `edge_names` - Configured edge names in file order
- `get_all_clients()` / `get_all_tunnels()` / `get_all_hosts()` - Fetch from every edge. Returns an `EdgeResults` mapping; a failed edge has an empty list and its reason in `.errors`
- `sync_from(..., prune=False)` - Sync configuration from a source edge to targets. `prune=True` also deletes resources absent from the source and aborts if the source data cannot be read completely
- `reload()` - Reload `edges.toml` in place (used by the dashboard Add edge action)
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

### Binary builds

`make build-binary` produces a native Nuitka binary; on Linux it links against
glibc. `make build-binary-musl` builds inside Alpine and links against musl, so
that artifact runs on musl distributions (such as Alpine) but not directly on
glibc systems like Debian or Arch. The _Nuitka Binary Build_ workflow builds the
full platform matrix and uploads the artifacts.

## Credits

- Partial-failure exit codes for `client status` and `edge sync` (#35) came
  from [@dannyward630](https://github.com/dannyward630)'s
  [`fix/35-partial-failure-exit-codes`](https://github.com/dannyward630/nps-ctl/tree/fix/35-partial-failure-exit-codes)
  branch.

## License

GPL-3.0 — see [LICENSE](LICENSE) for details.
