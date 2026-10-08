# Quick Start

Get nps-ctl configured and running in 5 minutes.

## Step 1 — Create a configuration file

nps-ctl reads its configuration from a TOML file. The default search paths
are:

1. `./config/edges.toml`
2. `~/.config/nps-ctl/edges.toml`
3. `/etc/nps-ctl/edges.toml`

Create `~/.config/nps-ctl/edges.toml` with at least one edge:

```toml
auth_crypt_key = "your_16char_key"
public_vkey = "your_public_vkey"

[web]
username = "admin"
password = "your_password"

[[edges]]
name = "nps-main"
api_url = "https://nps.example.com"
auth_key = "your_auth_key"
region = "US"
ssh_host = "cloud.example"
```

| Field | Description |
|-------|-------------|
| `auth_crypt_key` | 16-character encryption key shared by NPS and NPC |
| `public_vkey` | Public verify key for NPC client registration |
| `[web]` | NPS web dashboard credentials (used by deploy commands) |
| `[[edges]]` | One block per NPS server node you want to manage |
| `name` | Unique identifier for this edge |
| `api_url` | NPS server API URL (with HTTPS) |
| `auth_key` | API authentication key configured on the NPS server |
| `region` | Human-readable region label |
| `ssh_host` | SSH host alias for deployment commands |

!!! note
    You can define multiple `[[edges]]` blocks to manage a multi-node
    cluster from a single config file.

## Step 2 — Check edge status

Verify that nps-ctl can reach your NPS server:

```bash
nps-ctl edge status
```

Example output:

```
           NPS Edge Status
┏━━━━━━━━━━━━┳━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━┓
┃ Edge       ┃ Region ┃ API URL                     ┃ Status     ┃
┡━━━━━━━━━━━━╇━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━┩
│ nps-main   │ US     │ https://nps.example.com     │ ✓ Online   │
└────────────┴────────┴─────────────────────────────┴────────────┘
```

## Step 3 — List clients

See all NPC clients registered on your edge:

```bash
nps-ctl client list
```

Example output:

```
┏━━━━┳━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━┳━━━━━━┓
┃ ID ┃ Remark      ┃ VKey          ┃ Status       ┃ Conn ┃
┡━━━━╇━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━╇━━━━━━┩
│ 1  │ my-server   │ abc123def456  │ Connected    │    3 │
│ 2  │ home-nas    │ xyz789uvw012  │ Disconnected │    0 │
└────┴─────────────┴───────────────┴──────────────┴──────┘
```

## Step 4 — Add a host mapping

Route a domain through NPS to a backend service running on one of your NPC
clients:

```bash
nps-ctl host add -d app.example.com -c my-server -T :8080
```

This creates an HTTP host mapping on all edges, forwarding requests for
`app.example.com` to port 8080 on the NPC client named `my-server`.

## Step 5 — Verify the host mapping

List all host mappings to confirm it was created:

```bash
nps-ctl host list
```

You should see `app.example.com` in the output, mapped to the correct client
and target port.

## Next steps

- **[Configuration](../get-started/configuration.md)** — full reference for
  `edges.toml` fields, NPC client definitions, and proxy settings
- **[CLI Reference](../guides/cli.md)** — complete documentation for all
  command groups (`edge`, `client`, `host`, `tunnel`, `util`)
- **[Library Usage](../guides/library.md)** — use `NPSCluster` and
  `NPSClient` in your own Python scripts
