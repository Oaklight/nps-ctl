"""NPS cluster management for multiple NPS servers.

This module provides NPSCluster for managing multiple NPS edge nodes,
including broadcasting operations and syncing configurations.
"""

import logging
import random
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from functools import partial
from pathlib import Path
from threading import Lock
from typing import Any, TypeVar, cast
from collections.abc import Callable

import tomllib
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
)

from . import client_mgmt, host, tunnel
from .base import NPSClient
from .exceptions import NPSError
from .logging import FlushingConsole, OperationContext, get_operation_logger
from .types import (
    ClientIdMapping,
    ClientInfo,
    EdgeConfig,
    EdgeResults,
    HostInfo,
    NPCClientConfig,
    TunnelInfo,
)

logger = logging.getLogger(__name__)
op_logger = get_operation_logger(__name__)

T = TypeVar("T")

# Union of all NPS API item types
SyncItem = ClientInfo | TunnelInfo | HostInfo

# Rich console for output with forced flush for streaming.
# FlushingConsole keeps output unbuffered through proxies. When stdout is not
# a terminal, use an effectively unlimited width so table cells are not wrapped.
console = FlushingConsole(width=None if sys.stdout.isatty() else 10000)


class RateLimiter:
    """Simple rate limiter to control request frequency.

    This helps prevent overwhelming servers with too many concurrent requests.
    """

    def __init__(self, min_interval: float = 0.2, jitter: float = 0.1):
        """Initialize rate limiter.

        Args:
            min_interval: Minimum interval between requests in seconds.
            jitter: Random jitter to add (0 to jitter seconds).
        """
        self._min_interval = min_interval
        self._jitter = jitter
        self._lock = Lock()
        self._last_request_time = 0.0

    def wait(self) -> None:
        """Wait until it's safe to make the next request."""
        with self._lock:
            now = time.perf_counter()
            elapsed = now - self._last_request_time
            wait_time = self._min_interval - elapsed

            if wait_time > 0:
                # Add random jitter to prevent thundering herd
                jitter = random.uniform(0, self._jitter)
                time.sleep(wait_time + jitter)

            self._last_request_time = time.perf_counter()


@dataclass
class _TargetSnapshot:
    """Existing resources on one target edge, used by both add and prune.

    ``clients`` is None when the target could not be queried, which aborts the
    sync for that edge. The key sets are the identity used by the add phase;
    the row lists let ``--prune`` delete resources the source does not have.
    """

    clients: list[ClientInfo] | None
    vkeys: set[str]
    tunnels: list[TunnelInfo]
    tunnel_keys: set[tuple[int, str, int]]
    hosts: list[HostInfo]
    host_keys: set[tuple[str, str]]
    tunnels_ok: bool = True
    hosts_ok: bool = True


@dataclass
class NPSCluster:
    """Manager for multiple NPS servers.

    Args:
        config_path: Path to the edges.toml configuration file.
        proxy: HTTP/HTTPS proxy URL for all API requests.
        socks_proxy: SOCKS5 proxy address for SSH tunnel (e.g., "localhost:1080").

    Example:
        >>> cluster = NPSCluster("config/edges.toml")
        >>> for name, clients in cluster.get_all_clients().items():
        ...     print(f"{name}: {len(clients)} clients")
    """

    config_path: str | Path
    proxy: str | None = None
    socks_proxy: str | None = None
    _edges: dict[str, EdgeConfig] = field(default_factory=dict, init=False)
    _clients: dict[str, NPSClient] = field(default_factory=dict, init=False)
    _npc_clients: dict[str, NPCClientConfig] = field(default_factory=dict, init=False)
    _primary: str = field(default="", init=False)

    def __post_init__(self) -> None:
        """Load configuration and initialize clients."""
        self._load_config()

    def cleanup(self) -> None:
        """Clean up all NPSClient instances (restore socket if SOCKS was used)."""
        for nps_client in self._clients.values():
            nps_client.cleanup()

    def __enter__(self) -> "NPSCluster":
        """Enter context manager."""
        return self

    def __exit__(self, *exc: object) -> None:
        """Exit context manager, cleaning up all clients."""
        self.cleanup()

    def __del__(self) -> None:
        """Clean up on garbage collection."""
        self.cleanup()

    def _load_config(self) -> None:
        """Load edge configuration from TOML file."""
        path = Path(self.config_path)
        if not path.exists():
            raise FileNotFoundError(f"Config file not found: {path}")

        op_logger.phase_info(f"Loading cluster configuration from {path}")

        with open(path, "rb") as f:
            config = tomllib.load(f)

        self._primary = str(config.get("primary", "") or "")
        edges = config.get("edges", [])
        for edge in edges:
            edge_config = EdgeConfig(
                name=edge["name"],
                api_url=edge["api_url"],
                auth_key=edge.get("auth_key", ""),
                region=edge.get("region", ""),
                ssh_host=edge.get("ssh_host", ""),
                username=edge.get("username", ""),
                password=edge.get("password", ""),
                platform_token=edge.get("platform_token", ""),
                api_mode=edge.get("api_mode", "auto"),
            )
            self._edges[edge_config.name] = edge_config
            previous = self._clients.get(edge_config.name)
            if previous is not None:
                previous.cleanup()
            self._clients[edge_config.name] = NPSClient(
                base_url=edge_config.api_url,
                auth_key=edge_config.auth_key,
                proxy=self.proxy,
                socks_proxy=self.socks_proxy,
                username=edge_config.username,
                password=edge_config.password,
                platform_token=edge_config.platform_token,
                api_mode=edge_config.api_mode,
            )
            logger.debug(
                f"Registered edge: {edge_config.name} ({edge_config.region}) "
                f"-> {edge_config.api_url}"
            )

        # Load NPC clients configuration
        npc_clients = config.get("clients", [])
        for npc_client in npc_clients:
            npc_config = NPCClientConfig(
                name=npc_client["name"],
                ssh_host=npc_client["ssh_host"],
                edges=npc_client.get("edges", []),
                vkey=npc_client.get("vkey", ""),
                remark=npc_client.get("remark", ""),
                conn_type=npc_client.get("conn_type", "tls"),
                ssh_user=npc_client.get("ssh_user", ""),
                http_proxy=npc_client.get("http_proxy", ""),
            )
            self._npc_clients[npc_config.name] = npc_config
            logger.debug(
                f"Registered NPC client: {npc_config.name} -> {npc_config.ssh_host}"
            )

        # Load NPC clients from clients.toml if it exists (takes precedence)
        clients_config_path = path.parent / "clients.toml"
        if clients_config_path.exists():
            with open(clients_config_path, "rb") as f:
                clients_config = tomllib.load(f)
            for npc_client in clients_config.get("clients", []):
                npc_config = NPCClientConfig(
                    name=npc_client["name"],
                    ssh_host=npc_client["ssh_host"],
                    edges=npc_client.get("edges", []),
                    vkey=npc_client.get("vkey", ""),
                    remark=npc_client.get("remark", ""),
                    conn_type=npc_client.get("conn_type", "tls"),
                    ssh_user=npc_client.get("ssh_user", ""),
                    http_proxy=npc_client.get("http_proxy", ""),
                )
                self._npc_clients[npc_config.name] = npc_config
            logger.debug(
                "Loaded %d NPC client(s) from %s",
                len(clients_config.get("clients", [])),
                clients_config_path,
            )

        op_logger.phase_info(f"Cluster initialized with {len(self._edges)} edges")

    def reload(self) -> None:
        """Reload edges.toml into this cluster instance.

        Existing edges are refreshed and new entries are added in place. Edges
        removed from the file are not dropped; construct a new ``NPSCluster``
        when a full replacement is required.
        """
        self._load_config()

    @property
    def clients_config_path(self) -> Path:
        """Path to the clients.toml configuration file."""
        return Path(self.config_path).parent / "clients.toml"

    @property
    def edge_names(self) -> list[str]:
        """Get list of all edge names."""
        return list(self._edges.keys())

    @property
    def primary_edge(self) -> str | None:
        """Configured primary edge, or None when unset or not a known edge.

        The primary is the source of truth that ``edge sync`` aligns the
        other edges with when no explicit source is given.
        """
        return self._primary if self._primary in self._edges else None

    @property
    def configured_primary(self) -> str:
        """Raw ``primary`` value from edges.toml (may name an unknown edge)."""
        return self._primary

    @property
    def npc_client_names(self) -> list[str]:
        """Get list of all NPC client names."""
        return list(self._npc_clients.keys())

    def get_edge(self, name: str) -> EdgeConfig | None:
        """Get edge configuration by name.

        Args:
            name: Edge name.

        Returns:
            EdgeConfig or None if not found.
        """
        return self._edges.get(name)

    def get_client(self, name: str) -> NPSClient | None:
        """Get NPS API client by edge name.

        Args:
            name: Edge name.

        Returns:
            NPSClient or None if not found.
        """
        return self._clients.get(name)

    def get_npc_client(self, name: str) -> NPCClientConfig | None:
        """Get NPC client configuration by name.

        Args:
            name: NPC client name.

        Returns:
            NPCClientConfig or None if not found.
        """
        return self._npc_clients.get(name)

    def get_vkey_for_npc(self, npc_config: NPCClientConfig) -> str | None:
        """Get vkey for an NPC client.

        If vkey is configured, return it directly.
        Otherwise, query the NPS API to find the client by remark.

        Args:
            npc_config: NPC client configuration.

        Returns:
            vkey string or None if not found.
        """
        # If vkey is configured, use it directly
        if npc_config.vkey:
            logger.debug(f"Using configured vkey for {npc_config.name}")
            return npc_config.vkey

        # Otherwise, query from NPS API
        remark = npc_config.remark  # Already defaults to name in __post_init__

        # Try to get vkey from any available edge
        for edge_name in self._clients.keys():
            try:
                nps = self._clients[edge_name]
                clients = client_mgmt.list_clients(nps, search=remark)
                matching = [c for c in clients if c.get("Remark") == remark]
                if matching:
                    vkey = matching[0].get("VerifyKey", "")
                    if vkey:
                        logger.debug(
                            f"Found vkey for {npc_config.name} from {edge_name}"
                        )
                        return vkey
            except NPSError as e:
                logger.warning(f"Failed to query clients from {edge_name}: {e}")
                continue

        logger.error(f"Could not find vkey for NPC client: {npc_config.name}")
        return None

    def get_server_addrs_for_npc(self, npc_config: NPCClientConfig) -> str:
        """Get server addresses string for NPC client.

        Builds a comma-separated list of server:port addresses based on
        the edges configured for this NPC client.

        Args:
            npc_config: NPC client configuration.

        Returns:
            Comma-separated server addresses (e.g., "host1:51235,host2:51235").
        """
        addrs = []
        # Determine port based on connection type
        port = 51235 if npc_config.conn_type == "tls" else 51234

        for edge_name in npc_config.edges:
            edge = self._edges.get(edge_name)
            if edge:
                # Extract hostname from api_url
                # api_url is like "https://nps-asia.example.com"
                # We need to get the hostname part
                api_url = edge.api_url
                if api_url.startswith("https://"):
                    hostname = api_url[8:]
                elif api_url.startswith("http://"):
                    hostname = api_url[7:]
                else:
                    hostname = api_url
                # Remove any path
                hostname = hostname.split("/")[0]
                addrs.append(f"{hostname}:{port}")
            else:
                logger.warning(f"Edge {edge_name} not found for NPC {npc_config.name}")

        return ",".join(addrs)

    def _parallel_fetch(
        self,
        fetch_fn: Callable[[NPSClient], T],
        operation_name: str,
        edge_names: list[str] | None = None,
        max_workers: int = 4,
    ) -> dict[str, tuple[T | None, str | None]]:
        """Fetch data from multiple edges in parallel.

        Args:
            fetch_fn: Function to call on each NPSClient.
            operation_name: Name of the operation for logging.
            edge_names: Edges to fetch. ``None`` means every configured edge;
                an empty list means no edges.
            max_workers: Maximum number of parallel workers.

        Returns:
            Dictionary mapping edge name to ``(result, error)`` in configured
            edge order. ``result`` is None and ``error`` is set when the fetch
            failed.
        """
        targets = list(self._clients.keys()) if edge_names is None else list(edge_names)
        outcomes: dict[str, tuple[T | None, str | None]] = {}

        def fetch_single(name: str) -> tuple[str, T | None, str | None]:
            """Fetch from a single edge, return (name, result, error)."""
            if name not in self._clients:
                return (name, None, f"Edge '{name}' not found")
            try:
                nps = self._clients[name]
                result = fetch_fn(nps)
                return (name, result, None)
            except NPSError as e:
                return (name, None, str(e))
            except Exception as e:
                return (name, None, f"Unexpected error: {e}")

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(fetch_single, name): name for name in targets}
            for future in as_completed(futures):
                name, result, error = future.result()
                if error:
                    op_logger.cluster_operation(operation_name, name, False, error)
                else:
                    # Log success with count if result is a list
                    if isinstance(result, list):
                        op_logger.cluster_operation(
                            operation_name, name, True, f"{len(result)} items"
                        )
                    else:
                        op_logger.cluster_operation(operation_name, name, True)
                outcomes[name] = (result, error)

        # Preserve configured edge order regardless of completion order.
        return {name: outcomes[name] for name in targets}

    def get_all_clients(
        self,
        edge_names: list[str] | None = None,
        max_workers: int = 4,
    ) -> EdgeResults[ClientInfo]:
        """Get clients from all or selected edges in parallel.

        Args:
            edge_names: Edges to fetch. ``None`` means every configured edge;
                an empty list means none.
            max_workers: Maximum number of parallel workers.

        Returns:
            Mapping of edge names to client lists, in configured edge order.
            Failed edges have empty lists and appear in ``errors``.
        """
        ctx = OperationContext("get_all_clients", "cluster")
        op_logger.operation_start(ctx)
        start_time = time.perf_counter()

        raw_results = self._parallel_fetch(
            client_mgmt.list_clients,
            "list_clients",
            edge_names=edge_names,
            max_workers=max_workers,
        )

        result: EdgeResults[ClientInfo] = EdgeResults()
        for name, (clients, error) in raw_results.items():
            result[name] = clients if clients is not None else []
            if error:
                result.errors[name] = error

        elapsed_ms = (time.perf_counter() - start_time) * 1000
        total_clients = sum(len(c) for c in result.values())
        failed_count = len(result.errors)
        op_logger.operation_success(
            ctx,
            result=f"{total_clients} clients total, {failed_count} edges failed",
            duration_ms=elapsed_ms,
        )
        return result

    def get_all_tunnels(
        self,
        max_workers: int = 4,
        edge_names: list[str] | None = None,
        tunnel_type: str = "",
    ) -> EdgeResults[TunnelInfo]:
        """Get tunnels from all or selected edges in parallel.

        Args:
            max_workers: Maximum number of parallel workers.
            edge_names: Edges to fetch. ``None`` means every configured edge;
                an empty list means none.
            tunnel_type: Filter by tunnel type. Empty means every type.

        Returns:
            Mapping of edge names to tunnel lists, in configured edge order.
            Failed edges have empty lists and appear in ``errors``.
        """
        ctx = OperationContext("get_all_tunnels", "cluster")
        op_logger.operation_start(ctx)
        start_time = time.perf_counter()

        fetch_tunnels = (
            partial(tunnel.list_tunnels, tunnel_type=tunnel_type)
            if tunnel_type
            else tunnel.list_tunnels
        )
        raw_results = self._parallel_fetch(
            fetch_tunnels,
            "list_tunnels",
            edge_names=edge_names,
            max_workers=max_workers,
        )

        result: EdgeResults[TunnelInfo] = EdgeResults()
        for name, (tunnels, error) in raw_results.items():
            result[name] = tunnels if tunnels is not None else []
            if error:
                result.errors[name] = error

        elapsed_ms = (time.perf_counter() - start_time) * 1000
        total_tunnels = sum(len(t) for t in result.values())
        failed_count = len(result.errors)
        op_logger.operation_success(
            ctx,
            result=f"{total_tunnels} tunnels total, {failed_count} edges failed",
            duration_ms=elapsed_ms,
        )
        return result

    def get_all_hosts(
        self,
        edge_names: list[str] | None = None,
        max_workers: int = 4,
    ) -> EdgeResults[HostInfo]:
        """Get hosts from all or selected edges in parallel.

        Args:
            edge_names: Edges to fetch. ``None`` means every configured edge;
                an empty list means none.
            max_workers: Maximum number of parallel workers.

        Returns:
            Mapping of edge names to host lists, in configured edge order.
            Failed edges have empty lists and appear in ``errors``.
        """
        ctx = OperationContext("get_all_hosts", "cluster")
        op_logger.operation_start(ctx)
        start_time = time.perf_counter()

        raw_results = self._parallel_fetch(
            host.list_hosts,
            "list_hosts",
            edge_names=edge_names,
            max_workers=max_workers,
        )

        result: EdgeResults[HostInfo] = EdgeResults()
        for name, (hosts, error) in raw_results.items():
            result[name] = hosts if hosts is not None else []
            if error:
                result.errors[name] = error

        elapsed_ms = (time.perf_counter() - start_time) * 1000
        total_hosts = sum(len(h) for h in result.values())
        failed_count = len(result.errors)
        op_logger.operation_success(
            ctx,
            result=f"{total_hosts} hosts total, {failed_count} edges failed",
            duration_ms=elapsed_ms,
        )
        return result

    def broadcast_client(
        self,
        remark: str,
        vkey: str = "",
        **kwargs: Any,
    ) -> dict[str, bool]:
        """Add a client to all edges.

        Args:
            remark: Client remark/name.
            vkey: Unique verification key (same for all edges).
            **kwargs: Additional client parameters.

        Returns:
            Dictionary mapping edge names to success status.
        """
        ctx = OperationContext(
            "broadcast_client", "cluster", details={"remark": remark}
        )
        op_logger.operation_start(ctx)
        start_time = time.perf_counter()

        results: dict[str, bool] = {}
        for name, nps in self._clients.items():
            try:
                success = client_mgmt.add_client(
                    nps, remark=remark, vkey=vkey, **kwargs
                )
                results[name] = success
                op_logger.cluster_operation(
                    "add_client", name, success, f"remark={remark}"
                )
            except NPSError as e:
                op_logger.cluster_operation("add_client", name, False, str(e))
                results[name] = False

        elapsed_ms = (time.perf_counter() - start_time) * 1000
        success_count = sum(1 for v in results.values() if v)
        op_logger.operation_success(
            ctx,
            result=f"{success_count}/{len(results)} edges",
            duration_ms=elapsed_ms,
        )
        return results

    def broadcast_host(
        self,
        client_remark: str,
        host_domain: str,
        target: str,
        **kwargs: Any,
    ) -> dict[str, bool]:
        """Add a host mapping to all edges.

        This method finds the client by remark on each edge and adds the host.

        Args:
            client_remark: Client remark to find.
            host_domain: Domain name.
            target: Target address.
            **kwargs: Additional host parameters.

        Returns:
            Dictionary mapping edge names to success status.
        """
        ctx = OperationContext(
            "broadcast_host",
            "cluster",
            details={"host": host_domain, "client": client_remark},
        )
        op_logger.operation_start(ctx)
        start_time = time.perf_counter()

        results: dict[str, bool] = {}
        for name, nps in self._clients.items():
            try:
                # Find client by remark
                clients = client_mgmt.list_clients(nps, search=client_remark)
                matching = [c for c in clients if c.get("Remark") == client_remark]
                if not matching:
                    logger.warning(f"Client '{client_remark}' not found on {name}")
                    op_logger.cluster_operation(
                        "add_host", name, False, f"client '{client_remark}' not found"
                    )
                    results[name] = False
                    continue

                client_id = matching[0]["Id"]
                success = host.add_host(
                    nps, client_id=client_id, host=host_domain, target=target, **kwargs
                )
                results[name] = success
                op_logger.cluster_operation(
                    "add_host", name, success, f"host={host_domain}"
                )
            except NPSError as e:
                op_logger.cluster_operation("add_host", name, False, str(e))
                results[name] = False

        elapsed_ms = (time.perf_counter() - start_time) * 1000
        success_count = sum(1 for v in results.values() if v)
        op_logger.operation_success(
            ctx,
            result=f"{success_count}/{len(results)} edges",
            duration_ms=elapsed_ms,
        )
        return results

    def broadcast_tunnel(
        self,
        client_remark: str,
        tunnel_type: str,
        port: int = 0,
        target: str = "",
        remark: str = "",
        **kwargs: Any,
    ) -> dict[str, bool]:
        """Add a tunnel to all edges.

        This method finds the client by remark on each edge and adds the tunnel.

        Args:
            client_remark: Client remark to find.
            tunnel_type: Tunnel type (e.g. "tcp", "udp", "socks5", "httpProxy").
            port: Server-side port.
            target: Target address (host:port).
            remark: Tunnel remark.
            **kwargs: Additional tunnel parameters.

        Returns:
            Dictionary mapping edge names to success status.
        """
        ctx = OperationContext(
            "broadcast_tunnel",
            "cluster",
            details={"type": tunnel_type, "client": client_remark},
        )
        op_logger.operation_start(ctx)
        start_time = time.perf_counter()

        results: dict[str, bool] = {}
        for name, nps in self._clients.items():
            try:
                clients = client_mgmt.list_clients(nps, search=client_remark)
                matching = [c for c in clients if c.get("Remark") == client_remark]
                if not matching:
                    logger.warning(f"Client '{client_remark}' not found on {name}")
                    op_logger.cluster_operation(
                        "add_tunnel",
                        name,
                        False,
                        f"client '{client_remark}' not found",
                    )
                    results[name] = False
                    continue

                client_id = matching[0]["Id"]
                success = tunnel.add_tunnel(
                    nps,
                    client_id=client_id,
                    tunnel_type=tunnel_type,
                    port=port,
                    target=target,
                    remark=remark,
                    **kwargs,
                )
                results[name] = success
                op_logger.cluster_operation(
                    "add_tunnel", name, success, f"type={tunnel_type} port={port}"
                )
            except NPSError as e:
                op_logger.cluster_operation("add_tunnel", name, False, str(e))
                results[name] = False

        elapsed_ms = (time.perf_counter() - start_time) * 1000
        success_count = sum(1 for v in results.values() if v)
        op_logger.operation_success(
            ctx,
            result=f"{success_count}/{len(results)} edges",
            duration_ms=elapsed_ms,
        )
        return results

    def _build_client_id_mapping(
        self,
        source_clients: list[ClientInfo],
        target_clients: list[ClientInfo],
    ) -> ClientIdMapping:
        """Build a mapping from source client IDs to target client IDs.

        Uses VerifyKey as the unique identifier to match clients across edges.

        Args:
            source_clients: List of clients from source edge.
            target_clients: List of clients from target edge.

        Returns:
            Dictionary mapping source client ID to target client ID.
        """
        # Build vkey -> target_id mapping
        vkey_to_target_id: dict[str, int] = {}
        for client in target_clients:
            vkey = client.get("VerifyKey", "")
            if vkey:
                vkey_to_target_id[vkey] = client.get("Id", 0)

        # Build source_id -> target_id mapping
        mapping: ClientIdMapping = {}
        for client in source_clients:
            source_id = client.get("Id", 0)
            vkey = client.get("VerifyKey", "")
            if vkey and vkey in vkey_to_target_id:
                mapping[source_id] = vkey_to_target_id[vkey]

        return mapping

    def sync_from(
        self,
        source_name: str,
        sync_clients: bool = True,
        sync_tunnels: bool = True,
        sync_hosts: bool = True,
        target_edges: list[str] | None = None,
        show_progress: bool = False,
        max_workers: int = 4,
        parallel: bool = False,
        quiet: bool = False,
        prune: bool = False,
    ) -> dict[str, dict[str, bool]]:
        """Sync configuration from one edge to all others.

        This method fetches source data and syncs to target edges.
        By default, syncs to edges sequentially for clearer output.
        Use parallel=True for faster but noisier parallel sync.

        Args:
            source_name: Source edge name.
            sync_clients: Whether to sync clients.
            sync_tunnels: Whether to sync tunnels.
            sync_hosts: Whether to sync hosts.
            target_edges: List of target edge names. If None, sync to all others.
            show_progress: Whether to show progress bar.
            max_workers: Maximum number of parallel workers for items.
            parallel: If True, sync to all edges in parallel (original behavior).
                      If False (default), sync to edges sequentially.
            quiet: If True, suppress progress output and only show summary.
            prune: Also delete resources on each target that are absent from the
                source. Source fetches are strict in this mode: if a selected
                resource type cannot be read, nothing is changed.

        Returns:
            Nested dictionary: {target_edge: {operation: success}}.
        """
        if source_name not in self._clients:
            raise ValueError(f"Source edge not found: {source_name}")

        sync_types = []
        if sync_clients:
            sync_types.append("clients")
        if sync_tunnels:
            sync_types.append("tunnels")
        if sync_hosts:
            sync_types.append("hosts")

        mode = "parallel" if parallel else "sequential"
        ctx = OperationContext(
            "sync_from",
            source_name,
            details={
                "types": ",".join(sync_types),
                "mode": mode,
                "workers": max_workers,
                "prune": prune,
            },
        )
        op_logger.operation_start(ctx)
        start_time = time.perf_counter()

        source = self._clients[source_name]

        # Determine target edges
        if target_edges is None:
            targets = [n for n in self._clients.keys() if n != source_name]
        else:
            targets = [
                n for n in target_edges if n != source_name and n in self._clients
            ]

        if not targets:
            console.print("[yellow]No target edges to sync to[/yellow]")
            return {}

        # Phase 1: Fetch source data
        if not quiet:
            console.print(
                f"\n[bold blue]Fetching source data from {source_name}...[/bold blue]"
            )

        # Pruning tunnels needs the source client rows to map source client
        # IDs to target IDs, even when clients themselves are not being synced.
        fetch_clients = sync_clients or (prune and sync_tunnels)
        source_clients, source_tunnels, source_hosts = self._fetch_source_data(
            source,
            fetch_clients,
            sync_tunnels,
            sync_hosts,
            source_name,
            strict=prune,
        )

        if not quiet:
            console.print(
                f"  Source: {len(source_clients)} clients, "
                f"{len(source_tunnels)} tunnels, {len(source_hosts)} hosts"
            )

        # Choose sync strategy
        if parallel:
            results = self._sync_from_parallel(
                source_name=source_name,
                targets=targets,
                source_clients=source_clients,
                source_tunnels=source_tunnels,
                source_hosts=source_hosts,
                sync_clients=sync_clients,
                sync_tunnels=sync_tunnels,
                sync_hosts=sync_hosts,
                show_progress=show_progress and not quiet,
                max_workers=max_workers,
                quiet=quiet,
                prune=prune,
            )
        else:
            results = self._sync_from_sequential(
                source_name=source_name,
                targets=targets,
                source_clients=source_clients,
                source_tunnels=source_tunnels,
                source_hosts=source_hosts,
                sync_clients=sync_clients,
                sync_tunnels=sync_tunnels,
                sync_hosts=sync_hosts,
                show_progress=show_progress and not quiet,
                max_workers=max_workers,
                quiet=quiet,
                prune=prune,
            )

        # Calculate and display summary
        elapsed_ms = (time.perf_counter() - start_time) * 1000
        self._print_sync_summary(results, elapsed_ms, quiet)

        op_logger.operation_success(
            ctx,
            result=self._get_summary_string(results),
            duration_ms=elapsed_ms,
        )

        return results

    def _fetch_source_data(
        self,
        source: NPSClient,
        sync_clients: bool,
        sync_tunnels: bool,
        sync_hosts: bool,
        source_name: str,
        *,
        strict: bool = False,
    ) -> tuple[list[ClientInfo], list[TunnelInfo], list[HostInfo]]:
        """Fetch source data in parallel.

        Args:
            source: Source NPSClient.
            sync_clients: Whether to fetch clients.
            sync_tunnels: Whether to fetch tunnels.
            sync_hosts: Whether to fetch hosts.
            source_name: Source edge name for logging.
            strict: Raise instead of returning partial data when a selected
                resource type cannot be fetched. Required before pruning, so a
                failed read can never be mistaken for an empty source.

        Returns:
            Tuple of (clients, tunnels, hosts).

        Raises:
            NPSError: If ``strict`` is set and any selected fetch failed.
        """
        source_clients: list[ClientInfo] = []
        source_tunnels: list[TunnelInfo] = []
        source_hosts: list[HostInfo] = []
        errors: list[str] = []

        def fetch_clients() -> list[ClientInfo]:
            return client_mgmt.list_clients(source) if sync_clients else []

        def fetch_tunnels() -> list[TunnelInfo]:
            return tunnel.list_tunnels(source) if sync_tunnels else []

        def fetch_hosts() -> list[HostInfo]:
            return host.list_hosts(source) if sync_hosts else []

        with ThreadPoolExecutor(max_workers=3) as executor:
            client_future = executor.submit(fetch_clients)
            tunnel_future = executor.submit(fetch_tunnels)
            host_future = executor.submit(fetch_hosts)

            try:
                source_clients = client_future.result()
            except Exception as e:
                logger.warning(f"Failed to fetch clients from {source_name}: {e}")
                errors.append(f"clients: {e}")

            try:
                source_tunnels = tunnel_future.result()
            except Exception as e:
                logger.warning(f"Failed to fetch tunnels from {source_name}: {e}")
                errors.append(f"tunnels: {e}")

            try:
                source_hosts = host_future.result()
            except Exception as e:
                logger.warning(f"Failed to fetch hosts from {source_name}: {e}")
                errors.append(f"hosts: {e}")

        if strict and errors:
            raise NPSError(
                f"Cannot prune from {source_name}: incomplete source data "
                f"({'; '.join(errors)})"
            )

        if strict:
            # A successful read whose rows have no identity is just as unsafe
            # as a failed read: the delete phase must never compare against an
            # identity set that silently lost rows.
            if sync_clients and any(not c.get("VerifyKey") for c in source_clients):
                raise NPSError(
                    f"Cannot prune from {source_name}: a source client has no VerifyKey"
                )
            if sync_tunnels and any(
                not (t.get("Client") or {}).get("VerifyKey") for t in source_tunnels
            ):
                raise NPSError(
                    f"Cannot prune from {source_name}: a source tunnel's "
                    "client has no VerifyKey"
                )
            if sync_hosts and any(not h.get("Host") for h in source_hosts):
                raise NPSError(
                    f"Cannot prune from {source_name}: a source host has no domain"
                )

        return source_clients, source_tunnels, source_hosts

    def _fetch_target_existing_data(
        self,
        target_name: str,
        sync_tunnels: bool,
        sync_hosts: bool,
    ) -> _TargetSnapshot:
        """Fetch existing data from a target edge.

        Args:
            target_name: Target edge name.
            sync_tunnels: Whether to fetch tunnels.
            sync_hosts: Whether to fetch hosts.

        Returns:
            Snapshot of the target's clients and the identity keys used by the
            add and prune phases.
        """
        target_nps = self._clients[target_name]
        clients_list: list[ClientInfo] | None = None
        tunnels: list[TunnelInfo] = []
        hosts: list[HostInfo] = []
        tunnels_ok = not sync_tunnels
        hosts_ok = not sync_hosts

        # Always fetch clients (needed for ID mapping)
        try:
            clients_list = client_mgmt.list_clients(target_nps)
        except NPSError as e:
            logger.warning(f"Failed to fetch clients from {target_name}: {e}")

        vkeys = {c.get("VerifyKey", "") for c in clients_list or []}

        if sync_tunnels:
            try:
                tunnels = tunnel.list_tunnels(target_nps)
                tunnels_ok = True
            except NPSError as e:
                logger.warning(f"Failed to fetch tunnels from {target_name}: {e}")

        if sync_hosts:
            try:
                hosts = host.list_hosts(target_nps)
                hosts_ok = True
            except NPSError as e:
                logger.warning(f"Failed to fetch hosts from {target_name}: {e}")

        tunnel_keys = {
            (
                t.get("Client", {}).get("Id", 0),
                tunnel.canonical_tunnel_mode(t),
                t.get("Port", 0),
            )
            for t in tunnels
        }
        host_keys = {(h.get("Host", ""), h.get("Location") or "/") for h in hosts}
        return _TargetSnapshot(
            clients=clients_list,
            vkeys=vkeys,
            tunnels=tunnels,
            tunnel_keys=tunnel_keys,
            hosts=hosts,
            host_keys=host_keys,
            tunnels_ok=tunnels_ok,
            hosts_ok=hosts_ok,
        )

    def _prune_target(
        self,
        target_name: str,
        snapshot: _TargetSnapshot,
        source_clients: list[ClientInfo],
        source_tunnels: list[TunnelInfo],
        source_hosts: list[HostInfo],
        sync_clients: bool,
        sync_tunnels: bool,
        sync_hosts: bool,
        rate_limiter: "RateLimiter | None" = None,
    ) -> dict[str, bool]:
        """Delete resources on a target that do not exist on the source.

        Tunnels and hosts are removed before clients so a client is not
        blocked by its descendants. Resources without a stable identity
        (a client without a verify key, a tunnel whose client cannot be
        matched, or a row without an ID) are kept.

        Returns:
            Operation name to success, using ``prune:<type>:<name>`` keys.
        """
        target_nps = self._clients[target_name]
        results: dict[str, bool] = {}

        def wait() -> None:
            if rate_limiter:
                rate_limiter.wait()

        id_mapping = self._build_client_id_mapping(
            source_clients, snapshot.clients or []
        )
        source_keys = {
            (
                id_mapping.get(t.get("Client", {}).get("Id", 0)),
                tunnel.canonical_tunnel_mode(t),
                t.get("Port", 0),
            )
            for t in source_tunnels
        }
        mapped_target_ids = set(id_mapping.values())
        target_vkeys = {
            c.get("Id", 0): c.get("VerifyKey", "") for c in snapshot.clients or []
        }
        # One anonymous source client is enough to make some target client
        # impossible to identify; no tunnel of an unmapped target client can
        # then be proven absent from the source.
        source_identifiable = all(c.get("VerifyKey") for c in source_clients)

        # Validate every identity before deleting anything: a partial prune is
        # worse than none, because the abort would leave the target half done.
        if sync_tunnels and source_tunnels and not id_mapping:
            raise NPSError(
                "Cannot prune tunnels: no source client could be mapped "
                "to a target client"
            )
        # An empty source read cannot be distinguished from a legacy API that
        # silently answered with no rows, so never turn it into "delete all".
        if sync_tunnels and snapshot.tunnels and not source_tunnels:
            raise NPSError(
                "Cannot prune tunnels: the source returned no tunnels while "
                "the target has some"
            )
        if sync_hosts and snapshot.hosts and not source_hosts:
            raise NPSError(
                "Cannot prune hosts: the source returned no hosts while the "
                "target has some"
            )
        if sync_hosts and any(not h.get("Host") for h in source_hosts):
            raise NPSError("Cannot prune hosts: a source host has no domain")
        # Clients have the largest blast radius (NPS removes their tunnels and
        # hosts with them), so an empty source read must not mean "delete all".
        if sync_clients and snapshot.clients and not source_clients:
            raise NPSError(
                "Cannot prune clients: the source returned no clients while "
                "the target has some"
            )
        if sync_clients and any(not c.get("VerifyKey") for c in source_clients):
            raise NPSError("Cannot prune clients: a source client has no VerifyKey")
        if sync_tunnels:
            source_client_ids = {c.get("Id") for c in source_clients if c.get("Id")}
            if any(
                not (item.get("Client") or {}).get("Id")
                or (item.get("Client") or {}).get("Id") not in source_client_ids
                for item in source_tunnels
            ):
                raise NPSError(
                    "Cannot prune tunnels: a source tunnel's client has no identity"
                )

        if sync_tunnels:
            for item in snapshot.tunnels:
                client = item.get("Client", {})
                key = (
                    client.get("Id", 0),
                    tunnel.canonical_tunnel_mode(item),
                    item.get("Port", 0),
                )
                if key in source_keys:
                    continue
                if key[0] not in mapped_target_ids and (
                    not target_vkeys.get(key[0]) or not source_identifiable
                ):
                    # The owning client is anonymous, or the source may hold it
                    # as an anonymous row: keep the tunnel rather than guess.
                    continue
                name = item.get("Remark") or f"port:{item.get('Port', 0)}"
                tunnel_id = item.get("Id")
                if not tunnel_id:
                    logger.warning(
                        f"Cannot prune tunnel {name} on {target_name}: missing ID"
                    )
                    results[f"prune:tunnel:{name}"] = False
                    continue
                wait()
                try:
                    ok = tunnel.del_tunnel(target_nps, tunnel_id)
                except NPSError as e:
                    logger.error(f"Failed to prune tunnel {name} on {target_name}: {e}")
                    ok = False
                results[f"prune:tunnel:{name}"] = ok

        if sync_hosts:
            source_host_keys = {
                (h.get("Host", ""), h.get("Location") or "/") for h in source_hosts
            }
            for item in snapshot.hosts:
                key = (item.get("Host", ""), item.get("Location") or "/")
                if key in source_host_keys:
                    continue
                name = item.get("Host", "")
                host_id = item.get("Id")
                if not host_id:
                    logger.warning(
                        f"Cannot prune host {name} on {target_name}: missing ID"
                    )
                    results[f"prune:host:{name}"] = False
                    continue
                wait()
                try:
                    ok = host.del_host(target_nps, host_id)
                except NPSError as e:
                    logger.error(f"Failed to prune host {name} on {target_name}: {e}")
                    ok = False
                results[f"prune:host:{name}"] = ok

        if sync_clients:
            source_vkeys = {
                c.get("VerifyKey", "") for c in source_clients if c.get("VerifyKey")
            }
            for item in snapshot.clients or []:
                vkey = item.get("VerifyKey", "")
                if not vkey or vkey in source_vkeys:
                    continue
                name = item.get("Remark") or f"id:{item.get('Id', 0)}"
                client_id = item.get("Id")
                if not client_id:
                    logger.warning(
                        f"Cannot prune client {name} on {target_name}: missing ID"
                    )
                    results[f"prune:client:{name}"] = False
                    continue
                wait()
                try:
                    ok = client_mgmt.del_client(target_nps, client_id)
                except NPSError as e:
                    logger.error(f"Failed to prune client {name} on {target_name}: {e}")
                    ok = False
                results[f"prune:client:{name}"] = ok

        return results

    def _sync_single_item(
        self,
        source_name: str,
        target_name: str,
        item_type: str,
        item_info: SyncItem,
        source_clients: list[ClientInfo],
        snapshot: _TargetSnapshot,
        rate_limiter: "RateLimiter | None" = None,
    ) -> tuple[str, str, str, bool]:
        """Sync a single item to a target edge.

        Returns:
            Tuple of (target_name, item_type, item_name, success).
        """
        # Apply rate limiting to reduce server pressure
        if rate_limiter:
            rate_limiter.wait()

        target_nps = self._clients[target_name]

        if item_type == "client":
            vkey = item_info.get("VerifyKey", "")
            remark = item_info.get("Remark", "")

            # Check if client already exists (by vkey)
            if vkey and vkey in snapshot.vkeys:
                logger.debug(f"Client {remark} already exists on {target_name}")
                return (target_name, item_type, remark, True)

            try:
                success = client_mgmt.add_client(target_nps, remark=remark, vkey=vkey)
                return (target_name, item_type, remark, success)
            except NPSError as e:
                logger.error(f"Failed to sync client {remark} to {target_name}: {e}")
                return (target_name, item_type, remark, False)

        elif item_type == "tunnel":
            if not snapshot.tunnels_ok:
                name = item_info.get("Remark") or f"port:{item_info.get('Port', 0)}"
                logger.warning(
                    f"Cannot sync tunnel {name} to {target_name}: "
                    "the target tunnel list is unavailable"
                )
                return (target_name, item_type, name, False)

            id_mapping = self._build_client_id_mapping(
                source_clients, snapshot.clients or []
            )

            source_client_id = item_info.get("Client", {}).get("Id", 0)
            target_client_id = id_mapping.get(source_client_id)
            tunnel_type = item_info.get("Mode", "tcp")
            port = item_info.get("Port", 0)
            target_addr = item_info.get("Target", {}).get("TargetStr", "")
            remark = item_info.get("Remark", "")
            item_name = remark or f"port:{port}"

            if not target_client_id:
                logger.warning(
                    f"Cannot sync tunnel {remark}: client not found on {target_name}"
                )
                return (target_name, item_type, item_name, False)

            # Check if tunnel already exists. Mode is compared canonically so
            # socks5/httpProxy rows match their mixProxy form on the target.
            tunnel_key = (
                target_client_id,
                tunnel.canonical_tunnel_mode(cast(TunnelInfo, item_info)),
                port,
            )
            if tunnel_key in snapshot.tunnel_keys:
                logger.debug(f"Tunnel {remark} already exists on {target_name}")
                return (target_name, item_type, item_name, True)

            try:
                success = tunnel.add_tunnel(
                    target_nps,
                    client_id=target_client_id,
                    tunnel_type=tunnel_type,
                    port=port,
                    target=target_addr,
                    remark=remark,
                )
                return (target_name, item_type, item_name, success)
            except NPSError as e:
                logger.error(f"Failed to sync tunnel {remark} to {target_name}: {e}")
                return (target_name, item_type, item_name, False)

        elif item_type == "host":
            if not snapshot.hosts_ok:
                name = item_info.get("Host", "")
                logger.warning(
                    f"Cannot sync host {name} to {target_name}: "
                    "the target host list is unavailable"
                )
                return (target_name, item_type, name, False)

            id_mapping = self._build_client_id_mapping(
                source_clients, snapshot.clients or []
            )

            source_client_id = item_info.get("Client", {}).get("Id", 0)
            target_client_id = id_mapping.get(source_client_id)
            host_domain = item_info.get("Host", "")
            target_addr = item_info.get("Target", {}).get("TargetStr", "")
            remark = item_info.get("Remark", "")
            location = item_info.get("Location", "")
            scheme = item_info.get("Scheme", "all")

            if not target_client_id:
                logger.warning(
                    f"Cannot sync host {host_domain}: client not found on {target_name}"
                )
                return (target_name, item_type, host_domain, False)

            # Check if host already exists (domain + location is the identity)
            if (host_domain, location or "/") in snapshot.host_keys:
                logger.debug(f"Host {host_domain} already exists on {target_name}")
                return (target_name, item_type, host_domain, True)

            try:
                success = host.add_host(
                    target_nps,
                    client_id=target_client_id,
                    host=host_domain,
                    target=target_addr,
                    remark=remark,
                    location=location,
                    scheme=scheme,
                )
                return (target_name, item_type, host_domain, success)
            except NPSError as e:
                logger.error(f"Failed to sync host {host_domain} to {target_name}: {e}")
                return (target_name, item_type, host_domain, False)

        return (target_name, item_type, "unknown", False)

    def _sync_from_sequential(
        self,
        source_name: str,
        targets: list[str],
        source_clients: list[ClientInfo],
        source_tunnels: list[TunnelInfo],
        source_hosts: list[HostInfo],
        sync_clients: bool,
        sync_tunnels: bool,
        sync_hosts: bool,
        show_progress: bool,
        max_workers: int,
        quiet: bool,
        prune: bool = False,
    ) -> dict[str, dict[str, bool]]:
        """Sync to edges one by one (sequential mode).

        This provides clearer output by processing one edge at a time.
        """
        results: dict[str, dict[str, bool]] = {}

        for i, target_name in enumerate(targets, 1):
            if not quiet:
                console.print(
                    f"\n[bold cyan][{i}/{len(targets)}] Syncing to {target_name}...[/bold cyan]"
                )

            edge_start = time.perf_counter()

            # Fetch existing data for this target
            snapshot = self._fetch_target_existing_data(
                target_name, sync_tunnels, sync_hosts
            )

            if snapshot.clients is None:
                if not quiet:
                    console.print(f"  [red]✗ Failed to connect to {target_name}[/red]")
                results[target_name] = {"_edge_failed": True}
                continue

            # Build task list for this edge
            tasks: list[tuple[str, SyncItem]] = []
            if sync_clients:
                for c in source_clients:
                    tasks.append(("client", c))
            if sync_tunnels:
                for t in source_tunnels:
                    tasks.append(("tunnel", t))
            if sync_hosts:
                for h in source_hosts:
                    tasks.append(("host", h))

            edge_results: dict[str, bool] = {}
            client_success = client_total = 0
            tunnel_success = tunnel_total = 0
            host_success = host_total = 0

            # Create rate limiter to prevent overwhelming the server
            # Use longer intervals for better reliability on unstable networks
            rate_limiter = RateLimiter(min_interval=0.5, jitter=0.2)

            # Sync items with progress bar
            if show_progress:
                with Progress(
                    SpinnerColumn(),
                    TextColumn("[progress.description]{task.description}"),
                    BarColumn(),
                    MofNCompleteColumn(),
                    TimeElapsedColumn(),
                    console=console,
                    transient=True,
                ) as progress:
                    task = progress.add_task("Syncing...", total=len(tasks))

                    with ThreadPoolExecutor(max_workers=max_workers) as executor:
                        futures = {
                            executor.submit(
                                self._sync_single_item,
                                source_name,
                                target_name,
                                item_type,
                                item_info,
                                source_clients,
                                snapshot,
                                rate_limiter,
                            ): (item_type, item_info)
                            for item_type, item_info in tasks
                        }

                        for future in as_completed(futures):
                            item_type, item_info = futures[future]
                            try:
                                _, i_type, i_name, success = future.result()
                                edge_results[f"{i_type}:{i_name}"] = success

                                if i_type == "client":
                                    client_total += 1
                                    if success:
                                        client_success += 1
                                elif i_type == "tunnel":
                                    tunnel_total += 1
                                    if success:
                                        tunnel_success += 1
                                elif i_type == "host":
                                    host_total += 1
                                    if success:
                                        host_success += 1
                            except Exception as e:
                                logger.error(f"Unexpected error: {e}")
                                edge_results[f"{item_type}:error"] = False

                            progress.update(task, advance=1)
            else:
                # No progress bar, just execute
                with ThreadPoolExecutor(max_workers=max_workers) as executor:
                    futures = {
                        executor.submit(
                            self._sync_single_item,
                            source_name,
                            target_name,
                            item_type,
                            item_info,
                            source_clients,
                            snapshot,
                            rate_limiter,
                        ): (item_type, item_info)
                        for item_type, item_info in tasks
                    }

                    for future in as_completed(futures):
                        item_type, item_info = futures[future]
                        try:
                            _, i_type, i_name, success = future.result()
                            edge_results[f"{i_type}:{i_name}"] = success

                            if i_type == "client":
                                client_total += 1
                                if success:
                                    client_success += 1
                            elif i_type == "tunnel":
                                tunnel_total += 1
                                if success:
                                    tunnel_success += 1
                            elif i_type == "host":
                                host_total += 1
                                if success:
                                    host_success += 1
                        except Exception as e:
                            logger.error(f"Unexpected error: {e}")
                            edge_results[f"{item_type}:error"] = False

            if prune:
                pruned = self._prune_target(
                    target_name,
                    snapshot,
                    source_clients,
                    source_tunnels,
                    source_hosts,
                    sync_clients,
                    sync_tunnels,
                    sync_hosts,
                    rate_limiter,
                )
                edge_results.update(pruned)
                if not quiet and pruned:
                    ok = sum(1 for value in pruned.values() if value)
                    console.print(f"  [dim]Pruned: {ok}/{len(pruned)} succeeded[/dim]")

            results[target_name] = edge_results
            edge_elapsed = time.perf_counter() - edge_start

            # Print edge summary
            if not quiet:
                self._print_edge_summary(
                    target_name,
                    client_success,
                    client_total,
                    tunnel_success,
                    tunnel_total,
                    host_success,
                    host_total,
                    edge_elapsed,
                )

        return results

    def _sync_from_parallel(
        self,
        source_name: str,
        targets: list[str],
        source_clients: list[ClientInfo],
        source_tunnels: list[TunnelInfo],
        source_hosts: list[HostInfo],
        sync_clients: bool,
        sync_tunnels: bool,
        sync_hosts: bool,
        show_progress: bool,
        max_workers: int,
        quiet: bool,
        prune: bool = False,
    ) -> dict[str, dict[str, bool]]:
        """Sync to all edges in parallel (original behavior).

        This is faster but produces interleaved output.
        """
        results: dict[str, dict[str, bool]] = {}
        for target_name in targets:
            results[target_name] = {}

        if not quiet:
            console.print(
                f"\n[bold blue]Fetching existing data from {len(targets)} target edges...[/bold blue]"
            )

        # Fetch existing data from all targets in parallel
        target_data: dict[str, _TargetSnapshot] = {}
        failed_targets: set[str] = set()

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(
                    self._fetch_target_existing_data,
                    name,
                    sync_tunnels,
                    sync_hosts,
                ): name
                for name in targets
            }
            for future in as_completed(futures):
                target_name = futures[future]
                try:
                    data = future.result()
                    target_data[target_name] = data
                    if data.clients is None:
                        failed_targets.add(target_name)
                except Exception as e:
                    logger.error(f"Failed to fetch data from {target_name}: {e}")
                    failed_targets.add(target_name)
                    target_data[target_name] = _TargetSnapshot(
                        None, set(), [], set(), [], set()
                    )

        active_targets = [t for t in targets if t not in failed_targets]
        if failed_targets and not quiet:
            console.print(
                f"[yellow]Skipping {len(failed_targets)} failed edges: "
                f"{', '.join(failed_targets)}[/yellow]"
            )
            for target_name in failed_targets:
                results[target_name]["_edge_failed"] = True

        # Build all tasks
        tasks: list[tuple[str, str, SyncItem]] = []
        if sync_clients:
            for target_name in active_targets:
                for c in source_clients:
                    tasks.append((target_name, "client", c))
        if sync_tunnels:
            for target_name in active_targets:
                for t in source_tunnels:
                    tasks.append((target_name, "tunnel", t))
        if sync_hosts:
            for target_name in active_targets:
                for h in source_hosts:
                    tasks.append((target_name, "host", h))

        if not quiet:
            console.print(
                f"\n[bold blue]Syncing {len(tasks)} items to "
                f"{len(active_targets)} target edges...[/bold blue]"
            )

        # Create rate limiter to prevent overwhelming the server
        # Use longer intervals for better reliability on unstable networks
        rate_limiter = RateLimiter(min_interval=0.5, jitter=0.2)

        # Execute all tasks in parallel
        if show_progress:
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                MofNCompleteColumn(),
                TaskProgressColumn(),
                TimeElapsedColumn(),
                console=console,
            ) as progress:
                task = progress.add_task("Syncing...", total=len(tasks))

                with ThreadPoolExecutor(max_workers=max_workers) as executor:
                    futures = {
                        executor.submit(
                            self._sync_single_item,
                            source_name,
                            target_name,
                            item_type,
                            item_info,
                            source_clients,
                            target_data[target_name],
                            rate_limiter,
                        ): (target_name, item_type, item_info)
                        for target_name, item_type, item_info in tasks
                    }

                    for future in as_completed(futures):
                        target_name, item_type, item_info = futures[future]
                        try:
                            t_name, i_type, i_name, success = future.result()
                            results[t_name][f"{i_type}:{i_name}"] = success
                        except Exception as e:
                            logger.error(f"Unexpected error: {e}")
                            if item_type == "client":
                                name = item_info.get("Remark", "")
                            elif item_type == "tunnel":
                                name = (
                                    item_info.get("Remark", "")
                                    or f"port:{item_info.get('Port', 0)}"
                                )
                            else:
                                name = item_info.get("Host", "")
                            results[target_name][f"{item_type}:{name}"] = False

                        progress.update(task, advance=1)
        else:
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = {
                    executor.submit(
                        self._sync_single_item,
                        source_name,
                        target_name,
                        item_type,
                        item_info,
                        source_clients,
                        target_data[target_name],
                        rate_limiter,
                    ): (target_name, item_type, item_info)
                    for target_name, item_type, item_info in tasks
                }

                for future in as_completed(futures):
                    target_name, item_type, item_info = futures[future]
                    try:
                        t_name, i_type, i_name, success = future.result()
                        results[t_name][f"{i_type}:{i_name}"] = success
                    except Exception as e:
                        logger.error(f"Unexpected error: {e}")
                        if item_type == "client":
                            name = item_info.get("Remark", "")
                        elif item_type == "tunnel":
                            name = (
                                item_info.get("Remark", "")
                                or f"port:{item_info.get('Port', 0)}"
                            )
                        else:
                            name = item_info.get("Host", "")
                        results[target_name][f"{item_type}:{name}"] = False

        if prune:
            for target_name in active_targets:
                pruned = self._prune_target(
                    target_name,
                    target_data[target_name],
                    source_clients,
                    source_tunnels,
                    source_hosts,
                    sync_clients,
                    sync_tunnels,
                    sync_hosts,
                    rate_limiter,
                )
                results[target_name].update(pruned)
                if not quiet and pruned:
                    ok = sum(1 for value in pruned.values() if value)
                    console.print(
                        f"[dim]Pruned {target_name}: {ok}/{len(pruned)} succeeded[/dim]"
                    )

        return results

    def _print_edge_summary(
        self,
        target_name: str,
        client_success: int,
        client_total: int,
        tunnel_success: int,
        tunnel_total: int,
        host_success: int,
        host_total: int,
        elapsed: float,
    ) -> None:
        """Print summary for a single edge sync."""
        if client_total > 0:
            status = (
                "[green]✓[/green]" if client_success == client_total else "[red]✗[/red]"
            )
            failed_msg = (
                f" [dim]({client_total - client_success} failed)[/dim]"
                if client_success < client_total
                else ""
            )
            console.print(
                f"  Clients: {client_success}/{client_total} {status}{failed_msg}"
            )

        if tunnel_total > 0:
            status = (
                "[green]✓[/green]" if tunnel_success == tunnel_total else "[red]✗[/red]"
            )
            failed_msg = (
                f" [dim]({tunnel_total - tunnel_success} failed)[/dim]"
                if tunnel_success < tunnel_total
                else ""
            )
            console.print(
                f"  Tunnels: {tunnel_success}/{tunnel_total} {status}{failed_msg}"
            )

        if host_total > 0:
            status = (
                "[green]✓[/green]" if host_success == host_total else "[red]✗[/red]"
            )
            failed_msg = (
                f" [dim]({host_total - host_success} failed)[/dim]"
                if host_success < host_total
                else ""
            )
            console.print(f"  Hosts: {host_success}/{host_total} {status}{failed_msg}")

        console.print(f"  [dim]Completed in {elapsed:.1f}s[/dim]")

    def _print_sync_summary(
        self,
        results: dict[str, dict[str, bool]],
        elapsed_ms: float,
        quiet: bool,
    ) -> None:
        """Print final sync summary."""
        if not results:
            return

        console.print("\n[bold]Summary:[/bold]")

        total_ops = 0
        total_success = 0

        for target_name, ops in results.items():
            success = sum(1 for k, v in ops.items() if v and k != "_edge_failed")
            total = sum(1 for k in ops.keys() if k != "_edge_failed")
            total_ops += total
            total_success += success

            if "_edge_failed" in ops:
                console.print(f"  {target_name}: [red]connection failed[/red]")
            elif success == total:
                console.print(f"  {target_name}: {success}/{total} [green]✓[/green]")
            else:
                console.print(f"  {target_name}: {success}/{total} [red]✗[/red]")

        if total_ops > 0:
            pct = (total_success / total_ops) * 100
            console.print(
                f"\n  [bold]Total: {total_success}/{total_ops} ({pct:.1f}%) | "
                f"{elapsed_ms / 1000:.1f}s[/bold]"
            )

    def _get_summary_string(self, results: dict[str, dict[str, bool]]) -> str:
        """Get summary string for logging."""
        total_ops = sum(
            sum(1 for k in ops.keys() if k != "_edge_failed")
            for ops in results.values()
        )
        success_ops = sum(
            sum(1 for k, v in ops.items() if v and k != "_edge_failed")
            for ops in results.values()
        )
        failed_edges = sum(1 for ops in results.values() if "_edge_failed" in ops)
        return f"{success_ops}/{total_ops} operations succeeded, {failed_edges} edges failed"
