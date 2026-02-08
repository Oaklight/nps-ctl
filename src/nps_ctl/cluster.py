"""NPS cluster management for multiple NPS servers.

This module provides NPSCluster for managing multiple NPS edge nodes,
including broadcasting operations and syncing configurations.
"""

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import tomllib
from tqdm import tqdm

from . import client_mgmt, host, tunnel
from .base import NPSClient
from .exceptions import NPSError
from .types import ClientInfo, EdgeConfig, HostInfo, TunnelInfo, ClientIdMapping

logger = logging.getLogger(__name__)


@dataclass
class NPSCluster:
    """Manager for multiple NPS servers.

    Args:
        config_path: Path to the edges.toml configuration file.
        proxy: HTTP/HTTPS proxy URL for all API requests.

    Example:
        >>> cluster = NPSCluster("config/edges.toml")
        >>> for name, clients in cluster.get_all_clients().items():
        ...     print(f"{name}: {len(clients)} clients")
    """

    config_path: str | Path
    proxy: str | None = None
    _edges: dict[str, EdgeConfig] = field(default_factory=dict, init=False)
    _clients: dict[str, NPSClient] = field(default_factory=dict, init=False)

    def __post_init__(self) -> None:
        """Load configuration and initialize clients."""
        self._load_config()

    def _load_config(self) -> None:
        """Load edge configuration from TOML file."""
        path = Path(self.config_path)
        if not path.exists():
            raise FileNotFoundError(f"Config file not found: {path}")

        with open(path, "rb") as f:
            config = tomllib.load(f)

        edges = config.get("edges", [])
        for edge in edges:
            edge_config = EdgeConfig(
                name=edge["name"],
                api_url=edge["api_url"],
                auth_key=edge["auth_key"],
                region=edge.get("region", ""),
                ssh_host=edge.get("ssh_host", ""),
            )
            self._edges[edge_config.name] = edge_config
            self._clients[edge_config.name] = NPSClient(
                base_url=edge_config.api_url,
                auth_key=edge_config.auth_key,
                proxy=self.proxy,
            )

    @property
    def edge_names(self) -> list[str]:
        """Get list of all edge names."""
        return list(self._edges.keys())

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

    def get_all_clients(self) -> dict[str, list[ClientInfo]]:
        """Get clients from all edges.

        Returns:
            Dictionary mapping edge names to their client lists.
        """
        result: dict[str, list[ClientInfo]] = {}
        for name, nps in self._clients.items():
            try:
                result[name] = client_mgmt.list_clients(nps)
            except NPSError as e:
                logger.error(f"Failed to get clients from {name}: {e}")
                result[name] = []
        return result

    def get_all_tunnels(self) -> dict[str, list[TunnelInfo]]:
        """Get tunnels from all edges.

        Returns:
            Dictionary mapping edge names to their tunnel lists.
        """
        result: dict[str, list[TunnelInfo]] = {}
        for name, nps in self._clients.items():
            try:
                result[name] = tunnel.list_tunnels(nps)
            except NPSError as e:
                logger.error(f"Failed to get tunnels from {name}: {e}")
                result[name] = []
        return result

    def get_all_hosts(self) -> dict[str, list[HostInfo]]:
        """Get hosts from all edges.

        Returns:
            Dictionary mapping edge names to their host lists.
        """
        result: dict[str, list[HostInfo]] = {}
        for name, nps in self._clients.items():
            try:
                result[name] = host.list_hosts(nps)
            except NPSError as e:
                logger.error(f"Failed to get hosts from {name}: {e}")
                result[name] = []
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
        results: dict[str, bool] = {}
        for name, nps in self._clients.items():
            try:
                results[name] = client_mgmt.add_client(
                    nps, remark=remark, vkey=vkey, **kwargs
                )
            except NPSError as e:
                logger.error(f"Failed to add client to {name}: {e}")
                results[name] = False
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
        results: dict[str, bool] = {}
        for name, nps in self._clients.items():
            try:
                # Find client by remark
                clients = client_mgmt.list_clients(nps, search=client_remark)
                matching = [c for c in clients if c.get("Remark") == client_remark]
                if not matching:
                    logger.warning(f"Client '{client_remark}' not found on {name}")
                    results[name] = False
                    continue

                client_id = matching[0]["Id"]
                results[name] = host.add_host(
                    nps, client_id=client_id, host=host_domain, target=target, **kwargs
                )
            except NPSError as e:
                logger.error(f"Failed to add host to {name}: {e}")
                results[name] = False
        return results

    def _build_client_id_mapping(
        self,
        source_clients: list[dict[str, Any]],
        target_clients: list[dict[str, Any]],
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
    ) -> dict[str, dict[str, bool]]:
        """Sync configuration from one edge to all others.

        Args:
            source_name: Source edge name.
            sync_clients: Whether to sync clients.
            sync_tunnels: Whether to sync tunnels.
            sync_hosts: Whether to sync hosts.
            target_edges: List of target edge names. If None, sync to all others.
            show_progress: Whether to show progress bar.
            max_workers: Maximum number of parallel workers.

        Returns:
            Nested dictionary: {target_edge: {operation: success}}.
        """
        if source_name not in self._clients:
            raise ValueError(f"Source edge not found: {source_name}")

        source = self._clients[source_name]
        results: dict[str, dict[str, bool]] = {}

        # Get source data
        source_clients = client_mgmt.list_clients(source) if sync_clients else []
        source_tunnels = tunnel.list_tunnels(source) if sync_tunnels else []
        source_hosts = host.list_hosts(source) if sync_hosts else []

        # Determine target edges
        if target_edges is None:
            targets = [n for n in self._clients.keys() if n != source_name]
        else:
            targets = [
                n for n in target_edges if n != source_name and n in self._clients
            ]

        # Initialize results dict
        for target_name in targets:
            results[target_name] = {}

        # Get existing data on target edges
        target_existing_clients: dict[str, set[str]] = {}
        target_existing_tunnels: dict[str, set[tuple[int, str, int]]] = {}
        target_existing_hosts: dict[str, set[str]] = {}
        target_clients_list: dict[str, list[dict[str, Any]]] = {}

        for target_name in targets:
            try:
                existing = client_mgmt.list_clients(self._clients[target_name])
                target_existing_clients[target_name] = {
                    c.get("VerifyKey", "") for c in existing
                }
                target_clients_list[target_name] = existing
            except NPSError:
                target_existing_clients[target_name] = set()
                target_clients_list[target_name] = []

            if sync_tunnels:
                try:
                    existing_tunnels = tunnel.list_tunnels(self._clients[target_name])
                    # Use (client_id, type, port) as unique key for tunnels
                    target_existing_tunnels[target_name] = {
                        (
                            t.get("Client", {}).get("Id", 0),
                            t.get("Mode", ""),
                            t.get("Port", 0),
                        )
                        for t in existing_tunnels
                    }
                except NPSError:
                    target_existing_tunnels[target_name] = set()

            if sync_hosts:
                try:
                    existing_hosts = host.list_hosts(self._clients[target_name])
                    # Use host domain as unique key
                    target_existing_hosts[target_name] = {
                        h.get("Host", "") for h in existing_hosts
                    }
                except NPSError:
                    target_existing_hosts[target_name] = set()

        # Build task list
        tasks: list[tuple[str, str, dict[str, Any]]] = []  # (target, type, data)

        if sync_clients:
            for target_name in targets:
                for client_info in source_clients:
                    tasks.append((target_name, "client", client_info))

        if sync_tunnels:
            for target_name in targets:
                for tunnel_info in source_tunnels:
                    tasks.append((target_name, "tunnel", tunnel_info))

        if sync_hosts:
            for target_name in targets:
                for host_info in source_hosts:
                    tasks.append((target_name, "host", host_info))

        def sync_single_item(
            target_name: str, item_type: str, item_info: dict[str, Any]
        ) -> tuple[str, str, str, bool]:
            """Sync a single item to a target edge.

            Returns:
                Tuple of (target_name, item_type, item_name, success).
            """
            target_nps = self._clients[target_name]

            if item_type == "client":
                vkey = item_info.get("VerifyKey", "")
                remark = item_info.get("Remark", "")

                # Check if client already exists (by vkey)
                if vkey and vkey in target_existing_clients.get(target_name, set()):
                    logger.debug(f"Client {remark} already exists on {target_name}")
                    return (target_name, item_type, remark, True)

                try:
                    success = client_mgmt.add_client(
                        target_nps, remark=remark, vkey=vkey
                    )
                    return (target_name, item_type, remark, success)
                except NPSError as e:
                    logger.error(
                        f"Failed to sync client {remark} to {target_name}: {e}"
                    )
                    return (target_name, item_type, remark, False)

            elif item_type == "tunnel":
                # Build client ID mapping for this target
                id_mapping = self._build_client_id_mapping(
                    source_clients, target_clients_list.get(target_name, [])
                )

                source_client_id = item_info.get("Client", {}).get("Id", 0)
                target_client_id = id_mapping.get(source_client_id)
                tunnel_type = item_info.get("Mode", "tcp")
                port = item_info.get("Port", 0)
                target_addr = item_info.get("Target", {}).get("TargetStr", "")
                remark = item_info.get("Remark", "")

                if not target_client_id:
                    logger.warning(
                        f"Cannot sync tunnel {remark}: client not found on {target_name}"
                    )
                    return (target_name, item_type, remark or f"port:{port}", False)

                # Check if tunnel already exists
                tunnel_key = (target_client_id, tunnel_type, port)
                if tunnel_key in target_existing_tunnels.get(target_name, set()):
                    logger.debug(f"Tunnel {remark} already exists on {target_name}")
                    return (target_name, item_type, remark or f"port:{port}", True)

                try:
                    success = tunnel.add_tunnel(
                        target_nps,
                        client_id=target_client_id,
                        tunnel_type=tunnel_type,
                        port=port,
                        target=target_addr,
                        remark=remark,
                    )
                    return (target_name, item_type, remark or f"port:{port}", success)
                except NPSError as e:
                    logger.error(
                        f"Failed to sync tunnel {remark} to {target_name}: {e}"
                    )
                    return (target_name, item_type, remark or f"port:{port}", False)

            elif item_type == "host":
                # Build client ID mapping for this target
                id_mapping = self._build_client_id_mapping(
                    source_clients, target_clients_list.get(target_name, [])
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

                # Check if host already exists
                if host_domain in target_existing_hosts.get(target_name, set()):
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
                    logger.error(
                        f"Failed to sync host {host_domain} to {target_name}: {e}"
                    )
                    return (target_name, item_type, host_domain, False)

            return (target_name, item_type, "unknown", False)

        # Execute tasks in parallel with progress bar
        with tqdm(total=len(tasks), desc="Syncing", disable=not show_progress) as pbar:
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = {
                    executor.submit(
                        sync_single_item, target_name, item_type, item_info
                    ): (
                        target_name,
                        item_type,
                        item_info,
                    )
                    for target_name, item_type, item_info in tasks
                }
                for future in as_completed(futures):
                    target_name, item_type, item_info = futures[future]
                    # Get display name for progress bar
                    if item_type == "client":
                        display_name = item_info.get("Remark", "")
                    elif item_type == "tunnel":
                        display_name = (
                            item_info.get("Remark", "")
                            or f"port:{item_info.get('Port', 0)}"
                        )
                    else:
                        display_name = item_info.get("Host", "")
                    pbar.set_postfix_str(f"{target_name}:{display_name}")

                    try:
                        t_name, i_type, i_name, success = future.result()
                        results[t_name][f"{i_type}:{i_name}"] = success
                    except Exception as e:
                        logger.error(f"Unexpected error syncing {item_type}: {e}")
                        results[target_name][f"{item_type}:{display_name}"] = False
                    pbar.update(1)

        return results
