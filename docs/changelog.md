---
title: Changelog
---

# Changelog

All notable changes to nps-ctl are documented here. This project follows [Keep a Changelog](https://keepachangelog.com/) conventions.

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
