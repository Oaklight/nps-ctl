"""NPS cluster management for multiple NPS servers.

This module provides NPSCluster for managing multiple NPS edge nodes,
including broadcasting operations and syncing configurations.
"""

import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import tomllib

from . import client_mgmt, host, tunnel
from .base import NPSClient
from .exceptions import NPSError
from .types import ClientInfo, EdgeConfig, HostInfo, TunnelInfo

logger = logging.getLogger(__name__)


@dataclass
class NPSCluster:
    """Manager for multiple NPS servers.

    Args:
        config_path: Path to the edges.toml configuration file.

    Example:
        >>> cluster = NPSCluster("config/edges.toml")
        >>> for name, clients in cluster.get_all_clients().items():
        ...     print(f"{name}: {len(clients)} clients")
    """

    config_path: str | Path
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

    def sync_from(
        self,
        source_name: str,
        sync_clients: bool = True,
        sync_tunnels: bool = True,
        sync_hosts: bool = True,
    ) -> dict[str, dict[str, bool]]:
        """Sync configuration from one edge to all others.

        Args:
            source_name: Source edge name.
            sync_clients: Whether to sync clients.
            sync_tunnels: Whether to sync tunnels.
            sync_hosts: Whether to sync hosts.

        Returns:
            Nested dictionary: {target_edge: {operation: success}}.
        """
        if source_name not in self._clients:
            raise ValueError(f"Source edge not found: {source_name}")

        source = self._clients[source_name]
        results: dict[str, dict[str, bool]] = {}

        # Get source data
        source_clients = client_mgmt.list_clients(source) if sync_clients else []
        # Note: Tunnel and host sync requires client ID mapping
        # which is more complex and should be implemented based on specific needs
        _ = sync_tunnels, sync_hosts  # Mark as intentionally unused for now

        for target_name, target_nps in self._clients.items():
            if target_name == source_name:
                continue

            results[target_name] = {}

            # Sync clients
            if sync_clients:
                for client_info in source_clients:
                    vkey = client_info.get("VerifyKey", "")
                    remark = client_info.get("Remark", "")
                    try:
                        success = client_mgmt.add_client(
                            target_nps, remark=remark, vkey=vkey
                        )
                        results[target_name][f"client:{remark}"] = success
                    except NPSError as e:
                        msg = f"Failed to sync client {remark} to {target_name}: {e}"
                        logger.error(msg)
                        print(msg, file=sys.stderr)
                        results[target_name][f"client:{remark}"] = False

        return results
