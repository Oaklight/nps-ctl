---
title: Home
hide:
  - navigation
---

# nps-ctl

**A Python CLI and library for managing NPS proxy server clusters.**

[![PyPI version](https://img.shields.io/pypi/v/nps-ctl)](https://pypi.org/project/nps-ctl/)
[![Python version](https://img.shields.io/pypi/pyversions/nps-ctl)](https://pypi.org/project/nps-ctl/)
[![License](https://img.shields.io/github/license/Oaklight/nps-ctl)](https://github.com/Oaklight/nps-ctl)
[![CI](https://img.shields.io/github/actions/workflow/status/Oaklight/nps-ctl/ci.yml)](https://github.com/Oaklight/nps-ctl/actions/workflows/ci.yml)

!!! note "Upstream NPS fork"
    nps-ctl targets the [djylb/nps](https://github.com/djylb/nps) fork, which
    is the actively maintained continuation of the original NPS project. Make
    sure your NPS server instances are running this fork.

## Features

- **Multi-edge cluster management** — control multiple NPS server nodes from a single CLI, with per-edge or broadcast operations.
- **Rich CLI and Python API** — full-featured command-line interface powered by Rich, plus a Python library for scripting and automation.
- **SSH deployment of NPS/NPC** — install, upgrade, and manage NPS server and NPC client binaries on remote hosts over SSH.
- **Cross-edge sync and broadcast** — add or remove hosts and tunnels across all edges in one command.
- **HTTP Basic Auth for hosts** — configure authentication on HTTP host mappings directly from the CLI.
- **Minimal dependencies** — only requires `rich`; no heavyweight frameworks.

## Get Started

Install from PyPI:

```bash
pip install nps-ctl
```

Then configure your edges in `~/.config/nps-ctl/edges.toml` and start managing your cluster:

```bash
nps-ctl edge list
nps-ctl client list
nps-ctl host list
```

- **[Installation](get-started/installation.md)** — install nps-ctl and set up your environment
- **[Quick Start](get-started/quickstart.md)** — configure your first edge and run basic commands
- **[CLI Reference](guides/cli.md)** — complete reference for all command groups
- **[Python Library](guides/library.md)** — use nps-ctl as a library in your own scripts
