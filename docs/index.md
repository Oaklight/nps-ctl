---
title: 首页
hide:
  - navigation
---

# nps-ctl

**用于管理 NPS 代理服务器集群的 Python CLI 和库。**

[![PyPI version](https://img.shields.io/pypi/v/nps-ctl)](https://pypi.org/project/nps-ctl/)
[![Python version](https://img.shields.io/pypi/pyversions/nps-ctl)](https://pypi.org/project/nps-ctl/)
[![License](https://img.shields.io/github/license/Oaklight/nps-ctl)](https://github.com/Oaklight/nps-ctl)
[![CI](https://img.shields.io/github/actions/workflow/status/Oaklight/nps-ctl/ci.yml)](https://github.com/Oaklight/nps-ctl/actions/workflows/ci.yml)

!!! note "上游 NPS 分支"
    nps-ctl 针对 [djylb/nps](https://github.com/djylb/nps) 分支开发，该分支是原始 NPS 项目的活跃维护延续版本。请确保你的 NPS 服务器实例运行的是此分支。

## 功能特性

- **多边缘节点集群管理** — 通过单个 CLI 控制多个 NPS 服务器节点，支持针对单个边缘节点或广播操作。
- **丰富的 CLI 和 Python API** — 基于 Rich 的全功能命令行界面，以及用于脚本和自动化的 Python 库。
- **SSH 部署 NPS/NPC** — 通过 SSH 在远程主机上安装、升级和管理 NPS 服务端和 NPC 客户端。
- **跨边缘节点同步和广播** — 一条命令即可在所有边缘节点上添加或删除主机映射和隧道。
- **HTTP 主机映射基本认证** — 直接通过 CLI 为 HTTP 主机映射配置身份验证。
- **最少依赖** — 仅需 `rich`，无重量级框架。

## 快速开始

从 PyPI 安装：

```bash
pip install nps-ctl
```

然后在 `~/.config/nps-ctl/edges.toml` 中配置你的边缘节点，即可开始管理集群：

```bash
nps-ctl edge list
nps-ctl client list
nps-ctl host list
```

- **[安装](get-started/installation.md)** — 安装 nps-ctl 并配置环境
- **[快速入门](get-started/quickstart.md)** — 配置你的第一个边缘节点并运行基本命令
- **[CLI 参考](guides/cli.md)** — 所有命令组的完整参考
- **[Python 库](guides/library.md)** — 在你自己的脚本中将 nps-ctl 作为库使用
