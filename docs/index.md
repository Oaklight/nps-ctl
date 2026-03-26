---
title: Home
hide:
  - navigation
---

# nps-ctl

A Python library and CLI tool for managing [NPS](https://github.com/djylb/nps) proxy servers.

!!! note
    This project targets [djylb/nps](https://github.com/djylb/nps), the actively maintained fork of the original [ehang-io/nps](https://github.com/ehang-io/nps) (unmaintained since 2021). The API is compatible with both forks, but djylb/nps is recommended.

## Features

- **API Client** — Type-safe Python wrapper for the NPS HTTP API
- **Multi-node Support** — Manage multiple NPS edge servers from a single interface
- **Cluster Sync** — Synchronize clients, tunnels, and hosts across edge nodes
- **NPC Deployment** — Install, configure, and manage NPC clients via SSH
- **CLI Tool** — Rich terminal interface for all operations
- **Minimal Dependencies** — Only requires [rich](https://github.com/Textualize/rich) for CLI output

## Quick Links

- [Installation](usage/installation.md)
- [Configuration](usage/configuration.md)
- [CLI Reference](usage/cli.md)
- [Library Usage](usage/library.md)
- [GitHub Repository](https://github.com/Oaklight/nps-ctl)
- [PyPI Package](https://pypi.org/project/nps-ctl/)
