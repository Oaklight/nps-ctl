---
title: 更新日志
---

# 更新日志

nps-ctl 的所有重要变更均记录于此。本项目遵循 [Keep a Changelog](https://keepachangelog.com/) 规范。

---

## 未发布

### 新增

- **`tunnel status`**：按边缘节点显示可达性、客户端在线数/总数、隧道数、运行数与不同服务端端口数，支持 `-e/--edge`、`-a/--all`、`--json` 和 `--no-color`
- `edge status` 支持 `-e/--edge` 和 `-a/--all`
- 供 `edge status`、`host status` 和 `tunnel status` 共用的状态渲染辅助函数
- `get_all_tunnels()` 支持 `edge_names`；现代 API 的隧道 `ports` 会归一化到 `TunnelInfo.Ports`
- 隧道列表与清单统计会查询 NPS 的 `mixProxy` 模式，djylb/nps 用它存储 socks5 与 httpProxy 隧道
- Web 仪表盘概览改用共享状态收集器，并暴露 `ok`/`partial`

### 变更

- **`edge status`** 默认抓取隧道，并显示 `Hosts (ports)` 与 `Tunnels (running, ports)`；任一客户端、域名映射或隧道抓取失败时退出 1
- `edge status` JSON 新增 `clients_ok`、`hosts_ok`、`tunnels_ok`、`tunnels_total`、`tunnels_running`、`tunnel_ports` 及隧道汇总；未请求的资源为 `null`
- `GET /api/overview` 的 `online` 现在表示客户端列表抓取成功，新增 `ok`/`partial`，不可用的数量以 `null` 而非 `0` 返回
- 存在部分结果时，状态汇总行会附加 `N partial`；`host status` 的错误行现在以 `✗` 为前缀
- `totals.ok`、`totals.partial` 与 `totals.failed` 现在把选中的边缘划分为互斥的三类，客户端列表抓取失败不再同时计入 `failed` 与 `partial`；`summary.offline` 仍然表示客户端存活计数
- 隧道端口范围按服务端 `common.GetPorts` 的规则解析：按逗号分隔，倒序范围会被交换
- `tunnel list -t/--type` 现在会在所有边缘节点上过滤（此前不带 `-e` 时会被忽略），并把 `socks5`/`httpProxy` 解析为 `mixProxy`；list/del/edit 的类型过滤均接受 `mixProxy`
- 隧道列表会在本地过滤并按 ID 去重，因此即使服务端忽略 `type` 参数，精确类型过滤仍然正确
- `tunnel del`/`tunnel edit` 的端口定位会匹配隧道的 `Port` 或其 `Ports` 范围中的任意端口
- `tunnel edit` 会保留代理隧道的 socks5/HTTP 标志，不再在 djylb/nps 上把两者都清除

---

## v0.8.0 — 2026-10-18

### 新增

- **`host status`**：逐边缘显示可达性、在线/总客户端数、域名映射数和不同目标端口数，支持 `-e/--edge`、`-a/--all`、`--json` 和 `--no-color`
- 共享边缘状态收集器，同时支撑 `host status` 与 `edge status`；抓取失败的数量为 `None`/`null`
- 集群子集抓取：`get_all_clients()` 与 `get_all_hosts()` 支持 `edge_names`，未知边缘返回清晰的 `Edge '<name>' not found` 错误

### 变更

- **`edge status`** 在可达性之外新增客户端、域名映射和目标端口数量；任一客户端或域名映射抓取失败即退出 1，而不再只检查节点是否离线
- `edge status` 的 JSON 保留 `summary: {configured, online, offline}`，新增逐边缘数量与顶层 `totals`

---

## v0.7.0 — 2026-10-08

### 新增

- **Host 映射 HTTP Basic Auth**：`host add` 和 `host edit` 新增 `--auth` 参数，设置 NPS 原生 Basic Auth（格式：`"user=pass"` 或 `"user1=pass1,user2=pass2"`；空字符串清除）
- `host list` 输出新增 Auth 状态列
- 现代 API 传输层：自动探测 djylb/nps v0.35.0 `/api/*` REST 端点，Bearer token 认证（线程安全自动刷新）——为后续迁移到现代 API 做准备

### 修复

- **Edge 安装静默失败**：`nps-ctl edge install` 现在能检测并恢复上游 `nps install` 退出码为 0 但实际部署失败的情况（预拷贝二进制、兜底创建 `Nps.service`、验证失败时硬退出）
- **Edge 升级缺失 service 文件**：`edge upgrade` 在 systemd service 文件丢失时（如 VPS 重装后）自动重建
- `host edit` 中 `HeaderChange` 字段名错误——编辑时会静默丢弃 header 修改规则

### 变更

- 部署脚本中 `which` 替换为 POSIX `command -v`，提升跨发行版兼容性
- 固定开发工具版本：ruff 0.15.20、ty 0.0.54

---

## v0.6.0 — 2026-06-13

### 新增

- **跨 Edge 定位器**：tunnel/host 的 del/edit 命令支持按 remark、域名或 port+type 跨所有 Edge 操作，无需指定 Edge 特定的 ID
- `--target` 新增 `-T` 短标志（用于 host add 和 tunnel add）
- `--target` / `-T` 校验：tcp/udp 类型的 tunnel add 现在要求必须提供 target 地址
- helpers.py 中新增共享参数工厂函数，确保参数定义的一致性

### 修复

- **`-v/--verbose` 失效 (P0)**：子命令级别的 `-v` 因 `dest="deploy_verbose"` 与代码中 `args.verbose` 不匹配而完全无效——影响 9 个子命令
- 移除 base.py 中多余的 `ty: ignore` 抑制注释

### 变更

- **短标志清理**：`-c` 保留给 `--client`（全局 `--config` 不再有短标志），`-t` 保留给 `--type`（`--template` 和 `--target` 使用长标志或 `-T`）
- **edge sync dest 统一**：`dest="target"` → `dest="edge"`，保持跨子命令一致性
- `client del --name` 改为 `-r/--remark`（`--name` 保留为隐藏别名向后兼容）
- edit 命令修改值参数统一加 `--new-` 前缀，区分定位参数和修改值
- 多匹配安全：del/edit 命令在匹配到多个结果时报错，要求使用 `--id` 精确定位
- `--client` 帮助文本跨子命令统一

---

## v0.5.2 — 2026-06-03

### 新增

- **多架构支持**：部署脚本现在通过 `uname -m` 自动检测 CPU 架构并下载正确的二进制文件（amd64、arm64、arm）。此前硬编码为 amd64，导致 ARM 主机（如 armv7l）部署失败
- `get_download_urls()` 和 `get_npc_download_urls()` 新增 `arch` 参数，支持显式指定目标架构

### 修复

- **Edge 升级数据保留**：`edge upgrade` 现在备份并恢复数据文件（clients.json、hosts.json、tasks.json、global.json），不再清空数据（closes #9）
- **Edge 升级模板路径**：修复升级配置路径未拼接模板文件名的问题

---

## v0.5.1 — 2026-06-03

### 修复

- **NPC 部署 sudo 支持**：所有 NPC 操作（安装、卸载、重新配置、重启）在 SSH 用户非 root 时自动添加 `sudo`，修复家庭实验室机器上的权限拒绝错误
- **重新配置参数丢失**：在安装/卸载/重新配置脚本的 `npc uninstall` 后添加 `systemctl daemon-reload`，确保重新安装前彻底清除旧的服务文件
- **NPS 配置模板**：将 `bridge_port` 拆分为 `bridge_tcp_port` 和 `bridge_tls_port`，匹配 NPS v0.34.x 配置格式

### 变更

- 默认 NPS/NPC 版本从 v0.34.1 升级至 v0.34.7

---

## v0.5.0 — 2026-05-28

### 修复

- `edge export` 省略 `-e` 时显示使用的 Edge 节点
- `tunnel add` tcp/udp 类型时校验 `--port` 必填
- `client list --update` 或 `--dry-run` 时要求 `-e` 参数
- 单 Edge 列表输出时显示 Edge 标题

### 变更

- 添加 pre-commit 配置和冒烟测试 CI 任务；切换为动态版本

---

## v0.4.0 — 2026-05-15

### 新增

- **广播隧道添加**：`tunnel add` 省略 `-e` 时广播到所有 Edge 节点
- **CLI 版本标志**：`--version` / `-V` 标志
- **CRUD 命令**：为 client、host、tunnel 添加 `delete`、`edit`、`start`/`stop` 命令

### 修复

- SOCKS 代理清理和超时类型校验

---

## v0.3.0 — 2026-04-20

### 新增

- **重新配置与升级**：`client reconfig`、`client upgrade`、`edge reconfig`、`edge upgrade` 子命令
- **SSH 用户和 HTTP 代理**：客户端配置支持 `ssh_user` 和 `http_proxy` 字段，用于受限网络下的 NPC 部署

### 修复

- ty 0.0.28 类型检查器兼容性

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
