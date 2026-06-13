# CLI Reference

## Global Options

| Option | Description |
| --- | --- |
| `--config PATH` | Path to `edges.toml` config file |
| `--debug` | Enable debug logging |
| `-v`, `--verbose` | Enable verbose output |
| `--proxy URL` | HTTP proxy URL |
| `--socks-proxy URL` | SOCKS5 proxy URL |
| `--auto-proxy HOST` | Auto-create SSH SOCKS proxy via specified host |
| `--no-ssl-verify` | Disable SSL certificate verification |
| `-V`, `--version` | Show version and exit |

## Command Groups

nps-ctl organizes commands into five groups: `client`, `edge`, `tunnel`, `host`, and `util`.

---

## `client` — NPC Client Management

### `client list`

List clients from NPS API and optionally update `clients.toml`.

| Option | Description |
| --- | --- |
| `-e`, `--edge` EDGE | Edge name to query clients from |
| `-a`, `--all` | Show clients from all edges |
| `--update` | Update `clients.toml` with fetched client info |
| `--dry-run` | Show what would be written without modifying `clients.toml` |

```bash
nps-ctl client list                   # First edge
nps-ctl client list -e nps-us         # Specific edge
nps-ctl client list -a                # All edges
nps-ctl client list -e nps-us --update  # Fetch and update clients.toml
```

### `client push`

Push client configs from `clients.toml` to edges.

| Option | Description |
| --- | --- |
| `-c`, `--client` NAME | Specific client name to push (default: all clients) |
| `-e`, `--edge` EDGE | Specific edge to push to (default: all edges in client config) |
| `--dry-run` | Show what would be pushed without making changes |
| `--update` | Update existing clients on edges (sync vkey from `clients.toml`) |
| `-y`, `--yes` | Skip confirmation prompts |

```bash
nps-ctl client push                         # Push all clients to all edges
nps-ctl client push -c my-server            # Push specific client
nps-ctl client push -e nps-us --update      # Update existing clients on one edge
nps-ctl client push --dry-run               # Preview changes
```

### `client add`

Interactively add a new client entry to `clients.toml`.

| Option | Description |
| --- | --- |
| `--name` | Client name (skip interactive prompt) |
| `--ssh-host` | SSH host (skip interactive prompt) |
| `--edges` EDGE [EDGE ...] | Edge names (skip interactive prompt) |
| `--vkey` | Verify key (auto-generated if not provided) |
| `--conn-type` {tls,tcp,kcp} | Connection type (default: tls) |
| `-y`, `--yes` | Skip confirmation prompts |

```bash
nps-ctl client add                                        # Fully interactive
nps-ctl client add --name my-server --ssh-host 10.0.0.5   # Partially pre-filled
```

### `client del`

Delete a client from edge(s). Requires one of `--id` or `-r/--remark` (mutually exclusive).

| Option | Description |
| --- | --- |
| `--id` ID | Client ID (edge-specific, requires `-e`) |
| `-r`, `--remark` NAME | Client remark name (can operate across all edges) |
| `-e`, `--edge` EDGE | Edge name (required for `--id`, default: all edges for `--remark`) |
| `-y`, `--yes` | Skip confirmation prompts |

```bash
nps-ctl client del --id 3 -e nps-us -y          # Delete by edge-specific ID
nps-ctl client del -r my-server                  # Delete by remark across all edges
```

### `client install`

Install NPC on client machines via SSH.

| Option | Description |
| --- | --- |
| `-c`, `--client` NAME | Client name to install (default: all clients) |
| `--version` VER | NPC version to install |
| `--release-url` URL | Custom release URL for NPC binary |
| `--force-reinstall` | *(Deprecated: use `client upgrade`)* Force reinstall |
| `-y`, `--yes` | Skip confirmation prompts |
| `-v`, `--verbose` | Show detailed output |

```bash
nps-ctl client install                          # Install all clients
nps-ctl client install -c my-server             # Install specific client
nps-ctl client install --version v0.34.7 -y     # Specific version, no prompt
```

### `client upgrade`

Upgrade NPC binary and reconfigure on client machines.

| Option | Description |
| --- | --- |
| `-c`, `--client` NAME | Client name to upgrade (default: all clients) |
| `--version` VER | NPC version to install |
| `--release-url` URL | Custom release URL for NPC binary |
| `-y`, `--yes` | Skip confirmation prompts |
| `-v`, `--verbose` | Show detailed output |

```bash
nps-ctl client upgrade                           # Upgrade all clients
nps-ctl client upgrade -c my-server -v           # Upgrade one client, verbose
```

### `client reconfig`

Reconfigure NPC with updated server addresses (no binary download).

| Option | Description |
| --- | --- |
| `-c`, `--client` NAME | Client name to reconfigure (default: all clients) |
| `-y`, `--yes` | Skip confirmation prompts |
| `-v`, `--verbose` | Show detailed output |

```bash
nps-ctl client reconfig                          # Reconfigure all clients
nps-ctl client reconfig -c my-server             # Reconfigure specific client
```

### `client uninstall`

Uninstall NPC from client machines via SSH.

| Option | Description |
| --- | --- |
| `-c`, `--client` NAME | Client name to uninstall (default: all clients) |
| `-y`, `--yes` | Skip confirmation prompts |
| `-v`, `--verbose` | Show detailed output |

```bash
nps-ctl client uninstall -c my-server -y
```

### `client status`

Check NPC status on client machines.

| Option | Description |
| --- | --- |
| `-c`, `--client` NAME | Client name to check (default: all clients) |
| `--parallel` | Check all clients in parallel via SSH |

```bash
nps-ctl client status                            # Check all clients
nps-ctl client status -c my-server               # Check specific client
nps-ctl client status --parallel                 # Parallel check
```

### `client restart`

Restart NPC service on client machines.

| Option | Description |
| --- | --- |
| `-c`, `--client` NAME | Client name to restart (default: all clients) |
| `-v`, `--verbose` | Show detailed output |

```bash
nps-ctl client restart
nps-ctl client restart -c my-server
```

---

## `edge` — NPS Edge Node Management

### `edge status`

Show status of all configured edge nodes.

```bash
nps-ctl edge status
```

### `edge install`

Install NPS on edge nodes via SSH.

| Option | Description |
| --- | --- |
| `-e`, `--edge` EDGE | Edge name to install (default: all edges) |
| `--template` PATH | Path to NPS config template |
| `--version` VER | NPS version to install |
| `--release-url` URL | Custom release URL for NPS binary |
| `--force-reinstall` | *(Deprecated: use `edge upgrade`)* Force reinstall |
| `-y`, `--yes` | Skip confirmation prompts |
| `-v`, `--verbose` | Show detailed output |

```bash
nps-ctl edge install -e nps-us -y
nps-ctl edge install --version v0.34.7
```

### `edge upgrade`

Upgrade NPS binary on edge nodes (preserves data files).

| Option | Description |
| --- | --- |
| `-e`, `--edge` EDGE | Edge name to upgrade (default: all edges) |
| `--template` PATH | Path to NPS config template |
| `--version` VER | NPS version to install |
| `--release-url` URL | Custom release URL for NPS binary |
| `-y`, `--yes` | Skip confirmation prompts |
| `-v`, `--verbose` | Show detailed output |

```bash
nps-ctl edge upgrade -e nps-us -v
nps-ctl edge upgrade --version v0.34.7 -y
```

### `edge reconfig`

Reconfigure NPS with updated config (no binary download). Restarts the service.

| Option | Description |
| --- | --- |
| `-e`, `--edge` EDGE | Edge name to reconfigure (default: all edges) |
| `--template` PATH | Path to NPS config template |
| `-y`, `--yes` | Skip confirmation prompts |
| `-v`, `--verbose` | Show detailed output |

```bash
nps-ctl edge reconfig -e nps-us
```

### `edge uninstall`

Uninstall NPS from edge nodes via SSH.

| Option | Description |
| --- | --- |
| `-e`, `--edge` EDGE | Edge name to uninstall (default: all edges) |
| `-y`, `--yes` | Skip confirmation prompts |
| `-v`, `--verbose` | Show detailed output |

```bash
nps-ctl edge uninstall -e nps-us -y
```

### `edge sync`

Sync configuration from one edge to others.

| Option | Description |
| --- | --- |
| `-f`, `--from` EDGE | Source edge name to sync from (required) |
| `-e`, `--edge`, `--to` EDGE [EDGE ...] | Target edge name(s) to sync to (default: all other edges) |
| `-t`, `--type` {all,clients,tunnels,hosts} | Type of configuration to sync (default: all) |
| `-y`, `--yes` | Skip confirmation prompts |
| `--parallel` | Sync to targets in parallel |
| `-q`, `--quiet` | Suppress detailed output |
| `-w`, `--workers` N | Number of parallel workers |

```bash
nps-ctl edge sync -f nps-asia                        # Sync all to all other edges
nps-ctl edge sync -f nps-asia --to nps-us             # Sync to specific edge
nps-ctl edge sync -f nps-asia -t tunnels --parallel   # Sync only tunnels, parallel
```

### `edge export`

Export edge configuration to a file.

| Option | Description |
| --- | --- |
| `-e`, `--edge` EDGE | Edge name to export (default: all edges) |
| `-o`, `--output` PATH | Output file path |

```bash
nps-ctl edge export -e nps-us -o backup.json
nps-ctl edge export                                   # Export all edges
```

---

## `tunnel` — Tunnel Management

### `tunnel list`

List tunnels on edge nodes.

| Option | Description |
| --- | --- |
| `-e`, `--edge` EDGE | Edge name to query (default: first edge) |
| `-t`, `--type` {tcp,udp,socks5,httpProxy,secret,p2p,file} | Filter by tunnel type |
| `-a`, `--all` | Show tunnels from all edges |

```bash
nps-ctl tunnel list                       # First edge
nps-ctl tunnel list -a                    # All edges
nps-ctl tunnel list -t tcp                # Only TCP tunnels
nps-ctl tunnel list -e nps-us -t udp      # UDP tunnels on specific edge
```

### `tunnel add`

Add a new tunnel to edge nodes.

| Option | Description |
| --- | --- |
| `-c`, `--client` NAME | Client name or ID (required) |
| `-t`, `--type` {tcp,udp,socks5,httpProxy} | Tunnel type (default: tcp) |
| `-p`, `--port` PORT | Server port |
| `-T`, `--target` ADDR | Target address (host:port) |
| `-e`, `--edge` EDGE | Edge name to add tunnel to (default: all edges) |
| `-r`, `--remark` TEXT | Tunnel remark |
| `-y`, `--yes` | Skip confirmation prompts |

```bash
nps-ctl tunnel add -c my-server -t tcp -p 8080 -T 127.0.0.1:80
nps-ctl tunnel add -c my-server -t udp -p 5353 -T 127.0.0.1:53 -r "dns"
nps-ctl tunnel add -c my-server -t socks5 -p 1080 -e nps-us
```

### `tunnel del`

Delete a tunnel from edge node(s). Locate by `--id`, `-r/--remark`, or `-p/--port` + `-t/--type` (cross-edge locators).

| Option | Description |
| --- | --- |
| `--id` ID | Tunnel ID (edge-specific, requires `-e`) — mutually exclusive with `--remark` |
| `-r`, `--remark` TEXT | Tunnel remark (can operate across all edges) — mutually exclusive with `--id` |
| `-p`, `--port` PORT | Server port (use with `-t/--type` to locate tunnel across edges) |
| `-t`, `--type` {tcp,udp,socks5,httpProxy} | Tunnel type (use with `-p/--port` to locate tunnel across edges) |
| `-e`, `--edge` EDGE | Edge name (required for `--id`, optional for `--remark`/`--port`+`--type`) |
| `-y`, `--yes` | Skip confirmation prompts |

```bash
nps-ctl tunnel del --id 5 -e nps-us -y           # By edge-specific ID
nps-ctl tunnel del -r "dns"                       # By remark across all edges
nps-ctl tunnel del -p 8080 -t tcp                 # By port+type across all edges
```

!!! note "Multi-match safety"
    If multiple tunnels match the locator, the command errors out. Use `--id` with `-e` for precision.

### `tunnel edit`

Edit an existing tunnel on edge node(s). Locator arguments (`--id`, `-r/--remark`, `-p/--port` + `-t/--type`) identify the tunnel; `--new-*` arguments specify the changes.

**Locator options:**

| Option | Description |
| --- | --- |
| `--id` ID | Tunnel ID to edit (edge-specific, requires `-e`) — mutually exclusive with `--remark` |
| `-r`, `--remark` TEXT | Tunnel remark to locate (can operate across all edges) — mutually exclusive with `--id` |
| `-p`, `--port` PORT | Server port to locate (use with `-t/--type` across edges) |
| `-t`, `--type` {tcp,udp,socks5,httpProxy} | Tunnel type to locate (use with `-p/--port` across edges) |
| `-e`, `--edge` EDGE | Edge name (required for `--id`, optional for `--remark`/`--port`+`--type`) |

**Value options (what to change):**

| Option | Description |
| --- | --- |
| `--new-target` ADDR | New target address (host:port) |
| `--new-port` PORT | New server port |
| `--new-remark` TEXT | New tunnel remark |
| `-y`, `--yes` | Skip confirmation prompts |

```bash
nps-ctl tunnel edit -r "dns" --new-target 10.0.0.1:53
nps-ctl tunnel edit -p 8080 -t tcp --new-port 9090
nps-ctl tunnel edit --id 5 -e nps-us --new-remark "web-proxy"
```

### `tunnel start`

Start a stopped tunnel on an edge node.

| Option | Description |
| --- | --- |
| `--id` ID | Tunnel ID to start (required) |
| `-e`, `--edge` EDGE | Edge name (required) |

```bash
nps-ctl tunnel start --id 5 -e nps-us
```

### `tunnel stop`

Stop a running tunnel on an edge node.

| Option | Description |
| --- | --- |
| `--id` ID | Tunnel ID to stop (required) |
| `-e`, `--edge` EDGE | Edge name (required) |

```bash
nps-ctl tunnel stop --id 5 -e nps-us
```

---

## `host` — Host Mapping Management

### `host list`

List host mappings on edge nodes.

| Option | Description |
| --- | --- |
| `-e`, `--edge` EDGE | Edge name to query (default: first edge) |
| `-a`, `--all` | Show host mappings from all edges |

```bash
nps-ctl host list
nps-ctl host list -a
nps-ctl host list -e nps-us
```

### `host add`

Add a new host mapping to edge nodes.

| Option | Description |
| --- | --- |
| `-d`, `--domain` DOMAIN | Domain name (required) |
| `-c`, `--client` NAME | Client name or ID (required) |
| `-T`, `--target` ADDR | Target address (host:port) (required) |
| `-e`, `--edge` EDGE | Edge name to add host mapping to (default: all edges) |
| `-r`, `--remark` TEXT | Host mapping remark |
| `-y`, `--yes` | Skip confirmation prompts |

```bash
nps-ctl host add -d app.example.com -c my-server -T :8080
nps-ctl host add -d api.example.com -c my-server -T 127.0.0.1:3000 -r "api"
```

### `host del`

Delete a host mapping from edge node(s). Requires one of `--id`, `-d/--domain`, or `-r/--remark` (mutually exclusive).

| Option | Description |
| --- | --- |
| `--id` ID | Host ID (edge-specific, requires `-e`) |
| `-d`, `--domain` DOMAIN | Host domain name (can operate across all edges) |
| `-r`, `--remark` TEXT | Host remark (can operate across all edges) |
| `-e`, `--edge` EDGE | Edge name (required for `--id`, optional for `--domain`/`--remark`) |
| `-y`, `--yes` | Skip confirmation prompts |

```bash
nps-ctl host del --id 2 -e nps-us -y             # By edge-specific ID
nps-ctl host del -d app.example.com               # By domain across all edges
nps-ctl host del -r "api"                         # By remark across all edges
```

!!! note "Multi-match safety"
    If multiple host mappings match the locator, the command errors out. Use `--id` with `-e` for precision.

### `host edit`

Edit an existing host mapping on edge node(s). Locator arguments identify the host; `--new-*` arguments specify the changes.

**Locator options:**

| Option | Description |
| --- | --- |
| `--id` ID | Host ID to edit (edge-specific, requires `-e`) — mutually exclusive with `--domain` and `--remark` |
| `-d`, `--domain` DOMAIN | Host domain to locate (can operate across all edges) |
| `-r`, `--remark` TEXT | Host remark to locate (can operate across all edges) |
| `-e`, `--edge` EDGE | Edge name (required for `--id`, optional for `--domain`/`--remark`) |

**Value options (what to change):**

| Option | Description |
| --- | --- |
| `--new-domain` DOMAIN | New domain name |
| `--new-target` ADDR | New target address (host:port) |
| `--new-remark` TEXT | New host remark |
| `-y`, `--yes` | Skip confirmation prompts |

```bash
nps-ctl host edit -d app.example.com --new-target :9090
nps-ctl host edit -r "api" --new-domain api-v2.example.com
nps-ctl host edit --id 2 -e nps-us --new-remark "web-app"
```

---

## `util` — Utility Commands

### `util generate-auth-key`

Generate a random authentication key for NPS.

| Option | Description |
| --- | --- |
| `length` | Key length (positional, default: 43) |

```bash
nps-ctl util generate-auth-key          # Default 43 characters
nps-ctl util generate-auth-key 64       # Custom length
```

---

## Short Flag Reference

Quick reference for all single-letter flags:

| Flag | Long Form | Scope |
| --- | --- | --- |
| `-a` | `--all` | `client list`, `tunnel list`, `host list` |
| `-c` | `--client` | Subcommands that take a client argument |
| `-d` | `--domain` | `host add`, `host del`, `host edit` |
| `-e` | `--edge` | Most subcommands |
| `-f` | `--from` | `edge sync` |
| `-o` | `--output` | `edge export` |
| `-p` | `--port` | `tunnel add`, `tunnel del`, `tunnel edit` |
| `-q` | `--quiet` | `edge sync` |
| `-r` | `--remark` | Various add/del/edit subcommands |
| `-t` | `--type` | `tunnel list/add/del/edit`, `edge sync` |
| `-v` | `--verbose` | Global and per-subcommand |
| `-w` | `--workers` | `edge sync` |
| `-y` | `--yes` | Most mutating subcommands |
| `-T` | `--target` | `tunnel add`, `host add` |
| `-V` | `--version` | Global |
