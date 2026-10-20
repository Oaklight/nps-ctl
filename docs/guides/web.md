# Web 管理面板

`nps-ctl web` 为所有已配置的边缘节点提供管理面板。默认只读，只有传入
`--allow-writes` 才会启用变更操作。

```bash
# 单用户
export NPS_WEB_PASSWORD='choose-a-password'
nps-ctl web --username admin --allow-writes
# http://127.0.0.1:8080/
```

默认只监听 `127.0.0.1`。未配置凭据时绑定到非回环地址会被拒绝，除非传入
`--insecure`；网络可达且无认证的绑定始终拒绝写入。暴露到回环地址之外前，
请在前置代理上终止 TLS，参见[部署](#_2)。

## 用户与角色

单用户可以传入 `--username` 和 `--password`（或设置 `NPS_WEB_PASSWORD`）。
需要多个用户时，创建 users 文件，并在本地生成每个密码的哈希：

```bash
nps-ctl util hash-password
# pbkdf2_sha256$260000$...$...
```

```toml
# web-users.toml
[[users]]
name = "admin"
password_hash = "pbkdf2_sha256$260000$...$..."
role = "operator"

[[users]]
name = "viewer"
password_hash = "pbkdf2_sha256$260000$...$..."
role = "viewer"
```

```bash
nps-ctl web --users-file web-users.toml --allow-writes
```

`operator` 可以执行所有操作；`viewer` 看到同样的面板，但没有操作按钮，
服务端也会拒绝其写请求。`hash-password` 会读取 `NPS_WEB_PASSWORD` 或不回显
地提示输入，因此明文密码不会出现在 argv 或 shell 历史中。users 文件应保持
`0600` 权限（如果组/其他用户可读，服务会发出警告）。

同时传入 `--users-file` 与 `--username/--password` 会报错。

## 操作

启用 `--allow-writes` 后：

| 操作 | 说明 |
| --- | --- |
| 同步边缘节点 | 从源节点复制缺失的客户端、隧道和域名映射到选中的目标节点。可勾选 **prune** 删除源节点上不存在的资源。 |
| 添加客户端 | 在选中的节点上创建客户端，所有节点共享一个验证密钥，且只显示一次。 |
| 添加隧道/域名映射 | 为某个客户端（按 remark 精确匹配）在选中的节点上添加隧道或域名映射；已存在的映射报告为 `exists`。 |
| 添加边缘节点 | 向 `edges.toml` 追加条目，运行中的集群会就地重新加载，无需重启。 |
| 编辑/删除 | 在单个节点上修改或删除客户端、隧道、域名映射。编辑范围限定为你打开的那一行和节点。 |

每个操作都会：

- 使用显式的边缘节点列表（不存在隐式的全集群写入）；
- 在执行前显示确认步骤（编辑会显示条目和节点）；
- 要求每次进程独立的 `X-CSRF-Token`，并拒绝跨源、非 JSON 和超大请求体；
- 同一时间只允许一个变更（第二个请求返回 `409`）；
- 逐节点报告结果，客户端验证密钥只在操作响应中显示一次且不会被隐藏。

`sync --prune` 是唯一的破坏性批量操作。它会删除目标节点上的多余资源
（先删隧道和域名映射，再删客户端）；如果所选源数据抓取失败，会在做出任何
修改前中止，避免把不可达的源节点当成空节点。CLI 中对应
`nps-ctl edge sync --prune`。

## 从面板添加边缘节点

**Add edge** 对话框会追加一个 `[[edges]]` 条目并就地重新加载集群。字段包括
名称、API URL、auth key（可选）、区域和 SSH 主机。auth key 只通过已认证的
连接传输，不会回显或写入日志，并写入 `edges.toml`（保留文件权限）。新节点
会在下一次概览刷新时探测；如果不可达，只会显示为离线，不影响其他节点。

## 部署

仓库中的 `deploy/web` 包含：

- `nps-ctl-web.service` —— 以 `nps-ctl` 用户运行的 systemd 单元，配置目录
  可写以支持“Add edge”操作；
- `Caddyfile.nps-admin` —— 为 `nps-admin.oaklight.top` 提供自动 TLS 的
  Caddy 站点配置；
- `web-users.example.toml` —— users 文件模板。

将 DNS 指向服务器，安装 `nps-ctl`，把 `edges.toml` 和 users 文件复制到
`/etc/nps-ctl`，启用 systemd 单元并添加 Caddy 配置。面板只监听回环地址，
Caddy 负责终止 TLS 并反向代理。

## 安全说明

- 读取结果会隐藏客户端验证密钥、隧道密码和 Basic Auth。
- 面板发送 `Cache-Control: no-store`、`nosniff`、严格 CSP 和
  `X-Frame-Options: DENY`。
- 未配置认证时，回环绑定会拒绝非回环 `Host` 请求头，防止 DNS rebinding。
  非回环的 `--insecure` 绑定显式只读。
- 内置服务器只提供 HTTP，暴露前请终止 TLS。
