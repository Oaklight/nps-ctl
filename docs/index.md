# nps-ctl

用于管理 [NPS](https://github.com/djylb/nps) 代理服务器的 Python 库和命令行工具。

!!! note "注意"
    本项目基于 [djylb/nps](https://github.com/djylb/nps)，这是原版 [ehang-io/nps](https://github.com/ehang-io/nps)（自 2021 年起停止维护）的活跃维护分支。API 兼容两个分支，但推荐使用 djylb/nps。

## 功能特性

- **API 客户端** — 类型安全的 NPS HTTP API Python 封装
- **多节点支持** — 通过统一界面管理多台 NPS 边缘服务器
- **集群同步** — 跨边缘节点同步客户端、隧道和域名映射
- **NPC 部署** — 通过 SSH 安装、配置和管理 NPC 客户端
- **命令行工具** — Rich 终端界面，支持所有操作
- **最小依赖** — 仅需 [rich](https://github.com/Textualize/rich) 用于终端输出

## 快速链接

- [安装](usage/installation.md)
- [配置](usage/configuration.md)
- [命令行参考](usage/cli.md)
- [库的使用](usage/library.md)
- [GitHub 仓库](https://github.com/Oaklight/nps-ctl)
- [PyPI 包](https://pypi.org/project/nps-ctl/)
