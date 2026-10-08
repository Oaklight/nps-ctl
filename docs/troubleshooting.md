# 故障排查

## 常见问题

### 连接被拒绝或超时

**症状：** nps-ctl 命令在连接 edge 时报连接错误。

**解决方案：**

1. 检查 `edges.toml` 中的 `api_url` 是否正确，且包含协议前缀（`https://`）。
2. 确认 edge 服务器上的 NPS 服务正在运行：
    ```bash
    ssh cloud.usa1 "systemctl status Nps"
    ```
3. 确认 Web UI 端口（默认 25412）可达。如果 NPS 绑定在 `127.0.0.1`，需要确保反向代理（如 Caddy）正确转发到该端口。
4. 检查防火墙规则——API 端口必须开放或通过代理转发：
    ```bash
    ssh cloud.usa1 "ufw status | grep 25412"
    ```

### 认证失败

**症状：** API 请求返回 401 或 "auth error" 响应。

**解决方案：**

1. 检查 `edges.toml` 中的 `auth_key` 是否与服务器上 `/etc/nps/conf/nps.conf` 中的 `auth_key` 一致。
2. 确认 `edges.toml` 中的 `auth_crypt_key` 与服务器端的 `auth_crypt_key` 完全匹配（必须恰好 16 个字符）。
3. 使用新版 API（v0.35.0+）时，检查 `username` 和 `password` 是否与服务器的 `web_username` 和 `web_password` 一致。
4. 如果使用 `api_mode = "auto"`，可以尝试显式设置为 `"legacy"` 或 `"modern"`，以排除自动探测失败的可能。

### SSL 证书错误

**症状：** 请求因 SSL/TLS 验证错误而失败。

**解决方案：**

- 在测试环境中使用自签名证书时，可以加上 `--no-ssl-verify` 参数：
    ```bash
    nps-ctl --no-ssl-verify edge status
    ```
- 在生产环境中，应修复服务器上的证书链。如果使用 Caddy 配合 ACME，请确认域名解析正确且 ACME 验证能够成功。

!!! warning "警告"
    `--no-ssl-verify` 会完全禁用证书验证。请勿在生产环境中使用——应当修复根本的证书问题。

### 客户端未连接

**症状：** `client list` 显示客户端处于断开状态，或主机映射返回 502 错误。

**解决方案：**

1. 检查客户端机器上的 NPC 服务是否正在运行：
    ```bash
    nps-ctl client status -c my-server
    ```
    或者直接通过 SSH 查看：
    ```bash
    ssh my-server "systemctl status Npc"
    ```
2. 确认 edge 服务器的防火墙已放行桥接端口：
    ```bash
    ssh cloud.usa1 "ufw status | grep -E '51234|51235'"
    ```
3. 查看 NPC 日志中是否有连接错误：
    ```bash
    ssh my-server "journalctl -u Npc --no-pager -n 50"
    ```
4. 确保客户端的 `vkey` 与 edge 上注册的一致。使用 `client list -e <edge>` 来验证。

### 找不到配置文件

**症状：** 启动时报 `No configuration file found` 错误。

**解决方案：**

1. 创建配置目录和文件：
    ```bash
    mkdir -p ~/.config/nps-ctl
    # 创建 edges.toml 并定义你的 edge
    ```
2. 或者显式指定配置文件路径：
    ```bash
    nps-ctl --config /path/to/edges.toml edge status
    ```
3. 检查文件是否为合法的 TOML 格式。常见错误是使用了 `[edges.name]` 表语法，而不是 `[[edges]]` 数组语法。

### Edge 安装静默失败

**症状：** `edge install` 执行完毕没有报错，但 NPS 并未运行。

**解决方案：**

1. 使用详细输出模式运行安装命令，查看详细信息：
    ```bash
    nps-ctl edge install -e nps-us -v -y
    ```
2. 确认二进制文件已部署到位：
    ```bash
    ssh cloud.usa1 "which nps && nps --version"
    ```
3. 检查 systemd 服务文件是否存在：
    ```bash
    ssh cloud.usa1 "cat /etc/systemd/system/Nps.service"
    ```
4. 查看服务日志中是否有启动失败的信息：
    ```bash
    ssh cloud.usa1 "journalctl -u Nps --no-pager -n 30"
    ```

!!! tip "提示"
    安装流程在 nps-ctl v0.7.0 中得到了改进，增加了回退 systemd 服务文件和严格的验证检查。如果你使用的是更早的版本，建议先升级 nps-ctl。

### 主机映射不生效

**症状：** 域名解析正确，但返回 502 Bad Gateway 或无响应。

**解决方案：**

1. 确认客户端已在该主机映射所在的 edge 上保持连接：
    ```bash
    nps-ctl client list -e nps-us
    ```
2. 验证 DNS 解析到了 edge 服务器的 IP：
    ```bash
    dig +short app.example.com
    ```
3. 检查主机映射的目标是否正确（服务必须在客户端机器的指定端口上监听）：
    ```bash
    nps-ctl host list -e nps-us
    ```
4. 在客户端本地测试服务是否正常：
    ```bash
    ssh my-server "curl -s http://127.0.0.1:8080"
    ```
5. 如果在 NPS 前面使用了 Caddy，请确认 Caddyfile 将该域名代理到了 NPS HTTP 代理端口（默认 30080）。

## 调试日志

nps-ctl 提供两个级别的详细输出：

```bash
# 详细模式 — 显示 API 请求/响应详情
nps-ctl -v edge status

# 调试模式 — 显示所有信息，包括内部状态
nps-ctl --debug edge status
```

这些参数是全局的，适用于任何子命令。调试输出包含完整的 HTTP 请求/响应过程，对于排查 API 相关问题非常有用。

## 常见问答

### 应该使用哪个 NPS 分支？

推荐使用 [djylb/nps](https://github.com/djylb/nps)。原始的 [ehang-io/nps](https://github.com/ehang-io/nps) 自 2021 年起已停止维护。djylb 分支仍在活跃开发中，包含安全修复，并新增了新版 API（v0.35.0+）等功能。nps-ctl 针对 djylb/nps 进行测试。

### nps-ctl 能同时管理 NPS 和 NPC 吗？

可以。`edge` 命令组用于管理 NPS 服务端节点（安装、升级、重新配置、同步、导出）。`client` 命令组用于管理 NPC 客户端（安装、升级、重新配置、状态查看、重启）。两者均通过 SSH 操作，使用配置文件中的 `ssh_host` 字段。

### nps-ctl 兼容原始的 ehang-io/nps 吗？

旧版 API 是兼容的，因此基本操作（列出客户端、隧道、主机映射；添加和删除条目）应当可以正常工作。但 ehang-io/nps 已停止维护，可能存在未修复的安全问题。新版 API 字段（`username`、`password`、`platform_token`、`api_mode`）是 djylb/nps v0.35.0+ 专有的。

### 如何生成 auth_key？

使用内置工具：

```bash
nps-ctl util generate-auth-key       # 43 字符的随机密钥
nps-ctl util generate-auth-key 64    # 自定义长度
```

### 只有一个 edge 时能使用 nps-ctl 吗？

可以。在 `edges.toml` 中定义一个 `[[edges]]` 块即可，所有命令的使用方式完全一样。多 edge 功能（同步、广播）只是没有额外的目标节点而已。
