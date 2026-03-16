---
title: 更新日志
---

# 更新日志

nps-ctl 的所有重要变更均记录于此。本项目遵循 [Keep a Changelog](https://keepachangelog.com/) 规范。

---

## v0.2.0 — 2026-03-16

### 新增

- **CI/CD 流水线**：GitHub Actions 工作流，包含 ruff 代码检查、ty 类型检查，以及 Python 3.11–3.13 的 pytest 测试
- **冒烟测试**：`nps_ctl`、`nps_ctl.api`、`nps_ctl.cli` 的包导入测试
- **双语文档**：英文 (`docs_en`) 和中文 (`docs_zh`) mkdocs 站点，包含完整的 API 和使用指南

### 变更

- 升级至 `actions/checkout@v5` 并在 CI 中启用 Node.js 24
- 新增 `ruff` 和 `ty` 工具；修复代码库中所有类型错误
- 重写 README，提供双语版本（`README_en.md`、`README_zh.md`），并新增 Makefile

### 修复

- 抑制 SOCKS 代理 socket monkey-patch 的 `ty` 类型错误

---

## v0.1.0 — 2026-02-09

**nps-ctl** 首次发布，用于管理 [NPS](https://github.com/djylb/nps) 代理服务器的 Python 库和命令行工具。

### 新增

- **NPSClient** — 单节点 NPS 服务器 API 客户端，支持 MD5 认证、SSL/TLS 和指数退避重试
- **NPSCluster** — 多节点集群管理器，支持广播操作、配置同步和速率限制
- **领域模块** — 独立的客户端、隧道和主机管理 API
- **SSH 部署** — 通过 SSH 在远程主机上安装/卸载 NPS 服务器和 NPC 客户端
- **代理支持** — HTTP/HTTPS 代理和 SOCKS5 代理（通过 PySocks），支持自动 SSH 隧道创建（`--auto-proxy`）
- **Rich CLI** — 嵌套子命令（`client`、`edge`、`tunnel`、`host`、`util`），带有 rich 表格输出和进度条
- **NPC 客户端管理** — `npc-list` 命令从独立的 `clients.toml` 获取和更新客户端配置
- **NPC 部署** — 推送 NPC 客户端二进制文件和配置到远程主机
- **结构化日志** — 自定义 NOTICE 日志级别、操作跟踪、`FlushingConsole` 确保通过代理时即时输出
- **并行操作** — 并发集群获取和客户端状态检查
- **速率限制** — 可配置的速率限制器，防止同步时压垮服务器
- **认证密钥生成** — CLI 命令生成 NPS API 认证密钥
- **镜像回退** — NPS 发行版下载自动回退到镜像源

### 链接

- PyPI：https://pypi.org/project/nps-ctl/0.1.0/
- GitHub：https://github.com/Oaklight/nps-ctl/releases/tag/v0.1.0
