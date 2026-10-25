---
title: Tunnel Health Checks
---

# Tunnel Health Checks

`nps-ctl check` answers two different questions about a deployment:

- `check links` asks whether the bridges between NPC clients and NPS edges stay up. It only reads.
- `check probe` and `check stress` ask whether the data crossing a tunnel arrives intact. They send traffic and temporarily change one edge.

All three take their topology from `edges.toml` and `clients.toml`, so nothing has to be described twice.

## Link health

```bash
nps-ctl check links                      # every NPC client, last 6 hours
nps-ctl check links -c cloud.usa2        # one client
nps-ctl check links --since 24h --json
```

For each NPC client, the command opens one SSH session and reads three things: the established sockets, the addresses the configured edges resolve to, and the tail of the NPC log. It then reports one row per (client, edge) pair:

| Column | Meaning |
|--------|---------|
| Outages | Bridge outages that started in the window |
| Median, Max | Outage length |
| Down | Share of the window the link was down |
| Period | Median gap between outage starts, marked `*` when at least 60% of the gaps lie within 15% of it |

A ping timeout opens an outage that starts at the last answered ping, not at the moment NPC noticed. The edge a timeout belongs to is named by the `Start server` line that follows it, because the timeout line itself carries no server. An outage ends at the next `Successful connection`. This is why a link can be reported as "down 5% of the time" while the same log looks healthy at a glance.

The exit code is 1 when a link is down, a client cannot be reached, or a link flaps three times or more in the window. Add `--fail-on error` to ignore warnings.

The periodic pattern is worth reading closely. Outages every 16 minutes on one edge, seen from every client in every region, point at the edge or the path to it rather than at any single client.

## Data integrity

`check links` shows when a bridge was down. It cannot show whether a request that crossed while it flapped arrived intact, and that is what `check probe` and `check stress` are for.

```bash
nps-ctl check probe -e nps-america2 -c cloud.usa2 --size 256K --count 30
nps-ctl check stress -e nps-europe -c cloud.usa2 --profile soak --duration 30m
```

A run does five things:

1. Starts a hash-echo service on the client host, bound to `127.0.0.1` on a free port, with an hour-long self-destruct.
2. Adds a host mapping on the chosen edge for a throwaway domain (`nps-ctl-check-<token>.nps-ctl-check.invalid`) pointing at that port.
3. Sends a baseline through the echo directly on the client host, with no tunnel.
4. Sends the same kind of load from the edge host through NPS's HTTP proxy, using the throwaway domain.
5. Removes the host mapping and stops the echo service.

Every request body is generated from the run token and the request index, so no two bodies are alike. The echo service answers with the body's length, its SHA-256 and one short hash per 64 KiB block. A reply that differs from what was sent means the body was truncated, extended, or had bytes spliced in from another concurrent request, and the block hashes say where. Uniform bodies would prove only that something arrived; these bodies prove that the right bytes arrived.

The baseline matters. If it fails, the tunnel numbers mean nothing, and the command reports that instead of blaming the path.

Options shared by `probe` and `stress`:

| Flag | Meaning |
|------|---------|
| `-e/--edge` | Edge whose tunnel to test (required) |
| `-c/--client` | NPC client from `clients.toml` (required) |
| `--http-proxy-port` | NPS HTTP proxy port; read from the edge's `nps.conf`, else 30080 |
| `--fail-on` | `error` (default) or `warn` |
| `--dry-run` | Print the plan and change nothing |
| `-y/--yes` | Skip the confirmation prompt |
| `--json` | Machine-readable output |

`probe` sends one step: `--size` (`64K`, `1M`), `--count`, `--concurrency`, and optionally `--mode slow` with `--chunk-kb` and `--gap-ms` to send a body in small pieces with pauses, which is closer to how a language model client uploads a long conversation.

`stress` sends a named profile:

| Profile | What it does |
|---------|--------------|
| `smoke` | 30 requests of 256 KiB at concurrency 4 |
| `ladder` | 64 KiB and 1 MiB bodies at concurrency 1, 2, 4, 8 and 16 |
| `slow` | Slow uploaders: 16 KiB chunks every 20 ms, then 4 KiB every 10 ms |
| `churn` | 400 small requests at concurrency 16 |
| `soak` | Steady load for `--duration` (default 10m), sized to catch a periodic fault |

When a run has failures, `stress` reads the client's NPC log for the same window and reports how many failures fall inside logged outages, next to the share of the run those outages cover. A result of "9 of 9 failures inside outages that cover 9% of the run" is evidence for the link; failures with no outage anywhere near them are evidence against it.

## What a run leaves behind

Nothing, if all goes well. Both the host mapping and the echo service are removed when the command exits, including after a failure part-way through setup. Cleanup is checked rather than assumed: the mapping is looked up again after the delete, and the echo service is stopped by a handle the command created. If either step fails, the finding `cleanup_failed` names what is left and the command exits 1.

Two safeguards keep the session away from real configuration. The domain is always a fresh `nps-ctl-check-*.nps-ctl-check.invalid`, and a mapping is only deleted if its host and remark are the ones this session wrote.

A probe session needs `python3` on both the edge host and the client host. Both shipped helpers use only the standard library.

## Recipes

Check whether one edge is the problem:

```bash
nps-ctl check links --since 24h
```

If one edge flaps from every client, it is the edge. If one client flaps against every edge, it is the client's network.

Watch a flapping link for damage:

```bash
nps-ctl check stress -e nps-europe -c cloud.usa2 --profile soak --duration 30m -y
```

With a period near 16 minutes, half an hour covers two outages. Compare the failure count with the outage coverage the report prints.

Reproduce a client's large uploads:

```bash
nps-ctl check probe -e nps-america2 -c cloud.usa2 --size 1M --count 50 --concurrency 4
```

## Scheduling

The exit code makes the command usable from cron or a timer:

```bash
*/15 * * * * nps-ctl check links --since 20m --json >> /var/log/nps-check.jsonl
```

Keep `links` on a schedule; the probe and stress commands create temporary objects and are better run by hand when something looks wrong.
