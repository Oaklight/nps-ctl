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

## Cluster inventory (do this first)

Run `nps-ctl edge list` before any edge-targeted operation. It reads
`edges.toml` only and prints every configured edge, including edges that are
currently unreachable. The edge names in the examples below are illustrative;
they are never the inventory.

- Read commands (`host list`, `host status`, `client list`, `tunnel list`,
  `tunnel status`) default to all edges.
- Write commands require an explicit target: `-e <edge>` for one edge or
  `-a/--all` for every configured edge. There is no silent cluster-wide default.
- `nps-ctl edge status` also lists every edge, but contacts each one and
  fetches full client, host, and tunnel inventories. Use `-e <edge>` to scope
  it. It exits 1 if any of those fetches fails, not only when an edge is down.
- Add `--json` for machine-readable output on `edge list`, `edge status`,
  `host status`, `tunnel status`, and `client/host/tunnel list`. Piped output
  has no ANSI styling; `--no-color` disables it explicitly.

```bash
nps-ctl edge list --json      # stable inventory for scripts and agents
```

## Edge (NPS server) management

```bash
nps-ctl edge list                             # every configured edge, offline
nps-ctl edge status                           # all edges status
nps-ctl edge status -e nps-america            # one edge, includes tunnels
nps-ctl edge install --edge nps-europe -y     # install NPS on a node
nps-ctl edge upgrade --edge nps-america -y    # upgrade binary, preserve data
nps-ctl edge reconfig --edge nps-asia -y      # update nps.conf only
nps-ctl edge uninstall --edge nps-europe -y   # remove NPS
nps-ctl edge export --edge nps-america        # export data
nps-ctl edge primary nps-asia                 # default source for edge sync
nps-ctl edge sync --from nps-america --to nps-asia  # sync config between edges
nps-ctl edge sync -y                          # sync from the configured primary
nps-ctl edge sync --prune -y                  # also delete extras on targets
nps-ctl edge add nps-eu --api-url https://nps-eu.example.com --ssh-host cloud.deu1
```

`edge sync --prune` is destructive. It aborts before changing anything when a
selected source fetch fails; without `-y` it prints the target list and asks
for confirmation.

## Client (NPC) management

```bash
nps-ctl client list                           # list all clients
nps-ctl client add --name new --ssh-host user@host --edges nps-asia --push -y
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
nps-ctl host list --matrix                    # domain-by-edge presence matrix
nps-ctl host list --edge nps-america          # single edge
nps-ctl host status                           # clients/hosts/ports per edge
nps-ctl host status -e nps-america --json     # single edge, machine-readable
nps-ctl host add -e nps-america -d myapp.service.oaklight.cn -c cloud.usa2 -T :8080
nps-ctl host add -a -d myapp.service.oaklight.cn -c cloud.usa2 -T :8080  # every edge
nps-ctl host del --domain myapp.service.oaklight.cn -a -y   # delete from all edges
nps-ctl host del --edge nps-america --domain myapp.service.oaklight.cn -y  # single edge
nps-ctl host edit --edge nps-america --id 42 --new-target :9090
```

**`host edit` cannot change the client.** To move a service, delete and re-add.

## TCP/UDP tunnels

```bash
nps-ctl tunnel list --edge nps-america
nps-ctl tunnel status                         # tunnels/running/ports per edge
nps-ctl tunnel status -e nps-america --json   # single edge, machine-readable
nps-ctl tunnel add -e nps-america -c homelab.oasis --type tcp --target :22 --port 30022
nps-ctl tunnel del --edge nps-america --id 5 -y
nps-ctl tunnel start --edge nps-america --id 5
nps-ctl tunnel stop --edge nps-america --id 5
```

Tunnel counts include `mixProxy`, where djylb/nps stores socks5 and httpProxy
tunnels. `tunnel list -t socks5|httpProxy` matches those rows; `-t mixProxy`
matches both.

## Web dashboard

`nps-ctl web` is read-only by default. With `--allow-writes`, operators can
sync edges (optionally with prune), add clients/tunnels/hosts, add an edge to
`edges.toml`, and edit or delete a client, tunnel, or host on one edge. Every
action uses an explicit target list, a review step, a per-process CSRF token,
same-origin/Host checks, and a single-writer lock.

```bash
# single operator
NPS_WEB_PASSWORD='...' nps-ctl web --username admin --allow-writes

# multi-user: operator can write, viewer is read-only
nps-ctl util hash-password          # prints a PBKDF2 hash, never the password
nps-ctl web --users-file web-users.toml --allow-writes
```

The server binds to `127.0.0.1` by default. A non-loopback bind without
credentials requires `--insecure` and is read-only; writes always require
authentication on a network bind. Terminate TLS in front of the loopback
listener; `deploy/web` contains a systemd unit and Caddy site block.

## Common tasks

### Migrate a service to a different client

```bash
nps-ctl host del --domain myapp.service.oaklight.cn -a -y
nps-ctl host add -e nps-america -d myapp.service.oaklight.cn -c <new-client> -T :<port>
```

### Upgrade NPS (non-destructive)

```bash
nps-ctl edge export --edge nps-america       # backup first
nps-ctl edge upgrade --edge nps-america -y   # preserves data files
```
