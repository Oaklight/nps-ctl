"""Collect bridge-link state from NPC client hosts over SSH.

Nothing here generates tunnel traffic. For each NPC client the collector reads
three things in one SSH round trip: the established sockets, the addresses its
configured servers resolve to, and the tail of the NPC log.
"""

from __future__ import annotations

import re
import shlex
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any

from ..deploy import DeployResult, ssh_execute
from .analysis import LinkSummary, assess, summarize
from .model import Finding
from .npc_log import NpcEvent, Outage, find_outages, parse_log

DEFAULT_LOG_PATH = "/var/log/npc.log"
DEFAULT_TAIL_BYTES = 4 * 1024 * 1024
DEFAULT_SINCE = 6 * 3600.0

SshRunner = Callable[..., DeployResult]

_SERVER = re.compile(r"^[A-Za-z0-9._-]+:\d+$")


@dataclass
class ServerLink:
    """One configured bridge server as seen from a client host.

    Attributes:
        host: Hostname the client dials.
        port: Bridge port.
        ips: Addresses the host resolves to on the client.
        established: Whether a socket to one of those addresses exists.
    """

    host: str
    port: int
    ips: list[str] = field(default_factory=list)
    established: bool = False

    @property
    def address(self) -> str:
        """``host:port`` as NPC logs it."""
        return f"{self.host}:{self.port}"


@dataclass
class ClientSnapshot:
    """Raw state collected from one NPC client host.

    Attributes:
        client: Client name from ``clients.toml``.
        ssh_host: SSH host used.
        error: Why collection failed, empty on success.
        npc_pid: PID of the running NPC process, empty when none.
        now: The client's clock at collection time, epoch seconds.
        servers: Configured bridge servers and their socket state.
        events: Link events parsed from the log tail.
    """

    client: str
    ssh_host: str
    error: str = ""
    npc_pid: str = ""
    now: float = 0.0
    servers: list[ServerLink] = field(default_factory=list)
    events: list[NpcEvent] = field(default_factory=list)


@dataclass
class LinkReport:
    """Assessment of one (client, server) bridge link.

    Attributes:
        client: Client name.
        server: ``host:port`` of the bridge.
        edge: Edge name whose API host matches the server, empty if unknown.
        established: Whether a bridge socket exists now.
        summary: Outage statistics over the examined window.
        outages: The outages themselves, for correlation.
        findings: Findings about this link.
    """

    client: str
    server: str
    edge: str
    established: bool
    summary: LinkSummary
    outages: list[Outage]
    findings: list[Finding]

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serialisable mapping."""
        return {
            "client": self.client,
            "server": self.server,
            "edge": self.edge,
            "established": self.established,
            "summary": self.summary.to_dict(),
            "findings": [finding.to_dict() for finding in self.findings],
        }


def sudo_prefix(ssh_user: str) -> str:
    """Return ``sudo `` for an explicitly non-root SSH user, else ``""``."""
    return "sudo " if ssh_user and ssh_user != "root" else ""


def build_script(
    servers: list[str], log_path: str, tail_bytes: int, sudo: str = ""
) -> str:
    """Build the shell script that gathers a client's link state.

    Args:
        servers: ``host:port`` bridge addresses to resolve and look for.
        log_path: NPC log path on the client.
        tail_bytes: How much of the log's end to return.
        sudo: Command prefix for reading the log, ``""`` or ``"sudo "``.

    Returns:
        A bash script. Output is line oriented: ``NOW``, ``PID``, ``SERVER``,
        ``ESTAB`` lines, then the log between ``LOG_BEGIN`` and ``LOG_END``.

    Raises:
        ValueError: If a server address is not a plain ``host:port``.
    """
    for server in servers:
        if not _SERVER.match(server):
            raise ValueError(f"unsafe server address {server!r}")
    listed = " ".join(shlex.quote(server) for server in servers)
    return f"""set -u
echo "NOW $(date +%s)"
echo "PID $(pgrep -x npc | head -1)"
for s in {listed}; do
  host=${{s%:*}}; port=${{s##*:}}
  ips=$(getent ahosts "$host" 2>/dev/null | awk '{{print $1}}' | sort -u | paste -sd' ' -)
  echo "SERVER $host $port $ips"
done
ss -tn state established 2>/dev/null | awk 'NR>1 {{print "ESTAB " $4}}'
echo "LOG_BEGIN"
{sudo}tail -c {int(tail_bytes)} {shlex.quote(log_path)} 2>/dev/null
echo "LOG_END"
"""


def parse_output(stdout: str) -> tuple[str, float, list[ServerLink], str]:
    """Parse the output of :func:`build_script`.

    Args:
        stdout: Script output.

    Returns:
        ``(npc_pid, now, servers, log_text)`` with socket state filled in.
    """
    pid = ""
    now = 0.0
    servers: list[ServerLink] = []
    peers: set[str] = set()
    log_lines: list[str] = []
    in_log = False
    for line in stdout.splitlines():
        if in_log:
            if line == "LOG_END":
                in_log = False
            else:
                log_lines.append(line)
        elif line == "LOG_BEGIN":
            in_log = True
        elif line.startswith("NOW "):
            now = float(line.split()[1])
        elif line.startswith("PID"):
            pid = line[3:].strip()
        elif line.startswith("SERVER "):
            parts = line.split()
            servers.append(ServerLink(parts[1], int(parts[2]), parts[3:]))
        elif line.startswith("ESTAB "):
            peers.add(line.split()[1])
    for server in servers:
        server.established = any(
            f"{ip}:{server.port}" in peers or f"[{ip}]:{server.port}" in peers
            for ip in server.ips
        )
    return pid, now, servers, "\n".join(log_lines)


def collect_client(
    client: str,
    ssh_host: str,
    servers: list[str],
    *,
    ssh_user: str = "",
    log_path: str = DEFAULT_LOG_PATH,
    tail_bytes: int = DEFAULT_TAIL_BYTES,
    ssh: SshRunner = ssh_execute,
) -> ClientSnapshot:
    """Collect the link state of one NPC client host.

    Args:
        client: Client name.
        ssh_host: SSH host of the client.
        servers: ``host:port`` bridge addresses the client is configured with.
        ssh_user: SSH login user; a non-root user reads the log with sudo.
        log_path: NPC log path on the client.
        tail_bytes: How much of the log's end to read.
        ssh: SSH runner, replaceable in tests.

    Returns:
        A snapshot; ``error`` is set instead of raising when SSH fails.
    """
    snapshot = ClientSnapshot(client=client, ssh_host=ssh_host)
    try:
        script = build_script(servers, log_path, tail_bytes, sudo_prefix(ssh_user))
    except ValueError as exc:
        snapshot.error = str(exc)
        return snapshot
    result = ssh(ssh_host, script, timeout=60, ssh_user=ssh_user)
    if not result.success:
        snapshot.error = result.message
        return snapshot
    pid, now, links, log_text = parse_output(result.stdout)
    snapshot.npc_pid = pid
    snapshot.now = now
    snapshot.servers = links
    snapshot.events = parse_log(log_text)
    if not pid:
        snapshot.error = "npc is not running"
    return snapshot


def report_for(
    snapshot: ClientSnapshot, since: float, edge_by_host: dict[str, str]
) -> tuple[list[LinkReport], list[Outage]]:
    """Assess every bridge link of a collected client.

    Outages whose server is not among the configured ones are returned
    separately rather than dropped: a bridge-port change or a client whose
    config drifted would otherwise make a real outage look like a healthy
    link.

    Args:
        snapshot: Output of :func:`collect_client`.
        since: Window length in seconds, ending at the client's clock.
        edge_by_host: Server hostname -> edge name, for display.

    Returns:
        ``(reports, unattributed)``: one report per configured server in
        configured order, and the outages no configured server matched.
    """
    cutoff = snapshot.now - since
    events = [event for event in snapshot.events if event.time >= cutoff]
    outages = find_outages(events)
    known = {server.address for server in snapshot.servers}
    unattributed = [outage for outage in outages if outage.server not in known]
    reports: list[LinkReport] = []
    for server in snapshot.servers:
        mine = [o for o in outages if o.server == server.address]
        summary = summarize(mine, snapshot.now, since)
        subject = f"{snapshot.client} -> {edge_by_host.get(server.host, server.host)}"
        reports.append(
            LinkReport(
                client=snapshot.client,
                server=server.address,
                edge=edge_by_host.get(server.host, ""),
                established=server.established,
                summary=summary,
                outages=mine,
                findings=assess(summary, server.established, subject),
            )
        )
    return reports, unattributed


def collect_links(
    cluster: Any,
    client_names: list[str],
    *,
    since: float = DEFAULT_SINCE,
    log_path: str = DEFAULT_LOG_PATH,
    tail_bytes: int = DEFAULT_TAIL_BYTES,
    ssh: SshRunner = ssh_execute,
    max_workers: int = 4,
) -> tuple[list[LinkReport], dict[str, str], dict[str, list[Outage]]]:
    """Collect and assess the bridge links of several NPC clients.

    Args:
        cluster: A cluster exposing ``get_npc_client``, ``get_edge`` and
            ``get_server_addrs_for_npc``.
        client_names: Clients to inspect.
        since: Window length in seconds.
        log_path: NPC log path on the clients.
        tail_bytes: How much of each log's end to read.
        ssh: SSH runner, replaceable in tests.
        max_workers: Clients inspected in parallel.

    Returns:
        ``(reports, errors, unattributed)``: link reports for clients that
        answered, a client -> reason mapping for those that did not, and, per
        client, the outages whose server no configured bridge matched.
    """

    def one(name: str) -> tuple[str, ClientSnapshot, dict[str, str]]:
        config = cluster.get_npc_client(name)
        servers = [s for s in cluster.get_server_addrs_for_npc(config).split(",") if s]
        edge_by_host = {}
        for edge_name in config.edges:
            edge = cluster.get_edge(edge_name)
            if edge is not None:
                host = edge.api_url.split("://", 1)[-1].split("/", 1)[0]
                edge_by_host[host] = edge_name
        snapshot = collect_client(
            name,
            config.ssh_host,
            servers,
            ssh_user=config.ssh_user,
            log_path=log_path,
            tail_bytes=tail_bytes,
            ssh=ssh,
        )
        return name, snapshot, edge_by_host

    reports: list[LinkReport] = []
    errors: dict[str, str] = {}
    unattributed: dict[str, list[Outage]] = {}
    with ThreadPoolExecutor(
        max_workers=max(1, min(max_workers, len(client_names)))
    ) as pool:
        outcomes = list(pool.map(one, client_names))
    for name, snapshot, edge_by_host in outcomes:
        if snapshot.error and not snapshot.servers:
            errors[name] = snapshot.error
            continue
        client_reports, orphans = report_for(snapshot, since, edge_by_host)
        reports.extend(client_reports)
        if orphans:
            unattributed[name] = orphans
        if snapshot.error:
            errors[name] = snapshot.error
    return reports, errors, unattributed
