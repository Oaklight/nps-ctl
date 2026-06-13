---
title: Changelog
---

# Changelog

All notable changes to nps-ctl are documented here. This project follows [Keep a Changelog](https://keepachangelog.com/) conventions.

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
