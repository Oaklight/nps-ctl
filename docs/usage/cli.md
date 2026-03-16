# 命令行参考

## 全局选项

| 选项                      | 说明                                   |
| ------------------------- | -------------------------------------- |
| `--config DIR`            | 配置目录（默认：`config/`）            |
| `--edge NAME`             | 指定目标边缘节点                       |
| `--all`                   | 操作所有边缘节点                       |
| `--socks-proxy HOST:PORT` | 通过 SOCKS5 代理路由                   |
| `--auto-proxy`            | 自动 SSH SOCKS 隧道                    |
| `-v`, `--verbose`         | 增加日志详细程度                       |
| `-y`, `--yes`             | 跳过确认提示                           |

## 命令

### `nps-ctl status`

显示所有已配置边缘节点的状态。

```bash
nps-ctl status
```

### `nps-ctl client list`

列出边缘节点上的客户端。

```bash
nps-ctl client list                # 第一个边缘节点
nps-ctl client list --edge nps-us  # 指定边缘节点
nps-ctl client list --all          # 所有边缘节点
```

### `nps-ctl client add`

添加新客户端。

```bash
nps-ctl client add --remark my-server --vkey unique-key
```

### `nps-ctl tunnels`

列出隧道。

```bash
nps-ctl tunnels --all
```

### `nps-ctl add-tunnel`

向边缘节点添加隧道。

```bash
nps-ctl add-tunnel --type tcp --client my-server --port 8080 --target 127.0.0.1:80
```

### `nps-ctl hosts`

列出域名映射。

```bash
nps-ctl hosts --all
```

### `nps-ctl add-host`

添加域名映射。

```bash
nps-ctl add-host --domain app.example.com --client my-server --target :8080
```

### `nps-ctl sync`

从一个边缘节点同步配置到其他节点。

```bash
nps-ctl sync --from nps-asia              # 同步到所有其他节点
nps-ctl sync --from nps-asia --to nps-us  # 同步到指定节点
```

### `nps-ctl npc install`

通过 SSH 在远程机器上安装 NPC 客户端。

```bash
nps-ctl npc install my-server
```

### `nps-ctl npc status`

检查各机器上的 NPC 客户端状态。

```bash
nps-ctl npc status
```

### `nps-ctl npc client-push`

从 `clients.toml` 推送客户端配置到 NPS 边缘节点。

```bash
nps-ctl npc client-push
nps-ctl npc client-push --update  # 更新已有客户端
```
