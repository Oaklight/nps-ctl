# CLI Quick Reference

## Global options

These options apply to all commands and must be placed before the command group.

```
nps-ctl [global options] <command> <subcommand> [options]
```

| Flag | Long | Description |
|------|------|-------------|
| `-V` | `--version` | Show version and exit |
| `-v` | `--verbose` | Enable verbose output |
| | `--debug` | Enable debug logging |
| | `--config` | Path to `edges.toml` config file |
| | `--proxy` | HTTP proxy URL |
| | `--socks-proxy` | SOCKS5 proxy URL |
| | `--auto-proxy` | Auto-create SSH SOCKS proxy via specified host |
| | `--no-ssl-verify` | Disable SSL certificate verification |
| | `--json` | Emit machine-readable JSON (list, status, and `edge list`) |
| | `--no-color` | Disable colored output |

Read commands (`client list`, `edge status`, `host list`, `host status`,
`tunnel list`, `tunnel status`) default to all configured edges.
`-e/--edge` narrows to one edge and `-a/--all` is an explicit all-edges alias;
mutating commands (`client del`, `host/tunnel add|del|edit`) require one of
them.

## Short flag reference

| Short | Long | Used in | Description |
|-------|------|---------|-------------|
| `-a` | `--all` | `client list/del`, `edge status`, `tunnel list/status/add/del/edit`, `host list/status/add/del/edit` | Explicit all-edges scope (default for reads, required alternative for mutations) |
| | `--matrix` | `host list` | Domain-by-edge presence matrix |
| `-c` | `--client` | `client del/push/install/upgrade/reconfig/uninstall/status/restart`, `tunnel add`, `host add` | Client name (remark) or numeric ID |
| `-d` | `--domain` | `host add/del/edit` | Domain name |
| `-e` | `--edge` | Most commands | Scope operation to a specific edge |
| `-f` | `--from` | `edge sync` | Source edge name (default: the configured primary) |
| `-o` | `--output` | `edge export` | Output file path |
| `-p` | `--port` | `tunnel add/del/edit` | Server port |
| `-q` | `--quiet` | `edge sync` | Suppress detailed output |
| `-r` | `--remark` | `client del`, `tunnel add/del/edit`, `host add/del/edit` | Remark (name) for locating or labeling items |
| `-t` | `--type` | `tunnel add/del/edit/list`, `edge sync` | Tunnel type or sync scope |
| `-v` | `--verbose` | `client install/upgrade/reconfig/uninstall/restart` | Show detailed output |
| `-w` | `--workers` | `edge sync` | Number of parallel workers |
| `-y` | `--yes` | `client add/del/push/install/upgrade/reconfig/uninstall`, `edge install/upgrade/reconfig/uninstall/add/sync`, `tunnel add/del/edit`, `host add/del/edit` | Skip confirmation prompts |
| `-T` | `--target` | `tunnel add`, `host add` | Target address (`host:port`) |
| `-V` | `--version` | Global | Show version and exit |

!!! tip
    `-v` serves double duty: it is `--verbose` on subcommands (e.g.
    `client install -v`) and on the global level (`nps-ctl -v`). The global
    `-v` is equivalent to `--verbose`. Use `--debug` for full debug logging.

## Long-only options

| Flag | Used in | Description |
|------|---------|-------------|
| `--prune` | `edge sync` | Delete resources on targets that are absent from the source (confirmation required; aborts on incomplete source data) |
| `--push` | `client add` | Push the new client to its configured edges after writing `clients.toml` |
| `--api-url` URL | `edge add` | Edge API URL (required) |
| `--region` TEXT | `edge add` | Display region |
| `--ssh-host` HOST | `edge add` | SSH host alias |
| `--no-auth-key` | `edge add` | Skip the auth key prompt |
| `--host`, `--port` | `web` | Bind address/port (default `127.0.0.1:8080`) |
| `--username`, `--password` | `web` | Single-user Basic Auth |
| `--users-file` PATH | `web` | Multi-user TOML file with `operator`/`viewer` roles |
| `--allow-writes` | `web` | Enable add/sync/edit/delete and add-edge actions |
| `--insecure` | `web` | Allow a non-loopback read-only bind without authentication |
| `--iterations` N | `util hash-password` | PBKDF2 iteration count |
| `--since` DURATION | `check links` | Window to examine, e.g. `90m`, `6h`, `2d` (default `6h`) |
| `--log-path` PATH | `check links` | NPC log path on the client hosts (default `/var/log/npc.log`) |
| `--tail-bytes` N | `check links` | How much of each log's end to read (default 4 MiB) |
| `--profile` NAME | `check stress` | `smoke`, `ladder`, `slow`, `churn` or `soak` |
| `--duration` DURATION | `check stress` | Soak length (default `10m`) |
| `--size`, `--count`, `--concurrency` | `check probe` | Body size (`64K`, `1M`), requests, parallelism |
| `--mode`, `--chunk-kb`, `--gap-ms` | `check probe` | `slow` uploads: chunk size and gap between chunks |
| `--http-proxy-port` N | `check probe/stress` | NPS HTTP proxy port (default: read from `nps.conf`, else 30080) |
| `--fail-on` LEVEL | `check` | `error` for probe/stress; `warn` for links |
| `--dry-run` | `check probe/stress` | Print the plan and change nothing |
| `--delete` | `check leftovers` | Delete the leftovers found (requires `-e` or `-a`) |

## Command groups

| Group | Subcommands |
|-------|-------------|
| `client` | `list`, `push`, `add`, `install`, `upgrade`, `reconfig`, `uninstall`, `status`, `restart`, `del` |
| `edge` | `list`, `status`, `install`, `upgrade`, `reconfig`, `uninstall`, `primary`, `add`, `sync`, `export` |
| `tunnel` | `list`, `status`, `add`, `del`, `edit`, `start`, `stop` |
| `host` | `list`, `status`, `add`, `del`, `edit` |
| `check` | `links`, `probe`, `stress`, `leftovers` |
| `util` | `generate-auth-key`, `hash-password` |
| `web` | Dashboard server (read-only unless `--allow-writes`) |
