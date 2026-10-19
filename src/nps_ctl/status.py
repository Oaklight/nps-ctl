"""Shared per-edge status collection.

``edge status``, ``host status``, ``tunnel status``, and the web dashboard
render the same per-edge inventory: reachability, client liveness, and the
counts for the requested resources. Keeping the fan-out and failure semantics
here prevents their JSON shapes from drifting apart.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any
from urllib.parse import urlsplit

if TYPE_CHECKING:
    from .cluster import NPSCluster
    from .types import HostInfo, TunnelInfo

MAX_PORT = 65535


@dataclass(frozen=True)
class EdgeStatus:
    """Status and inventory for one edge.

    ``online`` reflects whether the client-list fetch succeeded. ``ok`` also
    requires every requested resource fetch to succeed. ``hosts_ok`` and
    ``tunnels_ok`` are ``None`` when that resource was not requested. Counts
    are ``None`` when their fetch failed, so callers never mistake a failure
    for an empty edge.
    """

    edge: str
    region: str
    api_url: str
    online: bool
    clients_ok: bool
    clients_total: int | None
    clients_online: int | None
    hosts_ok: bool | None
    hosts_total: int | None
    ports: int | None
    error: str = ""
    tunnels_ok: bool | None = None
    tunnels_total: int | None = None
    tunnels_running: int | None = None
    tunnel_ports: int | None = None

    @property
    def ok(self) -> bool:
        """Whether every requested fetch for this edge succeeded."""
        return (
            self.clients_ok
            and self.hosts_ok is not False
            and self.tunnels_ok is not False
        )

    @property
    def partial(self) -> bool:
        """Whether at least one requested fetch succeeded but not all."""
        return not self.ok and any(
            value is True for value in (self.clients_ok, self.hosts_ok, self.tunnels_ok)
        )


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


def _coerce_port(value: Any) -> int | None:
    """Return a valid port from an int or numeric string, else None."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        port = value
    elif isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            port = int(text)
        except ValueError:
            return None
    else:
        return None
    if 1 <= port <= MAX_PORT:
        return port
    return None


def _parse_ports(value: Any) -> set[int]:
    """Parse a Port or Ports value into a set of valid ports.

    Mirrors the server's ``common.GetPorts``: comma-separated items, single
    ports and inclusive ``start-end`` ranges, whitespace around the dash and
    around each item is ignored, and a reversed range is swapped before it is
    expanded. A list/tuple is treated as a comma-separated list. Malformed
    tokens and out-of-range values are ignored.
    """
    if isinstance(value, (list, tuple)):
        value = ",".join(str(item) for item in value)
    elif not isinstance(value, str):
        port = _coerce_port(value)
        return {port} if port is not None else set()

    ports: set[int] = set()
    for item in value.split(","):
        item = item.strip()
        if not item:
            continue
        start_text, separator, end_text = item.partition("-")
        if separator:
            start = _coerce_port(start_text)
            end = _coerce_port(end_text)
            if start is None or end is None:
                continue
            if end < start:
                start, end = end, start
            ports.update(range(start, end + 1))
            continue
        port = _coerce_port(item)
        if port is not None:
            ports.add(port)
    return ports


def extract_tunnel_ports(tunnel: TunnelInfo) -> set[int]:
    """Return the distinct valid server ports a tunnel exposes.

    Counts every tunnel mode. Auto-assigned or invalid ports (``0``,
    negatives, values over 65535, malformed ranges) are ignored.
    """
    ports = _parse_ports(tunnel.get("Port"))
    ports.update(_parse_ports(tunnel.get("Ports")))
    return ports


def count_distinct_tunnel_ports(tunnels: list[TunnelInfo]) -> int:
    """Count distinct valid server ports across tunnels."""
    ports: set[int] = set()
    for tunnel in tunnels:
        ports.update(extract_tunnel_ports(tunnel))
    return len(ports)


def _fetch_resources(
    cluster: NPSCluster,
    known: list[str],
    max_workers: int,
    *,
    include_hosts: bool,
    include_tunnels: bool,
) -> dict[str, Any]:
    """Fetch the requested resource inventories concurrently."""
    specs: list[tuple[str, Any]] = [
        (
            "clients",
            lambda: cluster.get_all_clients(edge_names=known, max_workers=max_workers),
        )
    ]
    if include_hosts:
        specs.append(
            (
                "hosts",
                lambda: cluster.get_all_hosts(
                    edge_names=known, max_workers=max_workers
                ),
            )
        )
    if include_tunnels:
        specs.append(
            (
                "tunnels",
                lambda: cluster.get_all_tunnels(
                    edge_names=known, max_workers=max_workers
                ),
            )
        )

    with ThreadPoolExecutor(max_workers=len(specs)) as executor:
        futures = {name: executor.submit(fetch) for name, fetch in specs}
        return {name: future.result() for name, future in futures.items()}


def client_identity(client: Any) -> str:
    """Return a cross-edge identity for a client.

    Client IDs are assigned per edge, so replicas are matched on VerifyKey
    (as ``sync_from`` does), falling back to the remark. A client with
    neither returns ``""``; ``_inventory`` then keys it by edge and ID, so
    such clients are counted separately rather than merged (over-counting is
    the safer error for drift).
    """
    if not isinstance(client, dict):
        return ""
    vkey = client.get("VerifyKey") or ""
    if vkey:
        return f"vkey:{vkey}"
    remark = client.get("Remark") or ""
    return f"remark:{remark}" if remark else ""


def tunnel_identity(tunnel: Any) -> tuple[Any, ...]:
    """Return a cross-edge identity for a tunnel.

    Keyed on owner, mode and server ports; ports come from both ``Port`` and
    ``Ports``, so multi-port tunnels (``Port: 0`` with a ``Ports`` range)
    stay distinct. Tunnels with no server port at all (``secret``, ``file``,
    ``p2p``) are further keyed on remark and target, which replicas share.
    """
    if not isinstance(tunnel, dict):
        return ("", "", ())
    ports = tuple(sorted(extract_tunnel_ports(tunnel)))
    key: tuple[Any, ...] = (
        client_identity(tunnel.get("Client") or {}),
        str(tunnel.get("Mode", "")),
        ports,
    )
    if not ports:
        target = tunnel.get("Target")
        if isinstance(target, dict):
            target = target.get("TargetStr", "")
        key += (str(tunnel.get("Remark") or ""), str(target or ""))
    return key


def host_identity(entry: Any) -> tuple[str, str]:
    """Return a cross-edge identity for a host mapping: domain and location.

    The owning client is deliberately not part of the key: a domain and
    location route to a single target, so the same pair published by two
    clients is a conflict, not two resources.
    """
    if not isinstance(entry, dict):
        return ("", "")
    return (str(entry.get("Host", "")), str(entry.get("Location") or "/"))


RESOURCE_IDENTITIES: dict[str, Any] = {
    "clients": client_identity,
    "tunnels": tunnel_identity,
    "hosts": host_identity,
}


@dataclass(frozen=True)
class ClusterStatus:
    """Per-edge status plus cross-edge inventory.

    Edges are usually replicas of one another, so summing per-edge counts
    overstates the cluster. ``unique`` counts distinct resources across the
    edges that answered (``None`` when no edge answered, absent when the
    resource was not requested). ``missing`` maps each answering edge to how
    many of those distinct resources it lacks. ``unknown`` lists, per edge,
    the requested resources it failed to report; such an edge cannot be
    called in sync.
    """

    rows: list[EdgeStatus]
    unique: dict[str, int | None]
    missing: dict[str, dict[str, int]]
    unknown: dict[str, list[str]]

    def in_sync(self, edge: str) -> bool:
        """Whether an edge reported every resource and lacks none."""
        return (
            edge in self.missing
            and not self.unknown.get(edge)
            and not any(self.missing[edge].values())
        )


def _inventory(
    fetched: dict[str, Any], known: list[str]
) -> tuple[dict[str, int | None], dict[str, dict[str, int]], dict[str, list[str]]]:
    """Compute distinct resource counts, per-edge gaps, and unknowns."""
    unique: dict[str, int | None] = {}
    missing: dict[str, dict[str, int]] = {name: {} for name in known}
    unknown: dict[str, list[str]] = {name: [] for name in known}
    for resource, results in fetched.items():
        identity = RESOURCE_IDENTITIES[resource]

        def key(name: str, item: Any) -> Any:
            # Anonymous items are edge-local: never matched across edges.
            return identity(item) or (name, "id", item.get("Id"))

        per_edge: dict[str, set[Any]] = {}
        for name in known:
            if name in results.errors:
                unknown[name].append(resource)
            else:
                per_edge[name] = {key(name, item) for item in results.get(name, [])}
        union: set[Any] = set().union(*per_edge.values())
        unique[resource] = len(union) if per_edge else None
        for name, keys in per_edge.items():
            missing[name][resource] = len(union - keys)
    return unique, missing, unknown


def collect_edge_status(
    cluster: NPSCluster,
    edge_names: list[str] | None = None,
    max_workers: int = 4,
    *,
    include_hosts: bool = True,
    include_tunnels: bool = False,
) -> list[EdgeStatus]:
    """Collect status for all or selected edges.

    See :func:`collect_cluster_status` for arguments; this returns only the
    per-edge rows.
    """
    return collect_cluster_status(
        cluster,
        edge_names,
        max_workers,
        include_hosts=include_hosts,
        include_tunnels=include_tunnels,
    ).rows


def collect_cluster_status(
    cluster: NPSCluster,
    edge_names: list[str] | None = None,
    max_workers: int = 4,
    *,
    include_hosts: bool = True,
    include_tunnels: bool = False,
) -> ClusterStatus:
    """Collect per-edge status and cross-edge inventory.

    Args:
        cluster: NPSCluster instance.
        edge_names: Edges to report. ``None`` means every configured edge;
            an empty list means none. Duplicates are collapsed.
        max_workers: Maximum number of parallel workers per edge fetch.
        include_hosts: Fetch host mappings and target-port counts.
        include_tunnels: Fetch tunnels, running state, and server-port counts.

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

    fetched = _fetch_resources(
        cluster,
        known,
        max_workers,
        include_hosts=include_hosts,
        include_tunnels=include_tunnels,
    )
    clients_results = fetched["clients"]
    hosts_results = fetched.get("hosts")
    tunnels_results = fetched.get("tunnels")

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
                    hosts_ok=False if include_hosts else None,
                    hosts_total=None,
                    ports=None,
                    error=f"Edge '{name}' not found",
                    tunnels_ok=False if include_tunnels else None,
                    tunnels_total=None,
                    tunnels_running=None,
                    tunnel_ports=None,
                )
            )
            continue

        edge = cluster.get_edge(name)
        clients = clients_results.get(name, [])
        clients_error = clients_results.errors.get(name)
        clients_ok = clients_error is None

        errors: list[str] = []
        if clients_error:
            errors.append(f"clients: {clients_error}")

        hosts_ok: bool | None = None
        hosts: list[HostInfo] = []
        if hosts_results is not None:
            hosts = hosts_results.get(name, [])
            hosts_error = hosts_results.errors.get(name)
            hosts_ok = hosts_error is None
            if hosts_error:
                errors.append(f"hosts: {hosts_error}")

        tunnels_ok: bool | None = None
        tunnels: list[TunnelInfo] = []
        if tunnels_results is not None:
            tunnels = tunnels_results.get(name, [])
            tunnels_error = tunnels_results.errors.get(name)
            tunnels_ok = tunnels_error is None
            if tunnels_error:
                errors.append(f"tunnels: {tunnels_error}")

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
                tunnels_ok=tunnels_ok,
                tunnels_total=len(tunnels) if tunnels_ok else None,
                tunnels_running=(
                    sum(1 for tunnel in tunnels if tunnel.get("RunStatus"))
                    if tunnels_ok
                    else None
                ),
                tunnel_ports=(
                    count_distinct_tunnel_ports(tunnels) if tunnels_ok else None
                ),
            )
        )

    unique, missing, unknown = _inventory(fetched, known)
    return ClusterStatus(rows=rows, unique=unique, missing=missing, unknown=unknown)


def sum_counts(values: list[int | None]) -> int | None:
    """Sum counts, or return None when any edge failed to report."""
    if any(value is None for value in values):
        return None
    return sum(value or 0 for value in values)


def build_status_payload(rows: list[EdgeStatus]) -> dict[str, Any]:
    """Build the shared JSON payload for status commands and the dashboard.

    ``summary`` keeps its existing ``{configured, online, offline}`` shape;
    ``totals`` aggregates the inventory counts, using ``null`` when any edge
    could not report so the JSON and the text footer always agree.
    ``totals.ok``, ``totals.partial``, and ``totals.failed`` partition the
    selected rows.
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
                "clients_ok": row.clients_ok,
                "clients_total": row.clients_total,
                "clients_online": row.clients_online,
                "hosts_ok": row.hosts_ok,
                "hosts_total": row.hosts_total,
                "ports": row.ports,
                "tunnels_ok": row.tunnels_ok,
                "tunnels_total": row.tunnels_total,
                "tunnels_running": row.tunnels_running,
                "tunnel_ports": row.tunnel_ports,
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
            "failed": sum(1 for row in rows if not row.online and not row.partial),
            "partial": sum(1 for row in rows if row.partial),
            "clients": sum_counts([row.clients_total for row in rows]),
            "hosts": sum_counts([row.hosts_total for row in rows]),
            "ports": sum_counts([row.ports for row in rows]),
            "tunnels": sum_counts([row.tunnels_total for row in rows]),
            "tunnels_running": sum_counts([row.tunnels_running for row in rows]),
            "tunnel_ports": sum_counts([row.tunnel_ports for row in rows]),
        },
    }
