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

## Short flag reference

| Short | Long | Used in | Description |
|-------|------|---------|-------------|
| `-a` | `--all` | `client list`, `tunnel list`, `host list` | Show items from all edges |
| `-c` | `--client` | `client del/push/install/upgrade/reconfig/uninstall/status/restart`, `tunnel add`, `host add` | Client name (remark) or numeric ID |
| `-d` | `--domain` | `host add/del/edit` | Domain name |
| `-e` | `--edge` | Most commands | Scope operation to a specific edge |
| `-f` | `--from` | `edge sync` | Source edge name |
| `-o` | `--output` | `edge export` | Output file path |
| `-p` | `--port` | `tunnel add/del/edit` | Server port |
| `-q` | `--quiet` | `edge sync` | Suppress detailed output |
| `-r` | `--remark` | `client del`, `tunnel add/del/edit`, `host add/del/edit` | Remark (name) for locating or labeling items |
| `-t` | `--type` | `tunnel add/del/edit/list`, `edge sync` | Tunnel type or sync scope |
| `-v` | `--verbose` | `client install/upgrade/reconfig/uninstall/restart` | Show detailed output |
| `-w` | `--workers` | `edge sync` | Number of parallel workers |
| `-y` | `--yes` | `client add/del/push/install/upgrade/reconfig/uninstall`, `edge install/upgrade/reconfig/uninstall/sync`, `tunnel add/del/edit`, `host add/del/edit` | Skip confirmation prompts |
| `-T` | `--target` | `tunnel add`, `host add` | Target address (`host:port`) |
| `-V` | `--version` | Global | Show version and exit |

!!! tip
    `-v` serves double duty: it is `--verbose` on subcommands (e.g.
    `client install -v`) and on the global level (`nps-ctl -v`). The global
    `-v` is equivalent to `--verbose`. Use `--debug` for full debug logging.

## Command groups

| Group | Subcommands |
|-------|-------------|
| `client` | `list`, `push`, `add`, `install`, `upgrade`, `reconfig`, `uninstall`, `status`, `restart`, `del` |
| `edge` | `status`, `install`, `upgrade`, `reconfig`, `uninstall`, `sync`, `export` |
| `tunnel` | `list`, `add`, `del`, `edit`, `start`, `stop` |
| `host` | `list`, `add`, `del`, `edit` |
| `util` | `generate-auth-key` |
