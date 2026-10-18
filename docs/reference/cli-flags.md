# CLI 快速参考

## 全局选项

以下选项适用于所有命令，必须放在命令组之前。

```
nps-ctl [全局选项] <命令> <子命令> [选项]
```

| 标志 | 长格式 | 说明 |
|------|--------|------|
| `-V` | `--version` | 显示版本并退出 |
| `-v` | `--verbose` | 启用详细输出 |
| | `--debug` | 启用调试日志 |
| | `--config` | `edges.toml` 配置文件的路径 |
| | `--proxy` | HTTP 代理 URL |
| | `--socks-proxy` | SOCKS5 代理 URL |
| | `--auto-proxy` | 通过指定主机自动创建 SSH SOCKS 代理 |
| | `--no-ssl-verify` | 禁用 SSL 证书验证 |
| | `--json` | 输出机器可读的 JSON（列表、状态和 `edge list`） |
| | `--no-color` | 禁用彩色输出 |

读取类命令（`client list`、`host list`、`host status`、`tunnel list`）默认作用于所有已配置边缘节点；`-e/--edge` 缩小到单个节点，`-a/--all` 是显式的全边缘别名（`edge status` 始终覆盖所有已配置节点）。变更类命令（`client del`、`host/tunnel add|del|edit`）必须提供其中之一。

## 短标志参考

| 短标志 | 长格式 | 适用命令 | 说明 |
|--------|--------|----------|------|
| `-a` | `--all` | `client list/del`、`tunnel list/add/del/edit`、`host list/status/add/del/edit` | 显式的全边缘范围（读取时是默认值，变更时是必需选项之一） |
| | `--matrix` | `host list` | 域名与边缘节点的存在性矩阵 |
| `-c` | `--client` | `client del/push/install/upgrade/reconfig/uninstall/status/restart`、`tunnel add`、`host add` | 客户端名称（备注）或数字 ID |
| `-d` | `--domain` | `host add/del/edit` | 域名 |
| `-e` | `--edge` | 大多数命令 | 将操作限定到指定的 edge |
| `-f` | `--from` | `edge sync` | 源 edge 名称 |
| `-o` | `--output` | `edge export` | 输出文件路径 |
| `-p` | `--port` | `tunnel add/del/edit` | 服务器端口 |
| `-q` | `--quiet` | `edge sync` | 抑制详细输出 |
| `-r` | `--remark` | `client del`、`tunnel add/del/edit`、`host add/del/edit` | 用于定位或标记条目的备注（名称） |
| `-t` | `--type` | `tunnel add/del/edit/list`、`edge sync` | 隧道类型或同步范围 |
| `-v` | `--verbose` | `client install/upgrade/reconfig/uninstall/restart` | 显示详细输出 |
| `-w` | `--workers` | `edge sync` | 并行工作线程数 |
| `-y` | `--yes` | `client add/del/push/install/upgrade/reconfig/uninstall`、`edge install/upgrade/reconfig/uninstall/sync`、`tunnel add/del/edit`、`host add/del/edit` | 跳过确认提示 |
| `-T` | `--target` | `tunnel add`、`host add` | 目标地址（`host:port`） |
| `-V` | `--version` | 全局 | 显示版本并退出 |

!!! tip "提示"
    `-v` 具有双重用途：在子命令上（如 `client install -v`）表示 `--verbose`，
    在全局级别（`nps-ctl -v`）也等同于 `--verbose`。如需完整的调试日志，
    请使用 `--debug`。

## 命令组

| 组 | 子命令 |
|----|--------|
| `client` | `list`、`push`、`add`、`install`、`upgrade`、`reconfig`、`uninstall`、`status`、`restart`、`del` |
| `edge` | `list`、`status`、`install`、`upgrade`、`reconfig`、`uninstall`、`sync`、`export` |
| `tunnel` | `list`、`add`、`del`、`edit`、`start`、`stop` |
| `host` | `list`、`status`、`add`、`del`、`edit` |
| `util` | `generate-auth-key` |
