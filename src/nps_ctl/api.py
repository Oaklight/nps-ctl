"""NPS API client for managing NPS servers.

This module provides NPSClient for single server management and
NPSCluster for managing multiple NPS servers.
"""

import hashlib
import json
import logging
import ssl
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TypedDict

import tomllib

logger = logging.getLogger(__name__)


class NPSError(Exception):
    """Base exception for NPS API errors."""

    pass


class NPSAuthError(NPSError):
    """Authentication error."""

    pass


class NPSAPIError(NPSError):
    """API request error."""

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


class ClientInfo(TypedDict, total=False):
    """Client information from NPS API."""

    Id: int
    VerifyKey: str
    Addr: str
    Remark: str
    Status: bool
    IsConnect: bool
    RateLimit: int
    Flow: dict[str, Any]
    MaxConn: int
    NowConn: int
    WebUserName: str
    WebPassword: str
    ConfigConnAllow: bool
    Cnf: dict[str, Any]


class TunnelInfo(TypedDict, total=False):
    """Tunnel information from NPS API."""

    Id: int
    Port: int
    ServerIp: str
    Mode: str
    Status: bool
    RunStatus: bool
    Client: ClientInfo
    Ports: str
    Flow: dict[str, Any]
    Password: str
    Remark: str
    TargetAddr: str
    NoStore: bool
    LocalPath: str
    StripPre: str
    Target: dict[str, Any]


class HostInfo(TypedDict, total=False):
    """Host (domain) information from NPS API."""

    Id: int
    Host: str
    HeaderChange: str
    HostChange: str
    Location: str
    Remark: str
    Scheme: str
    CertFilePath: str
    KeyFilePath: str
    NoStore: bool
    IsClose: bool
    Flow: dict[str, Any]
    Client: ClientInfo
    Target: dict[str, Any]
    AutoHttps: bool


@dataclass
class EdgeConfig:
    """Configuration for a single NPS edge node."""

    name: str
    api_url: str
    auth_key: str
    region: str = ""
    ssh_host: str = ""


@dataclass
class NPSClient:
    """API client for a single NPS server.

    Args:
        base_url: The base URL of the NPS server (e.g., "https://nps.example.com").
        auth_key: The authentication key configured in nps.conf.
        timeout: Request timeout in seconds.
        verify_ssl: Whether to verify SSL certificates.

    Example:
        >>> client = NPSClient("https://nps.example.com", "your_auth_key")
        >>> clients = client.list_clients()
        >>> for c in clients:
        ...     print(f"{c['Id']}: {c['Remark']}")
    """

    base_url: str
    auth_key: str
    timeout: int = 30
    verify_ssl: bool = True
    _ssl_context: ssl.SSLContext | None = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        """Initialize SSL context."""
        self.base_url = self.base_url.rstrip("/")
        if not self.verify_ssl:
            self._ssl_context = ssl.create_default_context()
            self._ssl_context.check_hostname = False
            self._ssl_context.verify_mode = ssl.CERT_NONE

    def _get_server_time(self) -> int:
        """Get the server timestamp for authentication.

        Returns:
            Server timestamp as integer.

        Raises:
            NPSAuthError: If failed to get server time.
        """
        url = f"{self.base_url}/auth/gettime"
        try:
            req = urllib.request.Request(url)
            with urllib.request.urlopen(
                req, timeout=self.timeout, context=self._ssl_context
            ) as response:
                data = json.loads(response.read().decode("utf-8"))
                return int(data.get("time", 0))
        except urllib.error.URLError as e:
            raise NPSAuthError(f"Failed to get server time: {e}") from e
        except (json.JSONDecodeError, ValueError) as e:
            raise NPSAuthError(f"Invalid server time response: {e}") from e

    def _generate_auth_key(self, timestamp: int) -> str:
        """Generate authentication key using MD5.

        Args:
            timestamp: Server timestamp.

        Returns:
            MD5 hash of auth_key + timestamp.
        """
        raw = f"{self.auth_key}{timestamp}"
        return hashlib.md5(raw.encode("utf-8")).hexdigest()

    def _request(
        self,
        endpoint: str,
        method: str = "GET",
        data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Make an authenticated API request.

        Args:
            endpoint: API endpoint (e.g., "/client/list").
            method: HTTP method.
            data: Request data for POST requests.

        Returns:
            JSON response as dictionary.

        Raises:
            NPSAPIError: If the request fails.
        """
        timestamp = self._get_server_time()
        auth_key = self._generate_auth_key(timestamp)

        # Auth params must be included in POST body, not URL query string
        auth_params = {"auth_key": auth_key, "timestamp": str(timestamp)}

        try:
            if method == "POST":
                # For POST requests, include auth params in the body
                post_params = {**auth_params}
                if data:
                    post_params.update({k: str(v) for k, v in data.items()})
                post_data = urllib.parse.urlencode(post_params).encode("utf-8")
                url = f"{self.base_url}{endpoint}"
                req = urllib.request.Request(url, data=post_data, method="POST")
                req.add_header("Content-Type", "application/x-www-form-urlencoded")
            else:
                # For GET requests, include auth params in URL
                params = {**auth_params}
                if data:
                    params.update({k: str(v) for k, v in data.items()})
                url = f"{self.base_url}{endpoint}?{urllib.parse.urlencode(params)}"
                req = urllib.request.Request(url, method=method)

            with urllib.request.urlopen(
                req, timeout=self.timeout, context=self._ssl_context
            ) as response:
                response_data = response.read().decode("utf-8")
                result = json.loads(response_data)
                return result

        except urllib.error.HTTPError as e:
            raise NPSAPIError(
                f"HTTP error: {e.code} {e.reason}", status_code=e.code
            ) from e
        except urllib.error.URLError as e:
            raise NPSAPIError(f"URL error: {e.reason}") from e
        except json.JSONDecodeError as e:
            raise NPSAPIError(f"Invalid JSON response: {e}") from e

    # ==================== Client Management ====================

    def list_clients(
        self,
        search: str = "",
        order: str = "asc",
        offset: int = 0,
        limit: int = 100,
    ) -> list[ClientInfo]:
        """List all clients.

        Args:
            search: Search keyword for filtering.
            order: Sort order ("asc" or "desc").
            offset: Pagination offset.
            limit: Maximum number of results.

        Returns:
            List of client information dictionaries.
        """
        data = {
            "search": search,
            "order": order,
            "offset": offset,
            "limit": limit,
        }
        result = self._request("/client/list", method="POST", data=data)
        return result.get("rows", [])

    def get_client(self, client_id: int) -> ClientInfo | None:
        """Get a single client by ID.

        Args:
            client_id: The client ID.

        Returns:
            Client information or None if not found.
        """
        result = self._request("/client/getclient", data={"id": client_id})
        if result.get("status") == 1:
            return result.get("data")
        return None

    def add_client(
        self,
        remark: str,
        vkey: str = "",
        basic_username: str = "",
        basic_password: str = "",
        rate_limit: int = 0,
        max_conn: int = 0,
        web_username: str = "",
        web_password: str = "",
    ) -> bool:
        """Add a new client.

        Args:
            remark: Client remark/name.
            vkey: Unique verification key (auto-generated if empty).
            basic_username: HTTP basic auth username.
            basic_password: HTTP basic auth password.
            rate_limit: Rate limit in KB/s (0 = unlimited).
            max_conn: Maximum connections (0 = unlimited).
            web_username: Web interface username.
            web_password: Web interface password.

        Returns:
            True if successful.
        """
        data = {
            "remark": remark,
            "u": basic_username,
            "p": basic_password,
            "vkey": vkey,
            "config_conn_allow": 1,
            "compress": 0,
            "crypt": 0,
            "rate_limit": rate_limit,
            "max_conn": max_conn,
            "web_username": web_username,
            "web_password": web_password,
        }
        result = self._request("/client/add", method="POST", data=data)
        return result.get("status") == 1

    def edit_client(
        self,
        client_id: int,
        remark: str,
        vkey: str = "",
        basic_username: str = "",
        basic_password: str = "",
        rate_limit: int = 0,
        max_conn: int = 0,
        web_username: str = "",
        web_password: str = "",
    ) -> bool:
        """Edit an existing client.

        Args:
            client_id: The client ID to edit.
            remark: Client remark/name.
            vkey: Unique verification key.
            basic_username: HTTP basic auth username.
            basic_password: HTTP basic auth password.
            rate_limit: Rate limit in KB/s (0 = unlimited).
            max_conn: Maximum connections (0 = unlimited).
            web_username: Web interface username.
            web_password: Web interface password.

        Returns:
            True if successful.
        """
        data = {
            "id": client_id,
            "remark": remark,
            "u": basic_username,
            "p": basic_password,
            "vkey": vkey,
            "config_conn_allow": 1,
            "compress": 0,
            "crypt": 0,
            "rate_limit": rate_limit,
            "max_conn": max_conn,
            "web_username": web_username,
            "web_password": web_password,
        }
        result = self._request("/client/edit", method="POST", data=data)
        return result.get("status") == 1

    def del_client(self, client_id: int) -> bool:
        """Delete a client.

        Args:
            client_id: The client ID to delete.

        Returns:
            True if successful.
        """
        result = self._request("/client/del", method="POST", data={"id": client_id})
        return result.get("status") == 1

    # ==================== Tunnel Management ====================

    # NPS API requires the 'type' parameter to return tunnel results.
    # When no type is specified, we query all known types and merge.
    TUNNEL_TYPES = ("tcp", "udp", "socks5", "httpProxy", "secret", "p2p", "file")

    def list_tunnels(
        self,
        client_id: int | None = None,
        tunnel_type: str = "",
        search: str = "",
        offset: int = 0,
        limit: int = 100,
    ) -> list[TunnelInfo]:
        """List tunnels.

        The NPS API requires a 'type' parameter to return results. When
        ``tunnel_type`` is empty, this method queries all known tunnel types
        and merges the results.

        Args:
            client_id: Filter by client ID (None for all).
            tunnel_type: Filter by type ("tcp", "udp", "socks5", "httpProxy",
                "secret", "p2p", "file"). Empty string queries all types.
            search: Search keyword.
            offset: Pagination offset.
            limit: Maximum number of results per type.

        Returns:
            List of tunnel information dictionaries.
        """
        if tunnel_type:
            return self._list_tunnels_by_type(
                tunnel_type,
                client_id=client_id,
                search=search,
                offset=offset,
                limit=limit,
            )

        # Query all tunnel types and merge results
        all_tunnels: list[TunnelInfo] = []
        for t in self.TUNNEL_TYPES:
            tunnels = self._list_tunnels_by_type(
                t,
                client_id=client_id,
                search=search,
                offset=offset,
                limit=limit,
            )
            all_tunnels.extend(tunnels)
        return all_tunnels

    def _list_tunnels_by_type(
        self,
        tunnel_type: str,
        client_id: int | None = None,
        search: str = "",
        offset: int = 0,
        limit: int = 100,
    ) -> list[TunnelInfo]:
        """List tunnels of a specific type.

        Args:
            tunnel_type: Tunnel type (required by NPS API).
            client_id: Filter by client ID (None for all).
            search: Search keyword.
            offset: Pagination offset.
            limit: Maximum number of results.

        Returns:
            List of tunnel information dictionaries.
        """
        data: dict[str, Any] = {
            "type": tunnel_type,
            "search": search,
            "offset": offset,
            "limit": limit,
        }
        if client_id is not None:
            data["client_id"] = client_id

        result = self._request("/index/gettunnel", method="POST", data=data)
        return result.get("rows", [])

    def get_tunnel(self, tunnel_id: int) -> TunnelInfo | None:
        """Get a single tunnel by ID.

        Args:
            tunnel_id: The tunnel ID.

        Returns:
            Tunnel information or None if not found.
        """
        result = self._request(
            "/index/getonetunnel", method="POST", data={"id": tunnel_id}
        )
        if result.get("status") == 1:
            return result.get("data")
        return None

    def add_tunnel(
        self,
        client_id: int,
        tunnel_type: str,
        port: int = 0,
        target: str = "",
        remark: str = "",
        password: str = "",
        server_ip: str = "",
        flow_limit: str = "",
        time_limit: str = "",
        local_proxy: int = 0,
        local_path: str = "",
        strip_pre: str = "",
    ) -> bool:
        """Add a new tunnel.

        Args:
            client_id: The client ID.
            tunnel_type: Tunnel type ("tcp", "udp", "socks5", "httpProxy",
                "secret", "p2p", "file").
            port: Server port (0 or negative for auto-assign).
            target: Target address (e.g., "127.0.0.1:8080"). Supports
                multiple targets separated by newlines.
            remark: Tunnel remark.
            password: Tunnel password (for socks5/httpProxy).
            server_ip: Server IP address.
            flow_limit: Flow limit in MB (empty for unlimited).
            time_limit: Time limit (empty for unlimited).
            local_proxy: Enable local proxy (0=no, 1=yes).
            local_path: Local path (for file service).
            strip_pre: URL prefix stripping.

        Returns:
            True if successful.
        """
        data: dict[str, Any] = {
            "client_id": client_id,
            "type": tunnel_type,
            "port": port,
            "target": target,
            "remark": remark,
            "password": password,
        }
        if server_ip:
            data["server_ip"] = server_ip
        if flow_limit:
            data["flow_limit"] = flow_limit
        if time_limit:
            data["time_limit"] = time_limit
        if local_proxy:
            data["local_proxy"] = local_proxy
        if local_path:
            data["local_path"] = local_path
        if strip_pre:
            data["strip_pre"] = strip_pre

        result = self._request("/index/add", method="POST", data=data)
        return result.get("status") == 1

    def edit_tunnel(
        self,
        tunnel_id: int,
        client_id: int,
        tunnel_type: str,
        port: int = 0,
        target: str = "",
        remark: str = "",
        password: str = "",
        server_ip: str = "",
        flow_limit: str = "",
        time_limit: str = "",
        local_proxy: int = 0,
        local_path: str = "",
        strip_pre: str = "",
    ) -> bool:
        """Edit an existing tunnel.

        Args:
            tunnel_id: The tunnel ID to edit.
            client_id: The client ID.
            tunnel_type: Tunnel type.
            port: Server port.
            target: Target address.
            remark: Tunnel remark.
            password: Tunnel password.
            server_ip: Server IP address.
            flow_limit: Flow limit in MB (empty for unlimited).
            time_limit: Time limit (empty for unlimited).
            local_proxy: Enable local proxy (0=no, 1=yes).
            local_path: Local path (for file service).
            strip_pre: URL prefix stripping.

        Returns:
            True if successful.
        """
        data: dict[str, Any] = {
            "id": tunnel_id,
            "client_id": client_id,
            "type": tunnel_type,
            "port": port,
            "target": target,
            "remark": remark,
            "password": password,
        }
        if server_ip:
            data["server_ip"] = server_ip
        if flow_limit:
            data["flow_limit"] = flow_limit
        if time_limit:
            data["time_limit"] = time_limit
        if local_proxy:
            data["local_proxy"] = local_proxy
        if local_path:
            data["local_path"] = local_path
        if strip_pre:
            data["strip_pre"] = strip_pre

        result = self._request("/index/edit", method="POST", data=data)
        return result.get("status") == 1

    def del_tunnel(self, tunnel_id: int) -> bool:
        """Delete a tunnel.

        Args:
            tunnel_id: The tunnel ID to delete.

        Returns:
            True if successful.
        """
        result = self._request("/index/del", method="POST", data={"id": tunnel_id})
        return result.get("status") == 1

    def start_tunnel(self, tunnel_id: int) -> bool:
        """Start a tunnel.

        Args:
            tunnel_id: The tunnel ID to start.

        Returns:
            True if successful.
        """
        result = self._request("/index/start", method="POST", data={"id": tunnel_id})
        return result.get("status") == 1

    def stop_tunnel(self, tunnel_id: int) -> bool:
        """Stop a tunnel.

        Args:
            tunnel_id: The tunnel ID to stop.

        Returns:
            True if successful.
        """
        result = self._request("/index/stop", method="POST", data={"id": tunnel_id})
        return result.get("status") == 1

    # ==================== Host Management ====================

    def list_hosts(
        self,
        client_id: int | None = None,
        search: str = "",
        offset: int = 0,
        limit: int = 100,
    ) -> list[HostInfo]:
        """List all host (domain) mappings.

        Args:
            client_id: Filter by client ID (None for all).
            search: Search keyword.
            offset: Pagination offset.
            limit: Maximum number of results.

        Returns:
            List of host information dictionaries.
        """
        data: dict[str, Any] = {
            "search": search,
            "offset": offset,
            "limit": limit,
        }
        if client_id is not None:
            data["client_id"] = client_id

        result = self._request("/index/hostlist", method="POST", data=data)
        return result.get("rows", [])

    def add_host(
        self,
        client_id: int,
        host: str,
        target: str,
        remark: str = "",
        location: str = "",
        scheme: str = "all",
        header_change: str = "",
        host_change: str = "",
    ) -> bool:
        """Add a new host (domain) mapping.

        Args:
            client_id: The client ID.
            host: The domain name (e.g., "app.example.com").
            target: Target address (e.g., "127.0.0.1:8080").
            remark: Host remark.
            location: URL path prefix (e.g., "/api").
            scheme: URL scheme ("http", "https", "all").
            header_change: Header modification rules.
            host_change: Host header modification.

        Returns:
            True if successful.
        """
        data = {
            "client_id": client_id,
            "host": host,
            "target": target,
            "remark": remark,
            "location": location,
            "scheme": scheme,
            "header": header_change,
            "hostchange": host_change,
        }
        result = self._request("/index/addhost", method="POST", data=data)
        return result.get("status") == 1

    def edit_host(
        self,
        host_id: int,
        client_id: int,
        host: str,
        target: str,
        remark: str = "",
        location: str = "",
        scheme: str = "all",
        header_change: str = "",
        host_change: str = "",
    ) -> bool:
        """Edit an existing host mapping.

        Args:
            host_id: The host ID to edit.
            client_id: The client ID.
            host: The domain name.
            target: Target address.
            remark: Host remark.
            location: URL path prefix.
            scheme: URL scheme.
            header_change: Header modification rules.
            host_change: Host header modification.

        Returns:
            True if successful.
        """
        data = {
            "id": host_id,
            "client_id": client_id,
            "host": host,
            "target": target,
            "remark": remark,
            "location": location,
            "scheme": scheme,
            "header": header_change,
            "hostchange": host_change,
        }
        result = self._request("/index/edithost", method="POST", data=data)
        return result.get("status") == 1

    def del_host(self, host_id: int) -> bool:
        """Delete a host mapping.

        Args:
            host_id: The host ID to delete.

        Returns:
            True if successful.
        """
        result = self._request("/index/delhost", method="POST", data={"id": host_id})
        return result.get("status") == 1


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
        """Get NPS client by edge name.

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
        for name, client in self._clients.items():
            try:
                result[name] = client.list_clients()
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
        for name, client in self._clients.items():
            try:
                result[name] = client.list_tunnels()
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
        for name, client in self._clients.items():
            try:
                result[name] = client.list_hosts()
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
        for name, client in self._clients.items():
            try:
                results[name] = client.add_client(remark=remark, vkey=vkey, **kwargs)
            except NPSError as e:
                logger.error(f"Failed to add client to {name}: {e}")
                results[name] = False
        return results

    def broadcast_host(
        self,
        client_remark: str,
        host: str,
        target: str,
        **kwargs: Any,
    ) -> dict[str, bool]:
        """Add a host mapping to all edges.

        This method finds the client by remark on each edge and adds the host.

        Args:
            client_remark: Client remark to find.
            host: Domain name.
            target: Target address.
            **kwargs: Additional host parameters.

        Returns:
            Dictionary mapping edge names to success status.
        """
        results: dict[str, bool] = {}
        for name, client in self._clients.items():
            try:
                # Find client by remark
                clients = client.list_clients(search=client_remark)
                matching = [c for c in clients if c.get("Remark") == client_remark]
                if not matching:
                    logger.warning(f"Client '{client_remark}' not found on {name}")
                    results[name] = False
                    continue

                client_id = matching[0]["Id"]
                results[name] = client.add_host(
                    client_id=client_id, host=host, target=target, **kwargs
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
        source_clients = source.list_clients() if sync_clients else []
        # Note: Tunnel and host sync requires client ID mapping
        # which is more complex and should be implemented based on specific needs
        # source_tunnels = source.list_tunnels() if sync_tunnels else []
        # source_hosts = source.list_hosts() if sync_hosts else []
        _ = sync_tunnels, sync_hosts  # Mark as intentionally unused for now

        for target_name, target_client in self._clients.items():
            if target_name == source_name:
                continue

            results[target_name] = {}

            # Sync clients
            if sync_clients:
                for client_info in source_clients:
                    vkey = client_info.get("VerifyKey", "")
                    remark = client_info.get("Remark", "")
                    try:
                        success = target_client.add_client(remark=remark, vkey=vkey)
                        results[target_name][f"client:{remark}"] = success
                    except NPSError as e:
                        logger.error(
                            f"Failed to sync client {remark} to {target_name}: {e}"
                        )
                        results[target_name][f"client:{remark}"] = False

        return results
