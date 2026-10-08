# CLI 参考

nps-ctl 提供了丰富的命令行界面，按五个命令组进行组织。每个组管理 NPS 基础设施的不同方面。如需快速查阅所有选项，请参见 [CLI 快速参考](../reference/cli-flags.md)。

## 全局选项

| 选项 | 说明 |
| --- | --- |
| `--config PATH` | `edges.toml` 配置文件路径 |
| `--debug` | 启用调试日志 |
| `-v`, `--verbose` | 启用详细输出 |
| `--proxy URL` | HTTP 代理 URL |
| `--socks-proxy URL` | SOCKS5 代理 URL |
| `--auto-proxy HOST` | 通过指定主机自动创建 SSH SOCKS 代理 |
| `--no-ssl-verify` | 禁用 SSL 证书验证 |
| `-V`, `--version` | 显示版本并退出 |

## 命令组

nps-ctl 将命令组织为五个组：`client`、`edge`、`tunnel`、`host` 和 `util`。

---

## `client` — NPC 客户端管理

### `client list`

从 NPS API 列出客户端，可选更新 `clients.toml`。

| 选项 | 说明 |
| --- | --- |
| `-e`, `--edge` EDGE | 要查询客户端的边缘节点名称 |
| `-a`, `--all` | 显示所有边缘节点的客户端 |
| `--update` | 用获取的客户端信息更新 `clients.toml` |
| `--dry-run` | 显示将要写入的内容，但不修改 `clients.toml` |

```bash
nps-ctl client list                   # First edge
nps-ctl client list -e nps-us         # Specific edge
nps-ctl client list -a                # All edges
nps-ctl client list -e nps-us --update  # Fetch and update clients.toml
```

### `client push`

将 `clients.toml` 中的客户端配置推送到边缘节点。

| 选项 | 说明 |
| --- | --- |
| `-c`, `--client` NAME | 要推送的特定客户端名称（默认：所有客户端） |
| `-e`, `--edge` EDGE | 要推送到的特定边缘节点（默认：客户端配置中的所有边缘节点） |
| `--dry-run` | 显示将要推送的内容，但不实际修改 |
| `--update` | 更新边缘节点上的现有客户端（从 `clients.toml` 同步 vkey） |
| `-y`, `--yes` | 跳过确认提示 |

```bash
nps-ctl client push                         # Push all clients to all edges
nps-ctl client push -c my-server            # Push specific client
nps-ctl client push -e nps-us --update      # Update existing clients on one edge
nps-ctl client push --dry-run               # Preview changes
```

### `client add`

交互式地向 `clients.toml` 添加新客户端条目。

| 选项 | 说明 |
| --- | --- |
| `--name` | 客户端名称（跳过交互式提示） |
| `--ssh-host` | SSH 主机（跳过交互式提示） |
| `--edges` EDGE [EDGE ...] | 边缘节点名称（跳过交互式提示） |
| `--vkey` | 验证密钥（未提供时自动生成） |
| `--conn-type` {tls,tcp,kcp} | 连接类型（默认：tls） |
| `-y`, `--yes` | 跳过确认提示 |

```bash
nps-ctl client add                                        # Fully interactive
nps-ctl client add --name my-server --ssh-host 10.0.0.5   # Partially pre-filled
```

### `client del`

从边缘节点删除客户端。需要 `--id` 或 `-r/--remark` 之一（互斥）。

| 选项 | 说明 |
| --- | --- |
| `--id` ID | 客户端 ID（边缘节点特定，需要 `-e`） |
| `-r`, `--remark` NAME | 客户端备注名称（可跨所有边缘节点操作） |
| `-e`, `--edge` EDGE | 边缘节点名称（`--id` 时必需，`--remark` 时默认所有边缘节点） |
| `-y`, `--yes` | 跳过确认提示 |

```bash
nps-ctl client del --id 3 -e nps-us -y          # Delete by edge-specific ID
nps-ctl client del -r my-server                  # Delete by remark across all edges
```

### `client install`

通过 SSH 在客户端机器上安装 NPC。

| 选项 | 说明 |
| --- | --- |
| `-c`, `--client` NAME | 要安装的客户端名称（默认：所有客户端） |
| `--version` VER | 要安装的 NPC 版本 |
| `--release-url` URL | NPC 二进制文件的自定义下载 URL |
| `--force-reinstall` | *（已弃用：请使用 `client upgrade`）* 强制重新安装 |
| `-y`, `--yes` | 跳过确认提示 |
| `-v`, `--verbose` | 显示详细输出 |

```bash
nps-ctl client install                          # Install all clients
nps-ctl client install -c my-server             # Install specific client
nps-ctl client install --version v0.34.7 -y     # Specific version, no prompt
```

### `client upgrade`

在客户端机器上升级 NPC 二进制文件并重新配置。

| 选项 | 说明 |
| --- | --- |
| `-c`, `--client` NAME | 要升级的客户端名称（默认：所有客户端） |
| `--version` VER | 要安装的 NPC 版本 |
| `--release-url` URL | NPC 二进制文件的自定义下载 URL |
| `-y`, `--yes` | 跳过确认提示 |
| `-v`, `--verbose` | 显示详细输出 |

```bash
nps-ctl client upgrade                           # Upgrade all clients
nps-ctl client upgrade -c my-server -v           # Upgrade one client, verbose
```

### `client reconfig`

使用更新的服务器地址重新配置 NPC（不下载二进制文件）。

| 选项 | 说明 |
| --- | --- |
| `-c`, `--client` NAME | 要重新配置的客户端名称（默认：所有客户端） |
| `-y`, `--yes` | 跳过确认提示 |
| `-v`, `--verbose` | 显示详细输出 |

```bash
nps-ctl client reconfig                          # Reconfigure all clients
nps-ctl client reconfig -c my-server             # Reconfigure specific client
```

### `client uninstall`

通过 SSH 从客户端机器上卸载 NPC。

| 选项 | 说明 |
| --- | --- |
| `-c`, `--client` NAME | 要卸载的客户端名称（默认：所有客户端） |
| `-y`, `--yes` | 跳过确认提示 |
| `-v`, `--verbose` | 显示详细输出 |

```bash
nps-ctl client uninstall -c my-server -y
```

### `client status`

检查客户端机器上的 NPC 状态。

| 选项 | 说明 |
| --- | --- |
| `-c`, `--client` NAME | 要检查的客户端名称（默认：所有客户端） |
| `--parallel` | 通过 SSH 并行检查所有客户端 |

```bash
nps-ctl client status                            # Check all clients
nps-ctl client status -c my-server               # Check specific client
nps-ctl client status --parallel                 # Parallel check
```

### `client restart`

在客户端机器上重启 NPC 服务。

| 选项 | 说明 |
| --- | --- |
| `-c`, `--client` NAME | 要重启的客户端名称（默认：所有客户端） |
| `-v`, `--verbose` | 显示详细输出 |

```bash
nps-ctl client restart
nps-ctl client restart -c my-server
```

---

## `edge` — NPS 边缘节点管理

### `edge status`

显示所有已配置边缘节点的状态。

```bash
nps-ctl edge status
```

### `edge install`

通过 SSH 在边缘节点上安装 NPS。

| 选项 | 说明 |
| --- | --- |
| `-e`, `--edge` EDGE | 要安装的边缘节点名称（默认：所有边缘节点） |
| `--template` PATH | NPS 配置模板路径 |
| `--version` VER | 要安装的 NPS 版本 |
| `--release-url` URL | NPS 二进制文件的自定义下载 URL |
| `--force-reinstall` | *（已弃用：请使用 `edge upgrade`）* 强制重新安装 |
| `-y`, `--yes` | 跳过确认提示 |
| `-v`, `--verbose` | 显示详细输出 |

```bash
nps-ctl edge install -e nps-us -y
nps-ctl edge install --version v0.34.7
```

### `edge upgrade`

升级边缘节点上的 NPS 二进制文件（保留数据文件）。

| 选项 | 说明 |
| --- | --- |
| `-e`, `--edge` EDGE | 要升级的边缘节点名称（默认：所有边缘节点） |
| `--template` PATH | NPS 配置模板路径 |
| `--version` VER | 要安装的 NPS 版本 |
| `--release-url` URL | NPS 二进制文件的自定义下载 URL |
| `-y`, `--yes` | 跳过确认提示 |
| `-v`, `--verbose` | 显示详细输出 |

```bash
nps-ctl edge upgrade -e nps-us -v
nps-ctl edge upgrade --version v0.34.7 -y
```

### `edge reconfig`

使用更新的配置重新配置 NPS（不下载二进制文件）。会重启服务。

| 选项 | 说明 |
| --- | --- |
| `-e`, `--edge` EDGE | 要重新配置的边缘节点名称（默认：所有边缘节点） |
| `--template` PATH | NPS 配置模板路径 |
| `-y`, `--yes` | 跳过确认提示 |
| `-v`, `--verbose` | 显示详细输出 |

```bash
nps-ctl edge reconfig -e nps-us
```

### `edge uninstall`

通过 SSH 从边缘节点上卸载 NPS。

| 选项 | 说明 |
| --- | --- |
| `-e`, `--edge` EDGE | 要卸载的边缘节点名称（默认：所有边缘节点） |
| `-y`, `--yes` | 跳过确认提示 |
| `-v`, `--verbose` | 显示详细输出 |

```bash
nps-ctl edge uninstall -e nps-us -y
```

### `edge sync`

将配置从一个边缘节点同步到其他节点。

| 选项 | 说明 |
| --- | --- |
| `-f`, `--from` EDGE | 同步源边缘节点名称（必需） |
| `-e`, `--edge`, `--to` EDGE [EDGE ...] | 同步目标边缘节点名称（默认：所有其他边缘节点） |
| `-t`, `--type` {all,clients,tunnels,hosts} | 要同步的配置类型（默认：all） |
| `-y`, `--yes` | 跳过确认提示 |
| `--parallel` | 并行同步到目标节点 |
| `-q`, `--quiet` | 抑制详细输出 |
| `-w`, `--workers` N | 并行工作线程数 |

```bash
nps-ctl edge sync -f nps-asia                        # Sync all to all other edges
nps-ctl edge sync -f nps-asia --to nps-us             # Sync to specific edge
nps-ctl edge sync -f nps-asia -t tunnels --parallel   # Sync only tunnels, parallel
```

### `edge export`

将边缘节点配置导出到文件。

| 选项 | 说明 |
| --- | --- |
| `-e`, `--edge` EDGE | 要导出的边缘节点名称（默认：所有边缘节点） |
| `-o`, `--output` PATH | 输出文件路径 |

```bash
nps-ctl edge export -e nps-us -o backup.json
nps-ctl edge export                                   # Export all edges
```

---

## `tunnel` — 隧道管理

### `tunnel list`

列出边缘节点上的隧道。

| 选项 | 说明 |
| --- | --- |
| `-e`, `--edge` EDGE | 要查询的边缘节点名称（默认：第一个边缘节点） |
| `-t`, `--type` {tcp,udp,socks5,httpProxy,secret,p2p,file} | 按隧道类型过滤 |
| `-a`, `--all` | 显示所有边缘节点的隧道 |

```bash
nps-ctl tunnel list                       # First edge
nps-ctl tunnel list -a                    # All edges
nps-ctl tunnel list -t tcp                # Only TCP tunnels
nps-ctl tunnel list -e nps-us -t udp      # UDP tunnels on specific edge
```

### `tunnel add`

向边缘节点添加新隧道。

| 选项 | 说明 |
| --- | --- |
| `-c`, `--client` NAME | 客户端名称或 ID（必需） |
| `-t`, `--type` {tcp,udp,socks5,httpProxy} | 隧道类型（默认：tcp） |
| `-p`, `--port` PORT | 服务器端口 |
| `-T`, `--target` ADDR | 目标地址（host:port） |
| `-e`, `--edge` EDGE | 要添加隧道的边缘节点名称（默认：所有边缘节点） |
| `-r`, `--remark` TEXT | 隧道备注 |
| `-y`, `--yes` | 跳过确认提示 |

```bash
nps-ctl tunnel add -c my-server -t tcp -p 8080 -T 127.0.0.1:80
nps-ctl tunnel add -c my-server -t udp -p 5353 -T 127.0.0.1:53 -r "dns"
nps-ctl tunnel add -c my-server -t socks5 -p 1080 -e nps-us
```

### `tunnel del`

从边缘节点删除隧道。通过 `--id`、`-r/--remark` 或 `-p/--port` + `-t/--type`（跨边缘节点定位器）定位。

| 选项 | 说明 |
| --- | --- |
| `--id` ID | 隧道 ID（边缘节点特定，需要 `-e`）— 与 `--remark` 互斥 |
| `-r`, `--remark` TEXT | 隧道备注（可跨所有边缘节点操作）— 与 `--id` 互斥 |
| `-p`, `--port` PORT | 服务器端口（与 `-t/--type` 配合使用以跨边缘节点定位隧道） |
| `-t`, `--type` {tcp,udp,socks5,httpProxy} | 隧道类型（与 `-p/--port` 配合使用以跨边缘节点定位隧道） |
| `-e`, `--edge` EDGE | 边缘节点名称（`--id` 时必需，`--remark`/`--port`+`--type` 时可选） |
| `-y`, `--yes` | 跳过确认提示 |

```bash
nps-ctl tunnel del --id 5 -e nps-us -y           # By edge-specific ID
nps-ctl tunnel del -r "dns"                       # By remark across all edges
nps-ctl tunnel del -p 8080 -t tcp                 # By port+type across all edges
```

!!! note "多匹配安全机制"
    如果多个隧道匹配定位器，命令将报错退出。使用 `--id` 配合 `-e` 以精确定位。

### `tunnel edit`

编辑边缘节点上的现有隧道。定位器参数（`--id`、`-r/--remark`、`-p/--port` + `-t/--type`）用于标识隧道；`--new-*` 参数指定要修改的内容。

**定位器选项：**

| 选项 | 说明 |
| --- | --- |
| `--id` ID | 要编辑的隧道 ID（边缘节点特定，需要 `-e`）— 与 `--remark` 互斥 |
| `-r`, `--remark` TEXT | 要定位的隧道备注（可跨所有边缘节点操作）— 与 `--id` 互斥 |
| `-p`, `--port` PORT | 要定位的服务器端口（与 `-t/--type` 配合使用以跨边缘节点定位） |
| `-t`, `--type` {tcp,udp,socks5,httpProxy} | 要定位的隧道类型（与 `-p/--port` 配合使用以跨边缘节点定位） |
| `-e`, `--edge` EDGE | 边缘节点名称（`--id` 时必需，`--remark`/`--port`+`--type` 时可选） |

**值选项（要修改的内容）：**

| 选项 | 说明 |
| --- | --- |
| `--new-target` ADDR | 新的目标地址（host:port） |
| `--new-port` PORT | 新的服务器端口 |
| `--new-remark` TEXT | 新的隧道备注 |
| `-y`, `--yes` | 跳过确认提示 |

```bash
nps-ctl tunnel edit -r "dns" --new-target 10.0.0.1:53
nps-ctl tunnel edit -p 8080 -t tcp --new-port 9090
nps-ctl tunnel edit --id 5 -e nps-us --new-remark "web-proxy"
```

### `tunnel start`

在边缘节点上启动已停止的隧道。

| 选项 | 说明 |
| --- | --- |
| `--id` ID | 要启动的隧道 ID（必需） |
| `-e`, `--edge` EDGE | 边缘节点名称（必需） |

```bash
nps-ctl tunnel start --id 5 -e nps-us
```

### `tunnel stop`

在边缘节点上停止正在运行的隧道。

| 选项 | 说明 |
| --- | --- |
| `--id` ID | 要停止的隧道 ID（必需） |
| `-e`, `--edge` EDGE | 边缘节点名称（必需） |

```bash
nps-ctl tunnel stop --id 5 -e nps-us
```

---

## `host` — 域名映射管理

### `host list`

列出边缘节点上的域名映射。

| 选项 | 说明 |
| --- | --- |
| `-e`, `--edge` EDGE | 要查询的边缘节点名称（默认：第一个边缘节点） |
| `-a`, `--all` | 显示所有边缘节点的域名映射 |

```bash
nps-ctl host list
nps-ctl host list -a
nps-ctl host list -e nps-us
```

### `host add`

向边缘节点添加新的域名映射。

| 选项 | 说明 |
| --- | --- |
| `-d`, `--domain` DOMAIN | 域名（必需） |
| `-c`, `--client` NAME | 客户端名称或 ID（必需） |
| `-T`, `--target` ADDR | 目标地址（host:port）（必需） |
| `-e`, `--edge` EDGE | 要添加域名映射的边缘节点名称（默认：所有边缘节点） |
| `-r`, `--remark` TEXT | 域名映射备注 |
| `--auth` TEXT | HTTP Basic Auth（`"user=pass"` 或 `"user1=pass1,user2=pass2"`） |
| `-y`, `--yes` | 跳过确认提示 |

```bash
nps-ctl host add -d app.example.com -c my-server -T :8080
nps-ctl host add -d api.example.com -c my-server -T 127.0.0.1:3000 -r "api"
nps-ctl host add -d private.example.com -c my-server -T :8080 --auth "admin=secret"
```

### `host del`

从边缘节点删除域名映射。需要 `--id`、`-d/--domain` 或 `-r/--remark` 之一（互斥）。

| 选项 | 说明 |
| --- | --- |
| `--id` ID | 域名映射 ID（边缘节点特定，需要 `-e`） |
| `-d`, `--domain` DOMAIN | 域名（可跨所有边缘节点操作） |
| `-r`, `--remark` TEXT | 域名映射备注（可跨所有边缘节点操作） |
| `-e`, `--edge` EDGE | 边缘节点名称（`--id` 时必需，`--domain`/`--remark` 时可选） |
| `-y`, `--yes` | 跳过确认提示 |

```bash
nps-ctl host del --id 2 -e nps-us -y             # By edge-specific ID
nps-ctl host del -d app.example.com               # By domain across all edges
nps-ctl host del -r "api"                         # By remark across all edges
```

!!! note "多匹配安全机制"
    如果多个域名映射匹配定位器，命令将报错退出。使用 `--id` 配合 `-e` 以精确定位。

### `host edit`

编辑边缘节点上的现有域名映射。定位器参数用于标识域名映射；`--new-*` 参数指定要修改的内容。

**定位器选项：**

| 选项 | 说明 |
| --- | --- |
| `--id` ID | 要编辑的域名映射 ID（边缘节点特定，需要 `-e`）— 与 `--domain` 和 `--remark` 互斥 |
| `-d`, `--domain` DOMAIN | 要定位的域名（可跨所有边缘节点操作） |
| `-r`, `--remark` TEXT | 要定位的域名映射备注（可跨所有边缘节点操作） |
| `-e`, `--edge` EDGE | 边缘节点名称（`--id` 时必需，`--domain`/`--remark` 时可选） |

**值选项（要修改的内容）：**

| 选项 | 说明 |
| --- | --- |
| `--new-domain` DOMAIN | 新的域名 |
| `--new-target` ADDR | 新的目标地址（host:port） |
| `--new-remark` TEXT | 新的域名映射备注 |
| `--auth` TEXT | HTTP Basic Auth（`"user=pass"` 或空字符串以清除） |
| `-y`, `--yes` | 跳过确认提示 |

```bash
nps-ctl host edit -d app.example.com --new-target :9090
nps-ctl host edit -r "api" --new-domain api-v2.example.com
nps-ctl host edit --id 2 -e nps-us --new-remark "web-app"
nps-ctl host edit -d private.example.com --auth ""   # clear auth
```

---

## `util` — 实用工具命令

### `util generate-auth-key`

为 NPS 生成随机认证密钥。

| 选项 | 说明 |
| --- | --- |
| `length` | 密钥长度（位置参数，默认：43） |

```bash
nps-ctl util generate-auth-key          # Default 43 characters
nps-ctl util generate-auth-key 64       # Custom length
```

---

另请参阅：[CLI 快速参考](../reference/cli-flags.md) 提供紧凑的选项查询表。
