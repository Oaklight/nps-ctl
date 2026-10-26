---
name: nps-ctl
version: 2.1.0
description: "NPS/NPC tunnel cluster management and health checking via nps-ctl. Use when the user asks to manage NPS edges, NPC clients, host mappings or TCP/UDP tunnels, to sync or back up edge configuration, to run the web dashboard, or to diagnose tunnel instability, dropped connections, truncated or corrupted uploads through a tunnel."
---

# nps-ctl — NPS/NPC Cluster Management

Manages NPS edge servers and NPC clients across a multi-region tunnel cluster,
and checks whether the tunnels are healthy.

```bash
pip install nps-ctl                  # from PyPI
pip install -e ~/projects/nps-ctl    # or editable from source
```

Config files:
- `~/.config/nps-ctl/edges.toml` — edge definitions (API URL, SSH host, auth)
- `~/.config/nps-ctl/clients.toml` — NPC client definitions (SSH host, edges, vkey)

Every command reads its topology from these two files. Never hard-code edge
names, hostnames or ports from memory — read the inventory first.

## Cluster inventory (do this first)

```bash
nps-ctl edge list            # configured edges, without contacting them
nps-ctl edge list --json     # stable inventory for scripts and agents
nps-ctl edge status          # contacts every edge; full client/host/tunnel inventory
```

The edge names in the examples below are illustrative; they are never the
inventory.

Target selection follows one rule across the tool:

- Read commands (`client list`, `edge status`, `tunnel list/status`,
  `host list/status`) default to every configured edge; `-e/--edge` narrows;
  `-a/--all` states the default explicitly. `check links` is the exception: it
  defaults to every configured NPC client and takes `-c`, not `-e`.
- Mutating commands (`host`/`tunnel` `add|del|edit`, `client del`) require an
  explicit target: `-e/--edge` for one edge or `-a/--all` for every edge.
  Omitting both is a usage error (exit 2), never a silent cluster-wide write.
- Edge IDs are edge-specific. `--id` always requires `-e`; locate by
  `-d/--domain`, `-r/--remark` or `-p/--port` to work across edges.
- `--json` exists on `edge list/status/primary`, `client list`,
  `tunnel list/status`, `host list/status` and all three `check` commands.
  It does not exist on `client status` or on any mutation.
- Exit codes: 0 success, 1 a remote operation failed or a check found a
  problem, 2 usage or targeting error.

## Edge (NPS server) management

```bash
nps-ctl edge list                             # offline inventory
nps-ctl edge status -e nps-america            # contact one edge
nps-ctl edge status --json                    # all edges, machine-readable
nps-ctl edge add nps-eu --api-url https://nps-eu.example.com --ssh-host cloud.deu1
nps-ctl edge install -e nps-europe -y         # install NPS on a node
nps-ctl edge upgrade -e nps-america -y        # upgrade binary, keep data
nps-ctl edge reconfig -e nps-asia -y          # rewrite nps.conf only
nps-ctl edge uninstall -e nps-europe -y
nps-ctl edge export -e nps-america -o backup.json
nps-ctl edge primary nps-asia                 # set the default sync source
nps-ctl edge primary                          # show it
```

`edge add` takes its auth key from `NPS_EDGE_AUTH_KEY` or a hidden prompt,
never from argv; pass `--no-auth-key` for modern-auth or unauthenticated edges.

Install and upgrade accept `--version`, `--release-url` and `--template`
(custom `nps.conf`). `--force-reinstall` is deprecated in favour of `upgrade`.

`edge status` exits 1 if any edge's inventory fetch fails, not only when the
edge is down.

### Sync between edges

```bash
nps-ctl edge sync                             # primary -> every other edge
nps-ctl edge sync -f nps-america -e nps-asia  # one source, one target
nps-ctl edge sync -t hosts                    # clients | tunnels | hosts | all
nps-ctl edge sync --prune -y                  # also delete extras on targets
nps-ctl edge sync --parallel -w 4 -q
```

`-e/--edge` and `--to` are the same option. `--prune` is destructive: it
deletes resources on targets that the source does not have, and aborts before
changing anything when the source cannot be read. Run it without `-y` first to
see the target list.

## Client (NPC) management

```bash
nps-ctl client list                           # every client, from the edges
nps-ctl client list -e nps-america --json
nps-ctl client list -e nps-america --update --dry-run   # preview changes
nps-ctl client list -e nps-america --update             # write them to clients.toml
nps-ctl client add --name new --ssh-host user@host --edges nps-asia --push -y
nps-ctl client push                           # create/refresh clients on their edges
nps-ctl client push -c cloud.deu1 --update    # re-sync vkeys from clients.toml
nps-ctl client status --parallel              # SSHs to every client
nps-ctl client restart -c cloud.deu1
nps-ctl client install -c cloud.deu1 --version v0.26.0 -y
nps-ctl client upgrade -c cloud.deu1 -y
nps-ctl client reconfig -c cloud.deu1 -y      # rewrite server addresses
nps-ctl client uninstall -c cloud.deu1 -y
nps-ctl client del -r cloud.deu1 -a -y        # by remark, from every edge
nps-ctl client del --id 12 -e nps-asia -y     # by ID, one edge
```

`client add` generates a vkey unless `--vkey` is given and defaults to
`--conn-type tls`; `client list --update` (and `--dry-run`) require `-e`, since
it writes what one edge knows; `--push` creates the client on its edges in the same step.
`client push --dry-run` shows what would change.

`client status` reports NPC version and service state per host. Without
`--parallel` it walks the clients one by one.

## Host mappings (HTTP proxy)

```bash
nps-ctl host list                             # all edges
nps-ctl host list --matrix                    # domain-by-edge presence matrix
nps-ctl host status -e nps-america --json     # clients/hosts/ports per edge
nps-ctl host add -e nps-america -d myapp.service.oaklight.cn -c cloud.usa2 -T :8080
nps-ctl host add -a -d myapp.service.oaklight.cn -c cloud.usa2 -T :8080
nps-ctl host edit -e nps-america --id 42 --new-target :9090
nps-ctl host edit -d old.service.oaklight.cn -a --new-domain new.service.oaklight.cn -y
nps-ctl host del -d myapp.service.oaklight.cn -a -y
nps-ctl host del --id 42 -e nps-america -y
```

`--auth "user=pass"` or `"user1=pass1,user2=pass2"` sets HTTP Basic Auth;
pass `--auth ""` on `host edit` to clear it. If a password contains a comma,
separate entries with newlines instead.

**`host edit` cannot change the client.** To move a service to another NPC
client, delete the mapping and add it again.

The target is written in NPS's short form (`:8080` means `127.0.0.1:8080` on the
client); `host list` prints the resolved form.

## TCP/UDP tunnels

```bash
nps-ctl tunnel status                         # tunnels/running/ports per edge
nps-ctl tunnel list -t socks5 -e nps-america
nps-ctl tunnel add -e nps-america -c homelab.oasis -t tcp -T :22 -p 30022
nps-ctl tunnel add -a -c homelab.oasis -t httpProxy -T :8081 -p 30080 --auth "u=p"
nps-ctl tunnel edit --id 5 -e nps-america --new-target :2222 --new-port 30023
nps-ctl tunnel start --id 5 -e nps-america
nps-ctl tunnel stop --id 5 -e nps-america
nps-ctl tunnel del --id 5 -e nps-america -y
nps-ctl tunnel del -p 30022 -t tcp -a -y      # locate by port+type across edges
```

Tunnel counts include `mixProxy`, where djylb/nps stores socks5 and httpProxy
tunnels. `tunnel list -t socks5` and `-t httpProxy` match those rows;
`-t mixProxy` matches both.

`tunnel start/stop` take only `--id` plus `-e`; there is no bulk start.

## Health checks

Three layers, from read-only to intrusive. All take their topology from the
same two config files.

### Link health (read-only)

```bash
nps-ctl check links                    # every NPC client, last 6 hours
nps-ctl check links -c cloud.usa2 --since 24h --json
```

One SSH session per client reads the established sockets, the addresses the
configured edges resolve to, and the tail of the NPC log (`/var/log/npc.log`,
`--log-path` and `--tail-bytes` to change). The report has one row per
(client, edge):

| Column | Meaning |
|--------|---------|
| Outages | Bridge outages that started in the window |
| Median, Max | Outage length |
| Down | Share of the window the link was down |
| Period | Median gap between outage starts, `*` when at least 60% of the gaps lie within 15% of it |

An outage starts at the last answered ping, not when NPC noticed, and is
attributed to an edge by the `Start server` line that follows the timeout. A
link can therefore read "down 5% of the time" while its log looks quiet. When
several of a client's bridges time out together, each keeps its own outage
(oldest-first pairing); two bridges that stop answering in the same second share
a stamp, and the second one's outage is opened from that shared stamp when its
own `Start server` line arrives, or from that line itself if it comes after the
drop is over. An outage whose server matches no configured bridge is reported as
`outages_unattributed` rather than dropped.

`--fail-on warn` (default) or `error` sets the level that makes the exit
code 1. A link that is down, an unreachable client, or three or more outages
in the window all fail the command.

Interpretation: one edge flapping from every client means the edge or the path
to it; one client flapping against every edge means that client's network.

### Integrity probe (creates temporary objects)

```bash
nps-ctl check probe -e nps-america2 -c cloud.usa2 --dry-run
nps-ctl check probe -e nps-america2 -c cloud.usa2 --size 1M --count 50 -y
nps-ctl check probe -e nps-america2 -c cloud.usa2 --mode slow --chunk-kb 4 --gap-ms 10 -y
```

A run starts a hash-echo service on the client host, adds a host mapping on
the chosen edge for a throwaway domain
(`nps-ctl-check-<token>.nps-ctl-check.invalid`), sends a client-local baseline
without the tunnel, then sends the same load from the edge host through NPS,
and removes both temporary objects.

Each request body is derived from the run token and the request index, so no
two bodies match. The echo answers with length, SHA-256 and one hash per
64 KiB block; a mismatch proves truncation, extension or bytes spliced in from
another concurrent request, and the block hashes locate it. A failing baseline
makes the tunnel numbers meaningless, and the command says so instead of
blaming the path.

`--mode slow` with `--chunk-kb` / `--gap-ms` imitates a slow uploader such as a
language-model client sending a long conversation.

`--json` never prompts: `probe` and `stress` print one JSON document, so pass
`-y` (or `--dry-run`) or they exit 2 with a JSON error. Without `--json` the
confirmation prompt goes to stderr. Ctrl-C cleans up and exits 130.

### Stress profiles (creates temporary objects)

```bash
nps-ctl check stress -e nps-europe -c cloud.usa2 --profile soak --duration 30m -y
nps-ctl check stress -e nps-america2 -c cloud.usa2 --profile ladder -y
```

| Profile | What it sends |
|---------|---------------|
| `smoke` | 30 requests of 256 KiB at concurrency 4 |
| `ladder` | 64 KiB and 1 MiB at concurrency 1, 2, 4, 8, 16 |
| `slow` | Slow uploaders: 16 KiB every 20 ms, then 4 KiB every 10 ms |
| `churn` | 400 small requests at concurrency 16 |
| `soak` | Steady load for `--duration` (default 10m) |

When requests fail, the report correlates them with the outages in the
client's NPC log and prints both the share of failures inside outage windows
and the share of the run those windows cover. "All failures inside outages
that cover 9% of the run" is evidence for the link; failures with no outage
anywhere near them are evidence against it.

### Leftover mappings

```bash
nps-ctl check leftovers                      # list, every edge
nps-ctl check leftovers --delete -a -y       # remove them
```

A run killed outright cannot clean up. `check leftovers` lists mappings carrying
the check's own remark and `.nps-ctl-check.invalid` domain, and removes them
through the same verified delete path. An edge that does not answer is reported
and the others still run. Leftovers matter beyond a wasted row: a mapping
present on one edge only reads as drift in `edge status`.

### What a check run leaves behind

Nothing, when it works. The host mapping and the echo service are removed on
exit, including after a failure part way through setup. Cleanup is verified:
the mapping is listed again after the delete, and the echo is stopped by a
handle the command created. A `cleanup_failed` finding names what is left and
makes the exit code 1 — read it and finish the removal by hand.

Runtime requirements: `python3` on both the edge host and the client host.
No credentials beyond the SSH access already configured for the edges and
clients.

Do not schedule `probe` or `stress`. They change the edge temporarily; keep
`check links` on a timer instead.

## Web dashboard

`nps-ctl web` is read-only by default. `--allow-writes` enables add/sync and
edit/delete actions on one edge at a time, behind a review step, a per-process
CSRF token, same-origin and Host checks, and a single-writer lock.

```bash
NPS_WEB_PASSWORD='...' nps-ctl web --username admin --allow-writes
nps-ctl util hash-password                    # PBKDF2 hash, never the raw password
nps-ctl web --users-file web-users.toml --allow-writes
nps-ctl web --host 127.0.0.1 --port 8080
```

Binds to `127.0.0.1:8080` by default. A non-loopback bind without credentials
requires `--insecure` and stays read-only; writes always require authentication
on a network bind. Terminate TLS in front of the loopback listener —
`deploy/web` ships a systemd unit and a Caddy site block. `[[users]]` entries in
the users file carry `name`, `password_hash` and `role` (`operator` writes,
`viewer` reads).

## Utilities

```bash
nps-ctl util generate-auth-key [LENGTH]       # default 43 characters
nps-ctl util hash-password --iterations 260000
```

## Common tasks

### Migrate a service to a different client

```bash
nps-ctl host del -d myapp.service.oaklight.cn -a -y
nps-ctl host add -a -d myapp.service.oaklight.cn -c <new-client> -T :<port>
```

### Rotate a client's verify key

Edit the vkey in `clients.toml`, then re-push it; `--update` syncs the key from
the file to the edges.

```bash
nps-ctl client push -c cloud.deu1 --update --dry-run
nps-ctl client push -c cloud.deu1 --update -y
```

### Upgrade an edge without losing data

```bash
nps-ctl edge export -e nps-america -o backup.json   # back up first
nps-ctl edge upgrade -e nps-america -y              # preserves data files
nps-ctl edge status -e nps-america                  # confirm
```

### Diagnose flapping or broken uploads

```bash
nps-ctl check links --since 24h                     # is a bridge dropping?
nps-ctl check links -c <client> --since 2h          # one client, every edge
nps-ctl check probe -e <edge> -c <client> -y        # does data survive the trip?
nps-ctl check stress -e <edge> -c <client> --profile soak --duration 30m -y
```

A periodic outage pattern, seen from every client on one edge, points at the
edge or the path to it. If `check links` is clean but `check probe` shows
damaged bodies, the fault is in the data path rather than in connect/disconnect
events, and the profile that reproduces it narrows the trigger (body size,
concurrency, or slow chunked uploads).

### Add a new edge

```bash
nps-ctl edge add nps-eu --api-url https://nps-eu.example.com --ssh-host cloud.deu1
nps-ctl edge install -e nps-eu -y
nps-ctl edge sync -f <existing-edge> -e nps-eu      # copy host/tunnel config
nps-ctl client push -e nps-eu                       # add the clients that list it
```

Remember to list the new edge in the relevant clients' `edges` in
`clients.toml`; `client push` only pushes to edges a client already names.

## Command index

| Group | Subcommands |
|-------|-------------|
| `edge` | `list`, `status`, `add`, `install`, `upgrade`, `reconfig`, `uninstall`, `primary`, `sync`, `export` |
| `client` | `list`, `add`, `push`, `del`, `status`, `install`, `upgrade`, `reconfig`, `restart`, `uninstall` |
| `host` | `list`, `status`, `add`, `edit`, `del` |
| `tunnel` | `list`, `status`, `add`, `edit`, `del`, `start`, `stop` |
| `check` | `links`, `probe`, `stress`, `leftovers` |
| `util` | `generate-auth-key`, `hash-password` |
| `web` | dashboard server (read-only unless `--allow-writes`) |

## Safety

- `edge sync --prune`, `edge uninstall`, `client uninstall`, and every `del`
  are destructive. Run them without `-y` first, or with `--dry-run` where the
  command offers one, and state the resolved target list before confirming.
- Every mutation prints the resolved targets; if the printed list is not what
  the user asked for, stop rather than confirming.
- `check probe` / `check stress` create a host mapping on a live edge. Prefer
  `--dry-run`, then run them on the edge and client the user named, and confirm
  `cleanup_problems` is empty afterwards.
