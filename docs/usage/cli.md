# 命令行参考

## 全局选项

| 选项                      | 说明                               |
| ------------------------- | ---------------------------------- |
| `--config PATH`           | edges.toml 配置文件路径            |
| `--debug`                 | 启用调试日志                       |
| `-v`, `--verbose`         | 启用详细输出                       |
| `--proxy URL`             | HTTP 代理 URL                      |
| `--socks-proxy URL`       | SOCKS5 代理 URL                    |
| `--auto-proxy HOST`       | 通过指定主机自动创建 SSH SOCKS 代理 |
| `--no-ssl-verify`         | 禁用 SSL 证书校验                  |
| `-V`, `--version`         | 显示版本号                         |

## 命令组概览

nps-ctl 按资源类型组织为五个命令组：

| 命令组   | 说明                   |
| -------- | ---------------------- |
| `client` | NPC 客户端管理         |
| `edge`   | NPS 边缘节点管理       |
| `tunnel` | 隧道管理               |
| `host`   | 域名映射管理           |
| `util`   | 工具命令               |

---

## `client` — NPC 客户端管理

### `client list`

从 NPS API 获取客户端列表，可选更新 clients.toml。

| 选项              | 说明                                       |
| ----------------- | ------------------------------------------ |
| `-e`, `--edge`    | 查询的 Edge 名称（更新 clients.toml 时必填）|
| `-a`, `--all`     | 显示所有 Edge 上的客户端                   |
| `--update`        | 将获取的客户端信息写入 clients.toml        |
| `--dry-run`       | 预览将要写入的内容，不实际修改             |

```bash
nps-ctl client list                        # 第一个 Edge
nps-ctl client list -a                     # 所有 Edge
nps-ctl client list -e nps-us --update     # 获取并更新 clients.toml
nps-ctl client list -e nps-us --dry-run    # 预览
```

### `client push`

从 clients.toml 读取配置，推送到 Edge 节点。

| 选项              | 说明                                         |
| ----------------- | -------------------------------------------- |
| `-c`, `--client`  | 指定推送的客户端名称（默认：全部）           |
| `-e`, `--edge`    | 指定推送的 Edge（默认：客户端配置中的所有 Edge）|
| `--dry-run`       | 预览将要推送的内容                           |
| `--update`        | 更新已有客户端（同步 vkey）                  |
| `-y`, `--yes`     | 跳过确认提示                                 |

```bash
nps-ctl client push
nps-ctl client push -c my-server -e nps-us
nps-ctl client push --update --dry-run
```

### `client add`

交互式添加新客户端到 clients.toml。

| 选项              | 说明                                     |
| ----------------- | ---------------------------------------- |
| `--name`          | 客户端名称（跳过交互提示）               |
| `--ssh-host`      | SSH 主机（跳过交互提示）                 |
| `--edges`         | Edge 名称列表（跳过交互提示）            |
| `--vkey`          | 验证密钥（未提供则自动生成）             |
| `--conn-type`     | 连接类型：`tls`/`tcp`/`kcp`（默认：tls）|
| `-y`, `--yes`     | 跳过确认提示                             |

```bash
nps-ctl client add
nps-ctl client add --name my-server --ssh-host 10.0.0.5 --edges nps-us nps-asia
```

### `client del`

从 Edge 节点删除客户端。支持跨 Edge 定位。

| 选项              | 说明                                           |
| ----------------- | ---------------------------------------------- |
| `--id`            | 客户端 ID（Edge 特定，需配合 `-e`）            |
| `-r`, `--remark`  | 客户端 remark 名称（可跨所有 Edge 操作）       |
| `-e`, `--edge`    | Edge 名称（`--id` 时必填，`--remark` 时可选）  |
| `-y`, `--yes`     | 跳过确认提示                                   |

`--id` 和 `-r/--remark` 互斥，必须提供其一。

> `--name` 作为 `--remark` 的隐藏别名保留，向后兼容。

```bash
nps-ctl client del --id 3 -e nps-us        # 按 ID 删除（需指定 Edge）
nps-ctl client del -r my-server             # 按 remark 跨所有 Edge 删除
nps-ctl client del -r my-server -e nps-us   # 按 remark 删除指定 Edge
```

### `client install`

通过 SSH 在远程机器上安装 NPC。

| 选项                 | 说明                           |
| -------------------- | ------------------------------ |
| `-c`, `--client`     | 客户端名称（默认：全部）       |
| `--version`          | NPC 版本号                     |
| `--release-url`      | 自定义 NPC 发行版下载 URL      |
| `--force-reinstall`  | 已弃用，请使用 `client upgrade`|
| `-y`, `--yes`        | 跳过确认提示                   |
| `-v`, `--verbose`    | 显示详细输出                   |

```bash
nps-ctl client install -c my-server
nps-ctl client install -c my-server --version v0.34.7
```

### `client upgrade`

升级远程机器上的 NPC 二进制文件并重新配置。

| 选项              | 说明                           |
| ----------------- | ------------------------------ |
| `-c`, `--client`  | 客户端名称（默认：全部）       |
| `--version`       | NPC 版本号                     |
| `--release-url`   | 自定义 NPC 发行版下载 URL      |
| `-y`, `--yes`     | 跳过确认提示                   |
| `-v`, `--verbose` | 显示详细输出                   |

```bash
nps-ctl client upgrade -c my-server
nps-ctl client upgrade --version v0.34.7
```

### `client reconfig`

仅更新 NPC 配置（服务器地址、vkey），不重新下载二进制文件。

| 选项              | 说明                           |
| ----------------- | ------------------------------ |
| `-c`, `--client`  | 客户端名称（默认：全部）       |
| `-y`, `--yes`     | 跳过确认提示                   |
| `-v`, `--verbose` | 显示详细输出                   |

```bash
nps-ctl client reconfig
nps-ctl client reconfig -c my-server
```

### `client uninstall`

通过 SSH 卸载远程机器上的 NPC。

| 选项              | 说明                           |
| ----------------- | ------------------------------ |
| `-c`, `--client`  | 客户端名称（默认：全部）       |
| `-y`, `--yes`     | 跳过确认提示                   |
| `-v`, `--verbose` | 显示详细输出                   |

```bash
nps-ctl client uninstall -c my-server
```

### `client status`

检查远程机器上 NPC 服务的运行状态。

| 选项              | 说明                           |
| ----------------- | ------------------------------ |
| `-c`, `--client`  | 客户端名称（默认：全部）       |
| `--parallel`      | 并行检查所有客户端             |

```bash
nps-ctl client status
nps-ctl client status -c my-server
nps-ctl client status --parallel
```

### `client restart`

重启远程机器上的 NPC 服务。

| 选项              | 说明                           |
| ----------------- | ------------------------------ |
| `-c`, `--client`  | 客户端名称（默认：全部）       |
| `-v`, `--verbose` | 显示详细输出                   |

```bash
nps-ctl client restart -c my-server
```

---

## `edge` — NPS 边缘节点管理

### `edge status`

显示所有已配置 Edge 节点的状态。

```bash
nps-ctl edge status
```

### `edge install`

通过 SSH 在远程 Edge 节点上安装 NPS 服务器。

| 选项                | 说明                            |
| ------------------- | ------------------------------- |
| `-e`, `--edge`      | Edge 名称（默认：全部）        |
| `--template`        | NPS 配置模板文件路径            |
| `--version`         | NPS 版本号                      |
| `--release-url`     | 自定义 NPS 发行版下载 URL       |
| `--force-reinstall` | 已弃用，请使用 `edge upgrade`   |
| `-y`, `--yes`       | 跳过确认提示                    |
| `-v`, `--verbose`   | 显示详细输出                    |

```bash
nps-ctl edge install -e nps-us
nps-ctl edge install -e nps-us --template conf/nps.tmpl
```

### `edge upgrade`

升级 Edge 节点上的 NPS 二进制文件，保留数据文件。

| 选项              | 说明                           |
| ----------------- | ------------------------------ |
| `-e`, `--edge`    | Edge 名称（默认：全部）       |
| `--template`      | NPS 配置模板文件路径           |
| `--version`       | NPS 版本号                     |
| `--release-url`   | 自定义 NPS 发行版下载 URL      |
| `-y`, `--yes`     | 跳过确认提示                   |
| `-v`, `--verbose` | 显示详细输出                   |

```bash
nps-ctl edge upgrade -e nps-us
nps-ctl edge upgrade --version v0.34.7
```

### `edge reconfig`

仅更新 NPS 配置，不重新下载二进制文件。更新后自动重启服务。

| 选项              | 说明                           |
| ----------------- | ------------------------------ |
| `-e`, `--edge`    | Edge 名称（默认：全部）       |
| `--template`      | NPS 配置模板文件路径           |
| `-y`, `--yes`     | 跳过确认提示                   |
| `-v`, `--verbose` | 显示详细输出                   |

```bash
nps-ctl edge reconfig -e nps-us
```

### `edge uninstall`

通过 SSH 卸载 Edge 节点上的 NPS 服务器。

| 选项              | 说明                           |
| ----------------- | ------------------------------ |
| `-e`, `--edge`    | Edge 名称（默认：全部）       |
| `-y`, `--yes`     | 跳过确认提示                   |
| `-v`, `--verbose` | 显示详细输出                   |

```bash
nps-ctl edge uninstall -e nps-us
```

### `edge sync`

从源 Edge 同步配置到目标 Edge 节点。

| 选项              | 说明                                             |
| ----------------- | ------------------------------------------------ |
| `-f`, `--from`    | 源 Edge 名称（必填）                             |
| `-e`, `--edge`, `--to` | 目标 Edge 名称（可多个，默认：所有其他 Edge）|
| `-t`, `--type`    | 同步类型：`all`/`clients`/`tunnels`/`hosts`（默认：all）|
| `-y`, `--yes`     | 跳过确认提示                                     |
| `--parallel`      | 并行同步到目标节点                               |
| `-q`, `--quiet`   | 静默输出                                         |
| `-w`, `--workers` | 并行 worker 数量                                 |

```bash
nps-ctl edge sync -f nps-asia                      # 同步到所有其他 Edge
nps-ctl edge sync -f nps-asia -e nps-us             # 同步到指定 Edge
nps-ctl edge sync -f nps-asia -t tunnels            # 仅同步隧道
nps-ctl edge sync -f nps-asia --parallel -w 4       # 并行同步
```

### `edge export`

导出 Edge 配置到文件。

| 选项              | 说明                           |
| ----------------- | ------------------------------ |
| `-e`, `--edge`    | Edge 名称（默认：全部）       |
| `-o`, `--output`  | 输出文件路径                   |

```bash
nps-ctl edge export -e nps-us -o backup.json
```

---

## `tunnel` — 隧道管理

### `tunnel list`

列出 Edge 节点上的隧道。

| 选项              | 说明                                                       |
| ----------------- | ---------------------------------------------------------- |
| `-e`, `--edge`    | Edge 名称（默认：第一个 Edge）                             |
| `-t`, `--type`    | 按类型过滤：`tcp`/`udp`/`socks5`/`httpProxy`/`secret`/`p2p`/`file` |
| `-a`, `--all`     | 显示所有 Edge 上的隧道                                     |

```bash
nps-ctl tunnel list
nps-ctl tunnel list -a
nps-ctl tunnel list -e nps-us -t tcp
```

### `tunnel add`

添加新隧道。

| 选项              | 说明                                       |
| ----------------- | ------------------------------------------ |
| `-c`, `--client`  | 客户端名称或 ID（必填）                    |
| `-t`, `--type`    | 隧道类型：`tcp`/`udp`/`socks5`/`httpProxy`（默认：tcp）|
| `-p`, `--port`    | 服务端端口                                 |
| `-T`, `--target`  | 目标地址（host:port），tcp/udp 类型必填    |
| `-e`, `--edge`    | Edge 名称（默认：所有 Edge）               |
| `-r`, `--remark`  | 隧道备注                                   |
| `-y`, `--yes`     | 跳过确认提示                               |

```bash
nps-ctl tunnel add -c my-server -t tcp -p 8080 -T 127.0.0.1:80
nps-ctl tunnel add -c my-server -t socks5 -p 1080
nps-ctl tunnel add -c my-server -t tcp -p 3306 -T 127.0.0.1:3306 -r mysql
```

### `tunnel del`

删除隧道。支持跨 Edge 定位。

| 选项              | 说明                                                       |
| ----------------- | ---------------------------------------------------------- |
| `--id`            | 隧道 ID（Edge 特定，需配合 `-e`）                         |
| `-r`, `--remark`  | 隧道备注名称（可跨所有 Edge 操作）                         |
| `-p`, `--port`    | 服务端端口（配合 `-t/--type` 跨 Edge 定位）                |
| `-t`, `--type`    | 隧道类型（配合 `-p/--port` 跨 Edge 定位）                  |
| `-e`, `--edge`    | Edge 名称（`--id` 时必填，其他定位方式可选）               |
| `-y`, `--yes`     | 跳过确认提示                                               |

定位方式（三选一）：

- `--id`：按 Edge 特定的隧道 ID 定位（需指定 `-e`）
- `-r/--remark`：按备注名称跨 Edge 定位
- `-p/--port` + `-t/--type`：按端口和类型组合跨 Edge 定位

> 匹配到多个结果时会报错，要求使用 `--id` 精确定位。

```bash
nps-ctl tunnel del --id 5 -e nps-us           # 按 ID 删除
nps-ctl tunnel del -r mysql                    # 按备注跨 Edge 删除
nps-ctl tunnel del -p 8080 -t tcp              # 按端口+类型跨 Edge 删除
nps-ctl tunnel del -r mysql -e nps-us          # 按备注删除指定 Edge
```

### `tunnel edit`

编辑已有隧道。支持跨 Edge 定位。

| 选项              | 说明                                                       |
| ----------------- | ---------------------------------------------------------- |
| `--id`            | 隧道 ID（Edge 特定，需配合 `-e`）                         |
| `-r`, `--remark`  | 隧道备注名称（可跨 Edge 定位）                             |
| `-p`, `--port`    | 服务端端口（配合 `-t/--type` 跨 Edge 定位）                |
| `-t`, `--type`    | 隧道类型（配合 `-p/--port` 跨 Edge 定位）                  |
| `-e`, `--edge`    | Edge 名称（`--id` 时必填，其他定位方式可选）               |
| `--new-target`    | 新的目标地址（host:port）                                  |
| `--new-port`      | 新的服务端端口                                             |
| `--new-remark`    | 新的备注名称                                               |
| `-y`, `--yes`     | 跳过确认提示                                               |

定位方式与 `tunnel del` 相同。修改值参数使用 `--new-` 前缀，与定位参数区分。

```bash
nps-ctl tunnel edit --id 5 -e nps-us --new-target 10.0.0.2:80
nps-ctl tunnel edit -r mysql --new-port 3307
nps-ctl tunnel edit -p 8080 -t tcp --new-remark web-proxy
```

### `tunnel start`

启动一个已停止的隧道。

| 选项              | 说明                           |
| ----------------- | ------------------------------ |
| `--id`            | 隧道 ID（必填）               |
| `-e`, `--edge`    | Edge 名称（必填）             |

```bash
nps-ctl tunnel start --id 5 -e nps-us
```

### `tunnel stop`

停止一个运行中的隧道。

| 选项              | 说明                           |
| ----------------- | ------------------------------ |
| `--id`            | 隧道 ID（必填）               |
| `-e`, `--edge`    | Edge 名称（必填）             |

```bash
nps-ctl tunnel stop --id 5 -e nps-us
```

---

## `host` — 域名映射管理

### `host list`

列出 Edge 节点上的域名映射。

| 选项              | 说明                           |
| ----------------- | ------------------------------ |
| `-e`, `--edge`    | Edge 名称（默认：第一个 Edge）|
| `-a`, `--all`     | 显示所有 Edge 上的域名映射     |

```bash
nps-ctl host list
nps-ctl host list -a
nps-ctl host list -e nps-us
```

### `host add`

添加新域名映射。

| 选项              | 说明                                     |
| ----------------- | ---------------------------------------- |
| `-d`, `--domain`  | 域名（必填）                             |
| `-c`, `--client`  | 客户端名称或 ID（必填）                  |
| `-T`, `--target`  | 目标地址（host:port，必填）              |
| `-e`, `--edge`    | Edge 名称（默认：所有 Edge）             |
| `-r`, `--remark`  | 域名映射备注                             |
| `-y`, `--yes`     | 跳过确认提示                             |

```bash
nps-ctl host add -d app.example.com -c my-server -T 127.0.0.1:8080
nps-ctl host add -d api.example.com -c my-server -T :3000 -r api-backend
```

### `host del`

删除域名映射。支持跨 Edge 定位。

| 选项              | 说明                                           |
| ----------------- | ---------------------------------------------- |
| `--id`            | Host ID（Edge 特定，需配合 `-e`）              |
| `-d`, `--domain`  | 域名（可跨所有 Edge 操作）                     |
| `-r`, `--remark`  | 备注名称（可跨所有 Edge 操作）                 |
| `-e`, `--edge`    | Edge 名称（`--id` 时必填，其他定位方式可选）   |
| `-y`, `--yes`     | 跳过确认提示                                   |

`--id`、`-d/--domain`、`-r/--remark` 互斥，必须提供其一。

> 匹配到多个结果时会报错，要求使用 `--id` 精确定位。

```bash
nps-ctl host del --id 2 -e nps-us              # 按 ID 删除
nps-ctl host del -d app.example.com             # 按域名跨 Edge 删除
nps-ctl host del -r api-backend                 # 按备注跨 Edge 删除
```

### `host edit`

编辑已有域名映射。支持跨 Edge 定位。

| 选项              | 说明                                           |
| ----------------- | ---------------------------------------------- |
| `--id`            | Host ID（Edge 特定，需配合 `-e`）              |
| `-d`, `--domain`  | 域名（可跨 Edge 定位）                         |
| `-r`, `--remark`  | 备注名称（可跨 Edge 定位）                     |
| `-e`, `--edge`    | Edge 名称（`--id` 时必填，其他定位方式可选）   |
| `--new-domain`    | 新的域名                                       |
| `--new-target`    | 新的目标地址（host:port）                      |
| `--new-remark`    | 新的备注名称                                   |
| `-y`, `--yes`     | 跳过确认提示                                   |

定位方式与 `host del` 相同。修改值参数使用 `--new-` 前缀，与定位参数区分。

```bash
nps-ctl host edit --id 2 -e nps-us --new-target 10.0.0.2:8080
nps-ctl host edit -d app.example.com --new-domain app2.example.com
nps-ctl host edit -r api-backend --new-target :3001
```

---

## `util` — 工具命令

### `util generate-auth-key`

生成用于 NPS API 认证的随机密钥。

| 参数       | 说明                           |
| ---------- | ------------------------------ |
| `length`   | 密钥长度（可选，默认：43）     |

```bash
nps-ctl util generate-auth-key
nps-ctl util generate-auth-key 64
```

---

## 短标志速查

| 短标志 | 长标志        | 作用域                     |
| ------ | ------------- | -------------------------- |
| `-V`   | `--version`   | 全局                       |
| `-v`   | `--verbose`   | 全局 & 子命令              |
| `-y`   | `--yes`       | 各写操作子命令             |
| `-e`   | `--edge`      | 指定 Edge 节点             |
| `-c`   | `--client`    | 指定客户端                 |
| `-t`   | `--type`      | 隧道/同步类型              |
| `-T`   | `--target`    | 目标地址                   |
| `-p`   | `--port`      | 服务端端口                 |
| `-r`   | `--remark`    | 备注名称                   |
| `-d`   | `--domain`    | 域名                       |
| `-a`   | `--all`       | 显示所有 Edge 的数据       |
| `-f`   | `--from`      | edge sync 的源 Edge        |
| `-o`   | `--output`    | edge export 的输出文件     |
| `-q`   | `--quiet`     | edge sync 静默输出         |
| `-w`   | `--workers`   | edge sync 并行 worker 数   |
