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
| `--json` | 输出机器可读的 JSON（列表、状态和 `edge list`） |
| `--no-color` | 禁用彩色输出 |
| `-V`, `--version` | 显示版本并退出 |

读取类命令（`client list`、`edge status`、`host list`、`host status`、`tunnel list`、`tunnel status`）默认作用于**所有**已配置的边缘节点；`-e/--edge` 缩小到单个边缘节点，`-a/--all` 是显式的全边缘别名。变更类命令（`client del`、`host/tunnel add|del|edit`）必须提供 `-e` 或 `-a` 之一，不存在隐式的全集群默认值。

## 命令组

nps-ctl 将命令组织为五个组：`client`、`edge`、`tunnel`、`host` 和 `util`。

---

## `client` — NPC 客户端管理

### `client list`

从 NPS API 列出客户端，可选更新 `clients.toml`。

| 选项 | 说明 |
| --- | --- |
| `-e`, `--edge` EDGE | 要查询客户端的边缘节点名称（默认：所有边缘节点） |
| `-a`, `--all` | 显式的全边缘别名（默认行为） |
| `--json` | 输出机器可读的 JSON |
| `--no-color` | 禁用彩色输出 |
| `--update` | 用获取的客户端信息更新 `clients.toml` |
| `--dry-run` | 显示将要写入的内容，但不修改 `clients.toml` |

```bash
nps-ctl client list                   # All edges
nps-ctl client list -e nps-us         # Specific edge
nps-ctl client list -a                # All edges (explicit)
nps-ctl client list --json            # Machine-readable output
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
| `-e`, `--edge` EDGE | 边缘节点名称（`--id` 时必需；`--remark` 时除非使用 `-a/--all` 否则也必需） |
| `-a`, `--all` | 从所有已配置边缘节点删除指定客户端 |
| `-y`, `--yes` | 跳过确认提示 |

```bash
nps-ctl client del --id 3 -e nps-us -y          # Delete by edge-specific ID
nps-ctl client del -r my-server -a               # Delete by remark across all edges
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

最后一行输出 `ok: N, failed: N`。只要任一 SSH 检查失败，或任一客户端的 NPC 未安装/未运行，命令就以 1 退出；全部正常运行时退出 0。

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

### `edge list`

列出 `edges.toml` 中配置的所有边缘节点，不需要网络访问。

| 选项 | 说明 |
| --- | --- |
| `--json` | 输出机器可读的 JSON |
| `--no-color` | 禁用彩色输出 |

```bash
nps-ctl edge list
nps-ctl edge list --json
```

### `edge status`

显示全部或选定边缘节点的可达性与资源清单。该命令会抓取完整的客户端、域名映射
和隧道列表，开销随集群规模增长，属于清单命令而非轻量健康探测。使用旧版 API 的
边缘节点列出隧道时需要按隧道类型逐个请求（共 8 次）；新版 API 只需一次请求。
第八种模式 `mixProxy` 是 djylb/nps 存储 socks5 与 httpProxy 隧道的方式，缺少它
会导致这些隧道无法计入任何统计。

| 选项 | 说明 |
| --- | --- |
| `-e`, `--edge` EDGE | 要查询的边缘节点（默认：全部） |
| `-a`, `--all` | 显式的全边缘别名（默认行为） |
| `--json` | 输出机器可读的 JSON |
| `--no-color` | 禁用彩色输出 |

```bash
nps-ctl edge status
nps-ctl edge status -e nps-us
nps-ctl edge status -a --json
```

输出列为 `Edge`、`Region`、`API URL`、`Status`、`Clients`、`Hosts` 和
`Tunnels`。`Clients` 为 `<在线>/<总数>`；`Hosts` 为 `<数量> (<端口数> ports)`，
`Tunnels` 为 `<数量> (<运行数> running, <端口数> ports)`。端口按去重计数：
域名端口来自 `Target.TargetStr`，隧道端口来自 `Port`/`Ports`。抓取失败的数量
显示为 `-`。

状态取值：

- `✓ Online` — 所有请求的抓取均成功。
- `⚠ Partial` — 至少一个请求的抓取成功，但并非全部成功。
- `✗ Offline` — 所有请求的抓取均失败。

当任一选中边缘返回部分结果时，汇总行会附加 `N partial`，随后是客户端、域名映射
与隧道的汇总数量。

JSON 保留 `summary: {configured, online, offline}`，并为每个边缘新增 `ok`、
`partial`、`clients_ok`、`clients_total`、`clients_online`、`hosts_ok`、
`hosts_total`、`ports`、`tunnels_ok`、`tunnels_total`、`tunnels_running`、
`tunnel_ports` 和 `error`，顶层新增 `totals`。未请求的资源与失败的数量是
`null`，不会是 `0`。

只要有节点离线，或任一客户端、域名映射或隧道抓取失败，命令就以 1 退出。

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

最后一行输出 `edges ok: N, failed: N`。只要有任一目标边缘节点无法连接，或任一同步操作失败，命令就以 1 退出。

### `edge export`

将边缘节点配置导出到文件。

| 选项 | 说明 |
| --- | --- |
| `-e`, `--edge` EDGE | 要导出的边缘节点名称（默认：第一个已配置边缘节点） |
| `-o`, `--output` PATH | 输出文件路径 |

```bash
nps-ctl edge export -e nps-us -o backup.json
nps-ctl edge export                                   # First configured edge
```

---

## `tunnel` — 隧道管理

### `tunnel status`

显示选定边缘节点的客户端在线状态与隧道清单。

| 选项 | 说明 |
| --- | --- |
| `-e`, `--edge` EDGE | 要查询的边缘节点（默认：全部） |
| `-a`, `--all` | 显式的全边缘别名（默认行为） |
| `--json` | 输出机器可读的 JSON |
| `--no-color` | 禁用彩色输出 |

```bash
nps-ctl tunnel status
nps-ctl tunnel status -e nps-us
nps-ctl tunnel status -a --json
```

输出列为 `Edge`、`Region`、`Status`、`Clients`、`Tunnels`、`Running` 和
`Ports`。`Clients` 为 `<在线>/<总数>`；`Ports` 统计 `Port`/`Ports` 中不同的
服务端端口，端口范围按服务端 `common.GetPorts` 的规则展开（包括交换倒序范围）。
自动分配或无效端口会被忽略。所有隧道模式都会计入，包括 djylb/nps 上的
`mixProxy`。该命令不抓取域名映射，因此 JSON 中的域名计数为 `null`。

仅当所有选定边缘的客户端与隧道抓取均成功时退出码为 0；任一抓取或配置失败
（包括未知的 `-e`）为 1；同时使用 `-e` 和 `-a` 为 2。

### `tunnel list`

列出边缘节点上的隧道。

| 选项 | 说明 |
| --- | --- |
| `-e`, `--edge` EDGE | 要查询的边缘节点名称（默认：所有边缘节点） |
| `-t`, `--type` {tcp,udp,socks5,httpProxy,mixProxy,secret,p2p,file} | 按隧道类型过滤 |
| `-a`, `--all` | 显式的全边缘别名（默认行为） |
| `--json` | 输出机器可读的 JSON |
| `--no-color` | 禁用彩色输出 |

```bash
nps-ctl tunnel list                       # All edges
nps-ctl tunnel list -a                    # All edges (explicit)
nps-ctl tunnel list -e nps-us             # Specific edge
nps-ctl tunnel list -t tcp                # Only TCP tunnels
nps-ctl tunnel list -e nps-us -t udp      # UDP tunnels on specific edge
nps-ctl tunnel list --json                # Machine-readable output
```

`mixProxy` 同时匹配两种代理；`socks5` 与 `httpProxy` 也会匹配 `mixProxy`
行，这是 djylb/nps 存储这两类隧道的方式。

### `tunnel add`

向边缘节点添加新隧道。

| 选项 | 说明 |
| --- | --- |
| `-c`, `--client` NAME | 客户端名称或 ID（必需） |
| `-t`, `--type` {tcp,udp,socks5,httpProxy} | 隧道类型（默认：tcp） |
| `-p`, `--port` PORT | 服务器端口 |
| `-T`, `--target` ADDR | 目标地址（host:port） |
| `-e`, `--edge` EDGE | 要添加隧道的边缘节点名称（除非使用 `-a/--all`，否则必需） |
| `-a`, `--all` | 向所有已配置边缘节点添加隧道 |
| `-r`, `--remark` TEXT | 隧道备注 |
| `-y`, `--yes` | 跳过确认提示 |

```bash
nps-ctl tunnel add -c my-server -t tcp -p 8080 -T 127.0.0.1:80 -a
nps-ctl tunnel add -c my-server -t udp -p 5353 -T 127.0.0.1:53 -a -r "dns"
nps-ctl tunnel add -c my-server -t socks5 -p 1080 -e nps-us
```

### `tunnel del`

从边缘节点删除隧道。通过 `--id`、`-r/--remark` 或 `-p/--port` + `-t/--type`（跨边缘节点定位器）定位。

| 选项 | 说明 |
| --- | --- |
| `--id` ID | 隧道 ID（边缘节点特定，需要 `-e`）— 与 `--remark` 互斥 |
| `-r`, `--remark` TEXT | 隧道备注（可跨所有边缘节点操作）— 与 `--id` 互斥 |
| `-p`, `--port` PORT | 服务器端口（与 `-t/--type` 配合使用以跨边缘节点定位隧道） |
| `-t`, `--type` {tcp,udp,socks5,httpProxy,mixProxy} | 隧道类型（与 `-p/--port` 配合使用以跨边缘节点定位隧道） |
| `-e`, `--edge` EDGE | 边缘节点名称（使用 `--id` 时必需；否则需提供此项或 `-a/--all`） |
| `-a`, `--all` | 从所有已配置边缘节点删除匹配的隧道 |
| `-y`, `--yes` | 跳过确认提示 |

```bash
nps-ctl tunnel del --id 5 -e nps-us -y           # By edge-specific ID
nps-ctl tunnel del -r "dns" -a                    # By remark across all edges
nps-ctl tunnel del -p 8080 -t tcp -a              # By port+type across all edges
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
| `-t`, `--type` {tcp,udp,socks5,httpProxy,mixProxy} | 要定位的隧道类型（与 `-p/--port` 配合使用以跨边缘节点定位） |
| `-e`, `--edge` EDGE | 边缘节点名称（使用 `--id` 时必需；否则需提供此项或 `-a/--all`） |
| `-a`, `--all` | 在所有已配置边缘节点上编辑匹配的隧道 |

**值选项（要修改的内容）：**

| 选项 | 说明 |
| --- | --- |
| `--new-target` ADDR | 新的目标地址（host:port） |
| `--new-port` PORT | 新的服务器端口 |
| `--new-remark` TEXT | 新的隧道备注 |
| `-y`, `--yes` | 跳过确认提示 |

```bash
nps-ctl tunnel edit -r "dns" -a --new-target 10.0.0.1:53
nps-ctl tunnel edit -p 8080 -t tcp -a --new-port 9090
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
| `-e`, `--edge` EDGE | 要查询的边缘节点名称（默认：所有边缘节点） |
| `-a`, `--all` | 显式的全边缘别名（默认行为） |
| `--matrix` | 域名与边缘节点的存在性矩阵 |
| `--json` | 输出机器可读的 JSON |
| `--no-color` | 禁用彩色输出 |

```bash
nps-ctl host list
nps-ctl host list -a
nps-ctl host list -e nps-us
nps-ctl host list --matrix          # Presence of every domain on every edge
nps-ctl host list --matrix --json
```

矩阵以所有域名的并集为行、已配置边缘节点为列。单元格含义：`✓` 存在、`-` 缺失、`!` 获取失败；失败的边缘节点还会在表格下方显示原因。只要有任一节点获取失败，命令就以 1 退出。

### `host status`

显示所选边缘节点的客户端在线状态与域名映射清单。

| 选项 | 说明 |
| --- | --- |
| `-e`, `--edge` EDGE | 要查询的边缘节点名称（默认：所有边缘节点） |
| `-a`, `--all` | 显式的全边缘别名（默认行为） |
| `--json` | 输出机器可读的 JSON |
| `--no-color` | 禁用彩色输出 |

```bash
nps-ctl host status
nps-ctl host status -e nps-us
nps-ctl host status -a --json
```

输出列为 `Edge`、`Region`、`Status`、`Clients`、`Hosts` 和 `Ports`，状态与
数量规则与 `edge status` 相同。汇总行报告在线边缘数（适用时附加 `N partial`）、
在线/总客户端数、域名映射数和不同目标端口数；错误行以 `✗` 为前缀。未知数量在
表格中显示为 `-`，在 JSON 中为 `null`。

仅当每个所选边缘的客户端与域名映射抓取都成功时命令才以 0 退出；任何抓取或
配置失败（包括未知的 `-e`）退出 1；同时使用 `-e` 和 `-a` 退出 2。

### `host add`

向边缘节点添加新的域名映射。

| 选项 | 说明 |
| --- | --- |
| `-d`, `--domain` DOMAIN | 域名（必需） |
| `-c`, `--client` NAME | 客户端名称或 ID（必需） |
| `-T`, `--target` ADDR | 目标地址（host:port）（必需） |
| `-e`, `--edge` EDGE | 要添加域名映射的边缘节点名称（除非使用 `-a/--all`，否则必需） |
| `-a`, `--all` | 向所有已配置边缘节点添加域名映射 |
| `-r`, `--remark` TEXT | 域名映射备注 |
| `--auth` TEXT | HTTP Basic Auth（`"user=pass"` 或 `"user1=pass1,user2=pass2"`） |
| `-y`, `--yes` | 跳过确认提示 |

```bash
nps-ctl host add -d app.example.com -c my-server -T :8080 -a
nps-ctl host add -d api.example.com -c my-server -T 127.0.0.1:3000 -a -r "api"
nps-ctl host add -d private.example.com -c my-server -T :8080 -a --auth "admin=secret"
```

### `host del`

从边缘节点删除域名映射。需要 `--id`、`-d/--domain` 或 `-r/--remark` 之一（互斥）。

| 选项 | 说明 |
| --- | --- |
| `--id` ID | 域名映射 ID（边缘节点特定，需要 `-e`） |
| `-d`, `--domain` DOMAIN | 域名（可跨所有边缘节点操作） |
| `-r`, `--remark` TEXT | 域名映射备注（可跨所有边缘节点操作） |
| `-e`, `--edge` EDGE | 边缘节点名称（使用 `--id` 时必需；否则需提供此项或 `-a/--all`） |
| `-a`, `--all` | 从所有已配置边缘节点删除匹配的域名映射 |
| `-y`, `--yes` | 跳过确认提示 |

```bash
nps-ctl host del --id 2 -e nps-us -y             # By edge-specific ID
nps-ctl host del -d app.example.com -a            # By domain across all edges
nps-ctl host del -r "api" -a                      # By remark across all edges
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
| `-e`, `--edge` EDGE | 边缘节点名称（使用 `--id` 时必需；否则需提供此项或 `-a/--all`） |
| `-a`, `--all` | 在所有已配置边缘节点上编辑匹配的域名映射 |

**值选项（要修改的内容）：**

| 选项 | 说明 |
| --- | --- |
| `--new-domain` DOMAIN | 新的域名 |
| `--new-target` ADDR | 新的目标地址（host:port） |
| `--new-remark` TEXT | 新的域名映射备注 |
| `--auth` TEXT | HTTP Basic Auth（`"user=pass"` 或空字符串以清除） |
| `-y`, `--yes` | 跳过确认提示 |

```bash
nps-ctl host edit -d app.example.com -a --new-target :9090
nps-ctl host edit -r "api" -a --new-domain api-v2.example.com
nps-ctl host edit --id 2 -e nps-us --new-remark "web-app"
nps-ctl host edit -d private.example.com -a --auth ""   # clear auth
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
