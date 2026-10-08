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

## 短标志参考

| 短标志 | 长格式 | 适用命令 | 说明 |
|--------|--------|----------|------|
| `-a` | `--all` | `client list`、`tunnel list`、`host list` | 显示所有 edge 上的条目 |
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
| `edge` | `status`、`install`、`upgrade`、`reconfig`、`uninstall`、`sync`、`export` |
| `tunnel` | `list`、`add`、`del`、`edit`、`start`、`stop` |
| `host` | `list`、`add`、`del`、`edit` |
| `util` | `generate-auth-key` |
