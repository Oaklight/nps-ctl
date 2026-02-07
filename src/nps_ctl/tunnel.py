"""NPS tunnel management API functions.

This module provides functions for managing tunnels on an NPS server,
including listing, adding, editing, starting, stopping, and deleting tunnels.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from nps_ctl.types import TunnelInfo

if TYPE_CHECKING:
    from nps_ctl.base import NPSClient

# NPS API requires the 'type' parameter to return tunnel results.
# When no type is specified, we query all known types and merge.
TUNNEL_TYPES = ("tcp", "udp", "socks5", "httpProxy", "secret", "p2p", "file")


def list_tunnels(
    nps: NPSClient,
    client_id: int | None = None,
    tunnel_type: str = "",
    search: str = "",
    offset: int = 0,
    limit: int = 100,
) -> list[TunnelInfo]:
    """List tunnels.

    The NPS API requires a 'type' parameter to return results. When
    ``tunnel_type`` is empty, this function queries all known tunnel types
    and merges the results.

    Args:
        nps: NPSClient instance.
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
        return _list_tunnels_by_type(
            nps,
            tunnel_type,
            client_id=client_id,
            search=search,
            offset=offset,
            limit=limit,
        )

    # Query all tunnel types and merge results
    all_tunnels: list[TunnelInfo] = []
    for t in TUNNEL_TYPES:
        tunnels = _list_tunnels_by_type(
            nps,
            t,
            client_id=client_id,
            search=search,
            offset=offset,
            limit=limit,
        )
        all_tunnels.extend(tunnels)
    return all_tunnels


def _list_tunnels_by_type(
    nps: NPSClient,
    tunnel_type: str,
    client_id: int | None = None,
    search: str = "",
    offset: int = 0,
    limit: int = 100,
) -> list[TunnelInfo]:
    """List tunnels of a specific type.

    Args:
        nps: NPSClient instance.
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

    result = nps.request("/index/gettunnel", method="POST", data=data)
    return result.get("rows", [])


def get_tunnel(nps: NPSClient, tunnel_id: int) -> TunnelInfo | None:
    """Get a single tunnel by ID.

    Args:
        nps: NPSClient instance.
        tunnel_id: The tunnel ID.

    Returns:
        Tunnel information or None if not found.
    """
    result = nps.request("/index/getonetunnel", method="POST", data={"id": tunnel_id})
    if result.get("status") == 1:
        return result.get("data")
    return None


def add_tunnel(
    nps: NPSClient,
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
        nps: NPSClient instance.
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

    result = nps.request("/index/add", method="POST", data=data)
    return result.get("status") == 1


def edit_tunnel(
    nps: NPSClient,
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
        nps: NPSClient instance.
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

    result = nps.request("/index/edit", method="POST", data=data)
    return result.get("status") == 1


def del_tunnel(nps: NPSClient, tunnel_id: int) -> bool:
    """Delete a tunnel.

    Args:
        nps: NPSClient instance.
        tunnel_id: The tunnel ID to delete.

    Returns:
        True if successful.
    """
    result = nps.request("/index/del", method="POST", data={"id": tunnel_id})
    return result.get("status") == 1


def start_tunnel(nps: NPSClient, tunnel_id: int) -> bool:
    """Start a tunnel.

    Args:
        nps: NPSClient instance.
        tunnel_id: The tunnel ID to start.

    Returns:
        True if successful.
    """
    result = nps.request("/index/start", method="POST", data={"id": tunnel_id})
    return result.get("status") == 1


def stop_tunnel(nps: NPSClient, tunnel_id: int) -> bool:
    """Stop a tunnel.

    Args:
        nps: NPSClient instance.
        tunnel_id: The tunnel ID to stop.

    Returns:
        True if successful.
    """
    result = nps.request("/index/stop", method="POST", data={"id": tunnel_id})
    return result.get("status") == 1
