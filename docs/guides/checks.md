---
title: 隧道健康检查
---

# 隧道健康检查

`nps-ctl check` 回答两个不同的问题：

- `check links` 关心 NPC 客户端到 NPS 边缘之间的桥接是否稳定，只读取，不产生流量。
- `check probe` 和 `check stress` 关心穿过隧道的数据是否完整，会发送流量并临时改动一个边缘。

三者的拓扑都来自 `edges.toml` 和 `clients.toml`，不需要重复描述。

## 链路健康

```bash
nps-ctl check links                      # 所有 NPC 客户端，最近 6 小时
nps-ctl check links -c cloud.usa2        # 单个客户端
nps-ctl check links --since 24h --json
```

对每个 NPC 客户端，命令只开一次 SSH 会话，读取三样东西：已建立的 socket、配置的边缘域名解析出的地址、NPC 日志的尾部。然后按（客户端，边缘）给出每一行：

| 列 | 含义 |
|----|------|
| Outages | 窗口内开始的桥接中断次数 |
| Median、Max | 中断时长 |
| Down | 窗口内处于中断状态的比例 |
| Period | 中断开始时间的间隔中位数；至少 60% 的间隔落在中位数 15% 以内时标 `*` |

一次 ping 超时开启的一段中断，起点是最后一个被回应的 ping，而不是 NPC 发现问题的时刻。超时行本身不带服务器信息，它所属的边缘由随后的 `Start server` 行给出。中断在下一次 `Successful connection` 结束。因此一条"中断占 5%"的链路，日志粗看可能完全正常。

退出码为 1 的情况：链路断开、客户端连不上、或者窗口内抖动三次以上。加 `--fail-on error` 可以忽略警告。

周期性的模式值得细看。同一边缘上每 16 分钟一次、各区域所有客户端都出现的中断，指向边缘本身或通往它的路径，而不是某个客户端。

## 数据完整性

`check links` 能说明桥接什么时候断过，但说明不了断开期间穿过的请求是否完整，这正是 `check probe` 和 `check stress` 的用途。

```bash
nps-ctl check probe -e nps-america2 -c cloud.usa2 --size 256K --count 30
nps-ctl check stress -e nps-europe -c cloud.usa2 --profile soak --duration 30m
```

一次运行做五件事：

1. 在客户端主机上启动哈希回显服务，只监听 `127.0.0.1` 的一个空闲端口，一小时后自动退出。
2. 在指定边缘上为一次性域名（`nps-ctl-check-<token>.nps-ctl-check.invalid`）添加主机映射，指向该端口。
3. 在客户端本机直接打回显服务，取得不经隧道的基线。
4. 从边缘主机经 NPS 的 HTTP 代理，用这个一次性域名发送同类负载。
5. 删除主机映射，停止回显服务。

每个请求体都由运行 token 和请求序号生成，没有任何两个相同。回显服务返回长度、SHA-256，以及每 64 KiB 一个短哈希。返回值与发送值不一致，就说明请求体被截断、被加长，或者混入了另一个并发请求的字节，块哈希还能指出位置。内容相同的请求体只能证明"有东西到达"，这种请求体能证明"正确的字节到达"。

基线很重要。基线失败时隧道的数据没有意义，命令会直接说明这一点，而不是归咎于链路。

`probe` 与 `stress` 共用的参数：

| 参数 | 含义 |
|------|------|
| `-e/--edge` | 要测试的隧道所在边缘（必填） |
| `-c/--client` | `clients.toml` 中的 NPC 客户端（必填） |
| `--http-proxy-port` | NPS HTTP 代理端口；默认从边缘的 `nps.conf` 读取，否则 30080 |
| `--fail-on` | `error`（默认）或 `warn` |
| `--dry-run` | 只打印计划，不做任何改动 |
| `-y/--yes` | 跳过确认提示 |
| `--json` | 输出机器可读结果 |

`probe` 只跑一步：`--size`（如 `64K`、`1M`）、`--count`、`--concurrency`；可选 `--mode slow` 配 `--chunk-kb` 与 `--gap-ms`，把请求体分成小段、每段之间停顿，更接近大模型客户端上传长对话的方式。

`stress` 跑命名负载：

| 负载 | 内容 |
|------|------|
| `smoke` | 30 个 256 KiB 请求，并发 4 |
| `ladder` | 64 KiB 与 1 MiB，并发依次为 1、2、4、8、16 |
| `slow` | 慢速上传：先 16 KiB 每 20 ms，再 4 KiB 每 10 ms |
| `churn` | 400 个小请求，并发 16 |
| `soak` | 按 `--duration`（默认 10m）持续施压，用于捕捉周期性故障 |

有失败时，`stress` 会读取同一时间窗口的 NPC 日志，报告有多少失败落在记录的中断窗口内，并给出这些窗口占整次运行的比例。"9 个失败全部落在占时 9% 的中断窗口内"支持链路有问题；失败附近没有任何中断则说明另有原因。

## 运行会留下什么

一切顺利时什么也不留。主机映射和回显服务在命令退出时都会被删除，包括在初始化中途失败的情况下。清理是检查过的，不是想当然的：删除后会再次查询映射，回显服务用命令自己创建的句柄停止。任何一步失败，`cleanup_failed` 会指出残留物，命令退出码为 1。

两项保护让会话远离真实配置：域名总是新生成的 `nps-ctl-check-*.nps-ctl-check.invalid`；只有主机名和备注都与会话写入的一致时才会删除映射。

探针会话要求边缘主机和客户端主机上都有 `python3`。两个随命令下发的辅助脚本只用标准库。

## 常用组合

判断是不是某个边缘的问题：

```bash
nps-ctl check links --since 24h
```

所有客户端对同一边缘都抖动，问题在边缘；同一客户端对所有边缘都抖动，问题在客户端网络。

盯住抖动的链路看有没有数据损坏：

```bash
nps-ctl check stress -e nps-europe -c cloud.usa2 --profile soak --duration 30m -y
```

周期约 16 分钟时，半小时能覆盖两次中断。把失败数与报告给出的中断占比对照。

复现客户端的大请求：

```bash
nps-ctl check probe -e nps-america2 -c cloud.usa2 --size 1M --count 50 --concurrency 4
```

## 定时运行

退出码让命令可以直接放进 cron 或 systemd timer：

```bash
*/15 * * * * nps-ctl check links --since 20m --json >> /var/log/nps-check.jsonl
```

建议只把 `links` 放到定时任务里；probe 与 stress 会创建临时对象，更适合发现问题时手工执行。
