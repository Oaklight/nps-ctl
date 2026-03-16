# CLI Reference

## Global Options

| Option                    | Description                                     |
| ------------------------- | ----------------------------------------------- |
| `--config DIR`            | Config directory (default: `config/`)            |
| `--edge NAME`             | Target a specific edge node                      |
| `--all`                   | Target all edge nodes                            |
| `--socks-proxy HOST:PORT` | Route through SOCKS5 proxy                       |
| `--auto-proxy`            | Auto SSH SOCKS tunnel                            |
| `-v`, `--verbose`         | Increase log verbosity                           |
| `-y`, `--yes`             | Skip confirmation prompts                        |

## Commands

### `nps-ctl status`

Show status of all configured edge nodes.

```bash
nps-ctl status
```

### `nps-ctl client list`

List clients on edge nodes.

```bash
nps-ctl client list                # First edge
nps-ctl client list --edge nps-us  # Specific edge
nps-ctl client list --all          # All edges
```

### `nps-ctl client add`

Add a new client.

```bash
nps-ctl client add --remark my-server --vkey unique-key
```

### `nps-ctl tunnels`

List tunnels.

```bash
nps-ctl tunnels --all
```

### `nps-ctl add-tunnel`

Add a tunnel to an edge.

```bash
nps-ctl add-tunnel --type tcp --client my-server --port 8080 --target 127.0.0.1:80
```

### `nps-ctl hosts`

List host mappings.

```bash
nps-ctl hosts --all
```

### `nps-ctl add-host`

Add a host mapping.

```bash
nps-ctl add-host --domain app.example.com --client my-server --target :8080
```

### `nps-ctl sync`

Sync configuration from one edge to others.

```bash
nps-ctl sync --from nps-asia              # Sync to all other edges
nps-ctl sync --from nps-asia --to nps-us  # Sync to specific edge
```

### `nps-ctl npc install`

Install NPC client on remote machines via SSH.

```bash
nps-ctl npc install my-server
```

### `nps-ctl npc status`

Check NPC client status across machines.

```bash
nps-ctl npc status
```

### `nps-ctl npc client-push`

Push client configurations from `clients.toml` to NPS edges.

```bash
nps-ctl npc client-push
nps-ctl npc client-push --update  # Update existing clients
```
