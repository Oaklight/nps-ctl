---
title: Changelog
---

# Changelog

All notable changes to nps-ctl are documented here. This project follows [Keep a Changelog](https://keepachangelog.com/) conventions.

---

## [Unreleased]

### Added

- **`check links`**: report per-(client, edge) bridge health from each NPC client's established sockets and log, without generating traffic. Outages start at the last answered ping, are attributed to an edge through the following `Start server` line, and a near-constant interval between them is flagged as periodic
- **`check probe` / `check stress`**: push self-verifying bodies through one edge's tunnel. A temporary hash-echo service runs on the client, a throwaway `nps-ctl-check-*.nps-ctl-check.invalid` mapping points at it on the chosen edge, and every answer is compared with what was sent, so truncation, damage and bytes spliced in from another request are all detected. A client-local run without the tunnel is the baseline
- **Stress profiles**: `smoke`, `ladder` (concurrency x body size), `slow` (chunked uploads), `churn` (connection churn) and `soak` (steady load for `--duration`), with failures matched against the outages in the client's NPC log
- **`check leftovers`**: list, and with `--delete` remove, host mappings left by a check run that was killed before it could clean up. Only rows carrying the check's own remark and domain are touched

### Fixed

- `check links` keeps one outage per bridge when several of a client's bridges time out together, instead of merging them and crediting one edge with another's downtime
- An outage whose server matches no configured bridge is reported as `outages_unattributed` rather than disappearing from every row
- A host mapping whose create returned no id is found again by domain and remark and removed, instead of being orphaned silently
- `check probe`/`stress --json` print a single JSON document: they no longer prompt on stdout, and without `-y` they exit 2 with a JSON error. The confirmation prompt elsewhere goes to stderr
- A check run interrupted with Ctrl-C reports what cleanup did and exits 130 instead of printing a traceback
- Getting the NPS HTTP proxy port on the edge needs only `grep`; a missing `python3` on the edge no longer blocks a run
- A bridge that repeats its ping timeout while still down reports the same last-answered ping, and the repeat now extends its outage instead of opening a phantom that surfaced as an unattributable outage
- `check leftovers` reports an unreachable edge in `errors` and carries on with the edges that answered, instead of a traceback and empty `--json` output
- A create refused before any write no longer claims that a mapping "may still be on" the edge; only a write that reached the edge can leave a row
- Two bridges that stop answering in the same second no longer lose one edge's downtime: the folded outage is opened when that bridge's `Start server` line arrives, and a reconnect that matches no open outage is dropped instead of closing another bridge's window

---

## v0.9.1 — 2026-10-21

### Added

- **Docker images**: `oaklight/nps-ctl` is published on Docker Hub — a Python image (`latest`, `latest-python`, `<version>`, `<version>-python`) and Nuitka binary images (`<version>-alpine`, `<version>-glibc`) for amd64 and arm64. The release workflow builds and pushes them, and a smoke test runs each image's `--version`
- `docker/`: Dockerfiles, entrypoints that start the dashboard on `0.0.0.0:8080` and require authentication, Compose files, and a `.dockerignore` that keeps configuration and credentials out of images

### Changed

- Linux Nuitka artifacts are named by libc — `linux-x86_64-glibc`, `linux-arm64-musl` — so the artifact name states what it links against (#75)
- The glibc binary images build on `ubuntu:24.04` and the Nuitka Linux runners are pinned to `ubuntu-24.04`, keeping the base at least as new as the libc the binary needs

### Fixed

- `edge sync` compares tunnel identity by canonical mode, so a source reporting `socks5`/`httpProxy` matches targets that store `mixProxy` (#72)
- Docker image builds stage the downloaded binary by prefix, so images can be built from tags that predate the libc-suffix rename (#77)

### Credits

- Thanks to [@dannyward630](https://github.com/dannyward630) for the partial-failure exit codes in `client status` and `edge sync` (#35)

---

## v0.9.0 — 2026-10-21

### Added

- **`edge primary [NAME]`** and an optional top-level `primary` in `edges.toml`; `edge sync` now defaults to the primary when `-f/--from` is omitted (#67)
- **`edge add NAME --api-url URL`**: append an edge with a comment-preserving, atomic `edges.toml` edit; the auth key comes from `NPS_EDGE_AUTH_KEY` or a hidden prompt, never argv (#67)
- **`client add --push`**: write `clients.toml` and push just the new client to its configured edges in one step (#68)
- **Web actions behind `--allow-writes`**: sync with optional prune, add client/tunnel/host, add edge, and edit/delete clients, tunnels and hosts on one edge (#69)
- **Multi-user dashboard auth**: `--users-file` with PBKDF2 password hashes and `viewer`/`operator` roles; `nps-ctl util hash-password` generates hashes without echoing the password
- **`deploy/web`**: systemd unit and Caddy site block for `nps-admin.oaklight.top`
- **`tunnel status`**: per-edge reachability, online/total clients, tunnel count, running count, and distinct server-port count, with `-e/--edge`, `-a/--all`, `--json`, and `--no-color`
- `edge status` supports `-e/--edge` and `-a/--all`
- Shared status rendering helpers used by `edge status`, `host status`, and `tunnel status`
- `get_all_tunnels()` accepts `edge_names`; modern tunnel `ports` values are normalized into `TunnelInfo.Ports`
- Tunnel listings and inventory counts query NPS's `mixProxy` mode, where djylb/nps stores socks5 and httpProxy tunnels
- The web dashboard overview is driven by the shared status collector and exposes `ok`/`partial`

### Changed

- **`edge sync --prune`** deletes clients, tunnels and hosts on targets that are absent from the source (opt-in, confirmation required); source fetches are strict so an unreadable source aborts before any change
- `client push` and `client add --push` now exit 1 when any edge push fails, and match existing clients by verify key first, then remark
- The web dashboard remains read-only by default; with `--allow-writes`, `viewer` users are still limited to reads and the server enforces the role on every write endpoint
- The web "Add edge" action reloads `edges.toml` in place, so a new edge appears without restarting the process
- **`edge status`** now fetches tunnels by default and reports `Hosts (ports)` and `Tunnels (running, ports)`; it exits 1 on any client, host, or tunnel fetch failure
- `edge status` JSON adds `clients_ok`, `hosts_ok`, `tunnels_ok`, `tunnels_total`, `tunnels_running`, `tunnel_ports`, and tunnel totals; unrequested resources are `null`
- `GET /api/overview` now defines `online` as client-list liveness, adds `ok`/`partial`, and reports unavailable counts as `null` instead of `0`
- Status footers add an `N partial` count when a selected edge returned a partial result; `host status` error lines are now prefixed with `✗`
- `totals.ok`, `totals.partial`, and `totals.failed` now partition the selected edges instead of counting a client-list failure in both `failed` and `partial`; `summary.offline` remains the client-liveness counter
- Tunnel port ranges are parsed like the server's `common.GetPorts`: comma-separated, with reversed ranges swapped
- `tunnel list -t/--type` now filters across all edges (previously it was ignored without `-e`) and resolves `socks5`/`httpProxy` to `mixProxy`; `mixProxy` is accepted by the list/del/edit type filters
- Tunnel listings filter and dedupe locally, so exact-type filters stay correct when a server ignores the `type` parameter
- `tunnel del`/`tunnel edit` port locators match the tunnel's `Port` or any port in its `Ports` range
- `tunnel edit` preserves a proxy tunnel's socks5/HTTP flags instead of clearing both on djylb/nps

### Fixed

- `edge sync` error paths no longer raise `TypeError` for an unknown source or target edge; they print an error and exit 1
- `edges.toml` edits are atomic, preserve the file mode, follow symlinks, and are re-parsed and verified before writing
- The dashboard rejects DNS-rebinding `Host` headers when no auth is configured, sends `frame-ancestors 'none'`/`X-Frame-Options: DENY`, and keeps the documented `--insecure` read-only network mode reachable
- `edge add` and the confirmation prompt exit cleanly with status 2 instead of an `EOFError` when there is no TTY

---

## v0.8.0 — 2026-10-18

### Added

- **`host status`**: per-edge reachability, online/total clients, host-mapping count, and distinct target-port count, with `-e/--edge`, `-a/--all`, `--json`, and `--no-color`
- Shared edge status collector backing both `host status` and `edge status`, with `None`/`null` counts for failed fetches
- Cluster subset fetching: `get_all_clients()` and `get_all_hosts()` accept `edge_names`, and an unknown edge reports a clean `Edge '<name>' not found` error

### Changed

- **`edge status`** now reports client, host, and target-port counts alongside reachability; it exits 1 on any client or host fetch failure, not only unreachable edges
- `edge status` JSON keeps `summary: {configured, online, offline}` and adds per-edge counts plus a top-level `totals`
- `client status` and `edge sync` exit 1 when any checked client or target edge fails, with an ok/failed summary (#35) — thanks to [@dannyward630](https://github.com/dannyward630)

---

## v0.7.0 — 2026-10-08

### Added

- **HTTP Basic Auth for host mappings**: `--auth` flag on `host add` and `host edit` sets native NPS basic auth (format: `"user=pass"` or `"user1=pass1,user2=pass2"`; empty string to clear)
- Auth status column in `host list` output
- Modern API transport layer: auto-detection of djylb/nps v0.35.0 `/api/*` REST endpoint, Bearer token auth with thread-safe refresh — preparation for future modern API migration

### Fixed

- **Edge install silent failure**: `nps-ctl edge install` now detects and recovers when upstream `nps install` exits 0 despite failing to deploy (pre-copies binary, creates fallback `Nps.service`, hard-fails verification)
- **Edge upgrade missing service file**: `edge upgrade` recreates the systemd service file if it was lost (e.g. after VPS reimage)
- `HeaderChange` field name in `host edit` — was silently dropping header change rules on edit

### Changed

- `which` replaced with POSIX `command -v` in deploy scripts for portability
- Pinned dev tool versions: ruff 0.15.20, ty 0.0.54

---

## v0.6.0 — 2026-06-13

### Added

- **Cross-edge locators** for `tunnel`/`host` del/edit: locate by remark, domain, or port+type across all edges instead of requiring edge-specific IDs
- `-T` short flag for `--target` (used in `host add` and `tunnel add`)
- `--target` / `-T` validation: tcp/udp `tunnel add` now requires target address
- Shared argument factory functions in `helpers.py` for consistent parameter definitions

### Fixed

- **`-v/--verbose` bug (P0)**: subcommand-level `-v` was silently ignored due to `dest="deploy_verbose"` mismatch — affected 9 subcommands
- Unused `ty: ignore` suppression comment in `base.py`

### Changed

- **Short flag cleanup**: `-c` reserved for `--client` (global `--config` no longer has short flag), `-t` reserved for `--type` (`--template` and `--target` use long flags or `-T`)
- **edge sync dest unified**: `dest="target"` → `dest="edge"` for consistency
- `client del --name` renamed to `-r/--remark` (`--name` kept as hidden alias)
- Edit commands use `--new-*` prefixed args to separate locator from value semantics
- Multi-match safety: del/edit commands error when multiple matches found, requiring `--id` for precision
- `--client` help text unified across subcommands

---

## v0.5.2 — 2026-06-03

### Added

- **Multi-architecture support**: Deploy scripts now auto-detect CPU architecture via `uname -m` and download the correct binary (amd64, arm64, arm). Previously hardcoded to amd64, which broke deployment on ARM hosts like armv7l.
- `get_download_urls()` and `get_npc_download_urls()` accept an `arch` parameter for explicit architecture selection

### Fixed

- **Edge upgrade data preservation**: `edge upgrade` now backs up and restores data files (clients.json, hosts.json, tasks.json, global.json) instead of wiping them (closes #9)
- **Edge upgrade template path**: Fixed template filename not being appended when resolving upgrade config path

---

## v0.5.1 — 2026-06-03

### Fixed

- **Sudo support for NPC deploy**: All NPC operations (install, uninstall, reconfig, restart) now prepend `sudo` when the SSH user is non-root, fixing permission denied errors on homelab machines
- **Reconfig parameter loss**: Added `systemctl daemon-reload` after `npc uninstall` in install/uninstall/reconfig scripts to ensure clean service file removal before reinstall
- **NPS config template**: Split `bridge_port` into `bridge_tcp_port` and `bridge_tls_port` to match NPS v0.34.x config format

### Changed

- Bumped default NPS/NPC version from v0.34.1 to v0.34.7

---

## v0.5.0 — 2026-05-28

### Fixed

- Show which edge is used when `edge export` omits `-e`
- Validate `--port` required for tcp/udp `tunnel add`
- Require `-e` when `client list --update` or `--dry-run`
- Show edge header in single-edge list output

### Changed

- Added pre-commit config and smoke-test CI job; switched to dynamic version

---

## v0.4.0 — 2026-05-15

### Added

- **Broadcast tunnel add**: `tunnel add` broadcasts to all edges when `-e` is omitted
- **CLI version flag**: `--version` / `-V` flag
- **CRUD commands**: `delete`, `edit`, `start`/`stop` for client, host, and tunnel

### Fixed

- SOCKS proxy cleanup and timeout type validation

---

## v0.3.0 — 2026-04-20

### Added

- **Reconfig and upgrade**: `client reconfig`, `client upgrade`, `edge reconfig`, `edge upgrade` subcommands
- **SSH user and HTTP proxy**: `ssh_user` and `http_proxy` fields in client config for NPC deployment behind restricted networks

### Fixed

- ty 0.0.28 type checker compatibility

---

## v0.2.0 — 2026-03-16

### Added

- **CI/CD pipeline**: GitHub Actions workflow with ruff linting, ty type checking, and pytest across Python 3.11–3.13
- **Smoke tests**: package import tests for `nps_ctl`, `nps_ctl.api`, and `nps_ctl.cli`
- **Bilingual documentation**: English (`docs_en`) and Chinese (`docs_zh`) mkdocs sites with full API and usage guides

### Changed

- Upgraded to `actions/checkout@v5` and enabled Node.js 24 for CI
- Added `ruff` and `ty` tooling; fixed all type errors across the codebase
- Rewrote README with bilingual versions (`README_en.md`, `README_zh.md`) and added Makefile

### Fixed

- Suppressed `ty` type error for SOCKS proxy socket monkey-patch

---

## v0.1.0 — 2026-02-09

Initial release of **nps-ctl**, a Python library and CLI tool for managing [NPS](https://github.com/djylb/nps) proxy servers.

### Added

- **NPSClient** — API client for a single NPS server with MD5 auth, SSL/TLS, and exponential backoff retry
- **NPSCluster** — Multi-node cluster manager with broadcast operations, config syncing, and rate limiting
- **Domain modules** — Separate client, tunnel, and host management APIs
- **SSH deployment** — Install/uninstall NPS servers and NPC clients on remote hosts via SSH
- **Proxy support** — HTTP/HTTPS proxy and SOCKS5 proxy (via PySocks) with auto SSH tunnel creation (`--auto-proxy`)
- **Rich CLI** — Nested subcommands (`client`, `edge`, `tunnel`, `host`, `util`) with rich table output and progress bars
- **NPC client management** — `npc-list` command to fetch and update client configs from separate `clients.toml`
- **NPC deployment** — Push NPC client binaries and configs to remote hosts
- **Structured logging** — Custom NOTICE level, operation tracking, `FlushingConsole` for immediate output through proxies
- **Parallel operations** — Concurrent cluster fetching and client status checks
- **Rate limiting** — Configurable rate limiter to prevent overwhelming servers during sync
- **Auth key generation** — CLI command to generate NPS API authentication keys
- **Mirror fallback** — Automatic fallback to mirror for NPS release downloads

### Links

- PyPI: https://pypi.org/project/nps-ctl/0.1.0/
- GitHub: https://github.com/Oaklight/nps-ctl/releases/tag/v0.1.0
