"""Shared per-edge status collection.

Both ``edge status`` and ``host status`` render the same per-edge inventory:
reachability, client liveness, host-mapping counts, and distinct target ports.
Keeping the fan-out and failure semantics here avoids two JSON shapes drifting
apart.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any
from urllib.parse import urlsplit

if TYPE_CHECKING:
    from .cluster import NPSCluster
    from .types import HostInfo

MAX_PORT = 65535


@dataclass(frozen=True)
class EdgeStatus:
    """Status and inventory for one edge.

    ``online`` reflects whether the client-list fetch succeeded; ``ok`` also
    requires the host-list fetch to succeed. Counts are ``None`` when their
    fetch failed, so callers never mistake a failure for an empty edge.
    """

    edge: str
    region: str
    api_url: str
    online: bool
    clients_ok: bool
    clients_total: int | None
    clients_online: int | None
    hosts_ok: bool
    hosts_total: int | None
    ports: int | None
    error: str = ""

    @property
    def ok(self) -> bool:
        """Whether every required fetch for this edge succeeded."""
        return self.clients_ok and self.hosts_ok

    @property
    def partial(self) -> bool:
        """Whether the edge answered at least one fetch but not both."""
        return not self.ok and (self.clients_ok or self.hosts_ok)


def extract_target_ports(target: Any) -> set[int]:
    """Return the distinct valid ports in a host target string.

    Args:
        target: A host ``Target`` value: either the normalized dict with a
            ``TargetStr`` key or the raw string. Comma-separated entries are
            accepted, with or without a URL scheme.

    Returns:
        Ports in the range 1..65535.
    """
    if isinstance(target, dict):
        target = target.get("TargetStr", "")
    if not isinstance(target, str):
        return set()

    ports: set[int] = set()
    for part in target.split(","):
        part = part.strip()
        if not part:
            continue
        candidate = part if "://" in part or part.startswith("//") else f"//{part}"
        try:
            port = urlsplit(candidate).port
        except ValueError:
            continue
        if port is not None and 1 <= port <= MAX_PORT:
            ports.add(port)
    return ports


def count_distinct_target_ports(hosts: list[HostInfo]) -> int:
    """Count distinct target ports across host mappings."""
    ports: set[int] = set()
    for entry in hosts:
        ports.update(extract_target_ports(entry.get("Target")))
    return len(ports)


def collect_edge_status(
    cluster: NPSCluster,
    edge_names: list[str] | None = None,
    max_workers: int = 4,
) -> list[EdgeStatus]:
    """Collect status for all or selected edges.

    Args:
        cluster: NPSCluster instance.
        edge_names: Edges to report. ``None`` means every configured edge;
            an empty list means none. Duplicates are collapsed.
        max_workers: Maximum number of parallel workers per fetch.

    Returns:
        One ``EdgeStatus`` per selected edge, in the requested order. Unknown
        names produce an error row without contacting any server.
    """
    if edge_names is None:
        selected = list(cluster.edge_names)
    else:
        selected = list(dict.fromkeys(edge_names))

    configured = set(cluster.edge_names)
    known = [name for name in selected if name in configured]

    clients_results = cluster.get_all_clients(edge_names=known, max_workers=max_workers)
    hosts_results = cluster.get_all_hosts(edge_names=known, max_workers=max_workers)

    rows: list[EdgeStatus] = []
    for name in selected:
        if name not in configured:
            rows.append(
                EdgeStatus(
                    edge=name,
                    region="",
                    api_url="",
                    online=False,
                    clients_ok=False,
                    clients_total=None,
                    clients_online=None,
                    hosts_ok=False,
                    hosts_total=None,
                    ports=None,
                    error=f"Edge '{name}' not found",
                )
            )
            continue

        edge = cluster.get_edge(name)
        clients = clients_results.get(name, [])
        hosts = hosts_results.get(name, [])
        clients_error = clients_results.errors.get(name)
        hosts_error = hosts_results.errors.get(name)
        clients_ok = clients_error is None
        hosts_ok = hosts_error is None

        errors = []
        if clients_error:
            errors.append(f"clients: {clients_error}")
        if hosts_error:
            errors.append(f"hosts: {hosts_error}")

        rows.append(
            EdgeStatus(
                edge=name,
                region=edge.region if edge else "",
                api_url=edge.api_url if edge else "",
                online=clients_ok,
                clients_ok=clients_ok,
                clients_total=len(clients) if clients_ok else None,
                clients_online=(
                    sum(1 for client in clients if client.get("IsConnect"))
                    if clients_ok
                    else None
                ),
                hosts_ok=hosts_ok,
                hosts_total=len(hosts) if hosts_ok else None,
                ports=count_distinct_target_ports(hosts) if hosts_ok else None,
                error="; ".join(errors),
            )
        )

    return rows


def build_status_payload(rows: list[EdgeStatus]) -> dict[str, Any]:
    """Build the shared JSON payload for status commands.

    ``summary`` keeps its existing ``{configured, online, offline}`` shape;
    ``totals`` aggregates the inventory counts.
    """
    online = sum(1 for row in rows if row.online)
    return {
        "edges": [
            {
                "edge": row.edge,
                "region": row.region,
                "api_url": row.api_url,
                "online": row.online,
                "ok": row.ok,
                "partial": row.partial,
                "clients_total": row.clients_total,
                "clients_online": row.clients_online,
                "hosts_total": row.hosts_total,
                "ports": row.ports,
                "error": row.error,
            }
            for row in rows
        ],
        "summary": {
            "configured": len(rows),
            "online": online,
            "offline": len(rows) - online,
        },
        "totals": {
            "ok": sum(1 for row in rows if row.ok),
            "failed": sum(1 for row in rows if not row.online),
            "partial": sum(1 for row in rows if row.partial),
            "clients": sum(row.clients_total or 0 for row in rows),
            "hosts": sum(row.hosts_total or 0 for row in rows),
            "ports": sum(row.ports or 0 for row in rows),
        },
    }
