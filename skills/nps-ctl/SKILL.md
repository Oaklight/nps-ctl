---
name: nps-ctl
version: 1.0.0
description: "NPS/NPC tunnel cluster management via nps-ctl. Use when the user asks to manage NPS edges, NPC clients, host mappings, or TCP/UDP tunnels."
---

# nps-ctl — NPS/NPC Cluster Management

Manages NPS edge servers and NPC clients across a multi-region tunnel cluster.

```bash
pip install nps-ctl                  # from PyPI
pip install -e ~/projects/nps-ctl    # or editable from source
```

Config files:
- `~/.config/nps-ctl/edges.toml` — edge definitions
- `~/.config/nps-ctl/clients.toml` — NPC client definitions

Run `nps-ctl edge status` to see current edges and their state.

## Edge (NPS server) management

```bash
nps-ctl edge status                           # all edges status
nps-ctl edge install --edge nps-europe -y     # install NPS on a node
nps-ctl edge upgrade --edge nps-america -y    # upgrade binary, preserve data
nps-ctl edge reconfig --edge nps-asia -y      # update nps.conf only
nps-ctl edge uninstall --edge nps-europe -y   # remove NPS
nps-ctl edge export --edge nps-america        # export data
nps-ctl edge sync --from nps-america --to nps-asia  # sync config between edges
```

## Client (NPC) management

```bash
nps-ctl client list                           # list all clients
nps-ctl client install --client cloud.deu1 -y # install NPC
nps-ctl client upgrade --client cloud.deu1 -y # upgrade NPC binary
nps-ctl client reconfig --client cloud.deu1 -y # update server addresses
nps-ctl client status --client cloud.deu1     # check status
nps-ctl client restart --client cloud.deu1    # restart service
nps-ctl client uninstall --client cloud.deu1 -y
```

## Host mappings (HTTP proxy)

```bash
nps-ctl host list                             # all edges
nps-ctl host list --edge nps-america          # single edge
nps-ctl host add -e nps-america -d myapp.service.oaklight.cn -c cloud.usa2 -t :8080
nps-ctl host del --host myapp.service.oaklight.cn -y   # delete from all edges
nps-ctl host del --edge nps-america --host myapp.service.oaklight.cn -y  # single edge
nps-ctl host edit --edge nps-america --id 42 --target :9090
```

**`host edit` cannot change the client.** To move a service, delete and re-add.

## TCP/UDP tunnels

```bash
nps-ctl tunnel list --edge nps-america
nps-ctl tunnel add -e nps-america -c homelab.oasis --type tcp --target :22 --port 30022
nps-ctl tunnel del --edge nps-america --id 5 -y
nps-ctl tunnel start --edge nps-america --id 5
nps-ctl tunnel stop --edge nps-america --id 5
```

## Common tasks

### Migrate a service to a different client

```bash
nps-ctl host del --host myapp.service.oaklight.cn -y
nps-ctl host add -e nps-america -d myapp.service.oaklight.cn -c <new-client> -t :<port>
```

### Upgrade NPS (non-destructive)

```bash
nps-ctl edge export --edge nps-america       # backup first
nps-ctl edge upgrade --edge nps-america -y   # preserves data files
```
