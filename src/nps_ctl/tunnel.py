"""NPS tunnel management API functions.

This module provides functions for managing tunnels on an NPS server,
including listing, adding, editing, starting, stopping, and deleting tunnels.

Supports both legacy (/index/*) and modern (/api/*) API endpoints.
The modern API eliminates the legacy 7-request fan-out for listing all
tunnel types, reducing it to a single GET request.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .types import TunnelInfo

if TYPE_CHECKING:
    from .base import NPSClient

# NPS legacy API requires the 'type' parameter to return tunnel results.
# When no type is specified, we query all known types and merge.
TUNNEL_TYPES = ("tcp", "udp", "socks5", "httpProxy", "secret", "p2p", "file")


# --- Public API (dispatch to v1/v2) ---


def list_tunnels(
    nps: NPSClient,
    client_id: int | None = None,
    tunnel_type: str = "",
    search: str = "",
    offset: int = 0,
    limit: int = 100,
) -> list[TunnelInfo]:
    """List tunnels.

    The legacy NPS API requires a 'type' parameter to return results. When
    ``tunnel_type`` is empty, the legacy path queries all known tunnel types
    and merges the results (7 requests). The modern API handles this in a
    single request.

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
    if nps.is_modern:
        return _list_tunnels_v2(nps, client_id, tunnel_type, search, offset, limit)
    return _list_tunnels_v1(nps, client_id, tunnel_type, search, offset, limit)


def get_tunnel(nps: NPSClient, tunnel_id: int) -> TunnelInfo | None:
    """Get a single tunnel by ID.

    Args:
        nps: NPSClient instance.
        tunnel_id: The tunnel ID.

    Returns:
        Tunnel information or None if not found.
    """
    if nps.is_modern:
        return _get_tunnel_v2(nps, tunnel_id)
    return _get_tunnel_v1(nps, tunnel_id)


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
    if nps.is_modern:
        return _add_tunnel_v2(
            nps,
            client_id,
            tunnel_type,
            port,
            target,
            remark,
            password,
            server_ip,
            flow_limit,
            time_limit,
            local_proxy,
            local_path,
            strip_pre,
        )
    return _add_tunnel_v1(
        nps,
        client_id,
        tunnel_type,
        port,
        target,
        remark,
        password,
        server_ip,
        flow_limit,
        time_limit,
        local_proxy,
        local_path,
        strip_pre,
    )


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
    if nps.is_modern:
        return _edit_tunnel_v2(
            nps,
            tunnel_id,
            client_id,
            tunnel_type,
            port,
            target,
            remark,
            password,
            server_ip,
            flow_limit,
            time_limit,
            local_proxy,
            local_path,
            strip_pre,
        )
    return _edit_tunnel_v1(
        nps,
        tunnel_id,
        client_id,
        tunnel_type,
        port,
        target,
        remark,
        password,
        server_ip,
        flow_limit,
        time_limit,
        local_proxy,
        local_path,
        strip_pre,
    )


def del_tunnel(nps: NPSClient, tunnel_id: int) -> bool:
    """Delete a tunnel.

    Args:
        nps: NPSClient instance.
        tunnel_id: The tunnel ID to delete.

    Returns:
        True if successful.
    """
    if nps.is_modern:
        return _del_tunnel_v2(nps, tunnel_id)
    return _del_tunnel_v1(nps, tunnel_id)


def start_tunnel(nps: NPSClient, tunnel_id: int) -> bool:
    """Start a tunnel.

    Args:
        nps: NPSClient instance.
        tunnel_id: The tunnel ID to start.

    Returns:
        True if successful.
    """
    if nps.is_modern:
        return _start_tunnel_v2(nps, tunnel_id)
    return _start_tunnel_v1(nps, tunnel_id)


def stop_tunnel(nps: NPSClient, tunnel_id: int) -> bool:
    """Stop a tunnel.

    Args:
        nps: NPSClient instance.
        tunnel_id: The tunnel ID to stop.

    Returns:
        True if successful.
    """
    if nps.is_modern:
        return _stop_tunnel_v2(nps, tunnel_id)
    return _stop_tunnel_v1(nps, tunnel_id)


# --- Legacy API (v1) ---


def _list_tunnels_by_type_v1(
    nps: NPSClient,
    tunnel_type: str,
    client_id: int | None = None,
    search: str = "",
    offset: int = 0,
    limit: int = 100,
) -> list[TunnelInfo]:
    """List tunnels of a specific type (legacy API)."""
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


def _list_tunnels_v1(
    nps: NPSClient,
    client_id: int | None,
    tunnel_type: str,
    search: str,
    offset: int,
    limit: int,
) -> list[TunnelInfo]:
    if tunnel_type:
        return _list_tunnels_by_type_v1(
            nps,
            tunnel_type,
            client_id=client_id,
            search=search,
            offset=offset,
            limit=limit,
        )
    # Query all tunnel types and merge results (7 requests)
    all_tunnels: list[TunnelInfo] = []
    for t in TUNNEL_TYPES:
        tunnels = _list_tunnels_by_type_v1(
            nps,
            t,
            client_id=client_id,
            search=search,
            offset=offset,
            limit=limit,
        )
        all_tunnels.extend(tunnels)
    return all_tunnels


def _get_tunnel_v1(nps: NPSClient, tunnel_id: int) -> TunnelInfo | None:
    result = nps.request("/index/getonetunnel", method="POST", data={"id": tunnel_id})
    if result.get("status") == 1:
        return result.get("data")
    return None


def _add_tunnel_v1(
    nps: NPSClient,
    client_id: int,
    tunnel_type: str,
    port: int,
    target: str,
    remark: str,
    password: str,
    server_ip: str,
    flow_limit: str,
    time_limit: str,
    local_proxy: int,
    local_path: str,
    strip_pre: str,
) -> bool:
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


def _edit_tunnel_v1(
    nps: NPSClient,
    tunnel_id: int,
    client_id: int,
    tunnel_type: str,
    port: int,
    target: str,
    remark: str,
    password: str,
    server_ip: str,
    flow_limit: str,
    time_limit: str,
    local_proxy: int,
    local_path: str,
    strip_pre: str,
) -> bool:
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


def _del_tunnel_v1(nps: NPSClient, tunnel_id: int) -> bool:
    result = nps.request("/index/del", method="POST", data={"id": tunnel_id})
    return result.get("status") == 1


def _start_tunnel_v1(nps: NPSClient, tunnel_id: int) -> bool:
    result = nps.request("/index/start", method="POST", data={"id": tunnel_id})
    return result.get("status") == 1


def _stop_tunnel_v1(nps: NPSClient, tunnel_id: int) -> bool:
    result = nps.request("/index/stop", method="POST", data={"id": tunnel_id})
    return result.get("status") == 1


# --- Modern API (v2) ---


def _normalize_tunnel(item: dict[str, Any]) -> TunnelInfo:
    """Normalize modern API tunnel response to legacy TunnelInfo format.

    Args:
        item: Tunnel data from modern API response.

    Returns:
        TunnelInfo dict with PascalCase keys matching legacy format.
    """
    client_data = item.get("client") or {}
    target_str = item.get("target", "")

    return {
        "Id": item.get("id", 0),
        "Port": item.get("port", 0),
        "ServerIp": item.get("server_ip", ""),
        "Mode": item.get("mode", ""),
        "Status": item.get("status", False),
        "RunStatus": item.get("run_status", False),
        "Remark": item.get("remark", ""),
        "Password": item.get("password", ""),
        "TargetAddr": target_str,
        "NoStore": item.get("no_store", False),
        "LocalPath": item.get("local_path", ""),
        "StripPre": item.get("strip_pre", ""),
        "Ports": "",
        "Flow": {
            "InletFlow": item.get("service_in_bytes", 0),
            "ExportFlow": item.get("service_out_bytes", 0),
        },
        "Client": {
            "Id": client_data.get("id", 0),
            "Remark": client_data.get("remark", ""),
            "VerifyKey": client_data.get("verify_key", ""),
            "Status": client_data.get("status", False),
            "IsConnect": client_data.get("is_connect", False),
        },
        "Target": {"TargetStr": target_str},
    }


def _list_tunnels_v2(
    nps: NPSClient,
    client_id: int | None,
    tunnel_type: str,
    search: str,
    offset: int,
    limit: int,
) -> list[TunnelInfo]:
    # Modern API returns all tunnel types in a single request
    params: dict[str, Any] = {"offset": offset, "limit": limit}
    if search:
        params["search"] = search
    if client_id is not None:
        params["client_id"] = client_id
    if tunnel_type:
        params["mode"] = tunnel_type
    resp = nps.api_request("GET", "/api/tunnels", params=params)
    items = resp.get("data", {}).get("items") or []
    return [_normalize_tunnel(i) for i in items]


def _get_tunnel_v2(nps: NPSClient, tunnel_id: int) -> TunnelInfo | None:
    resp = nps.api_request("GET", f"/api/tunnels/{tunnel_id}")
    item = resp.get("data", {}).get("item")
    if item is None:
        return None
    return _normalize_tunnel(item)


def _add_tunnel_v2(
    nps: NPSClient,
    client_id: int,
    tunnel_type: str,
    port: int,
    target: str,
    remark: str,
    password: str,
    server_ip: str,
    flow_limit: str,
    time_limit: str,
    local_proxy: int,
    local_path: str,
    strip_pre: str,
) -> bool:
    data: dict[str, Any] = {
        "client_id": client_id,
        "mode": tunnel_type,
        "port": port,
        "target": target,
        "remark": remark,
        "password": password,
    }
    if server_ip:
        data["server_ip"] = server_ip
    if local_proxy:
        data["local_proxy"] = bool(local_proxy)
    if local_path:
        data["local_path"] = local_path
    if strip_pre:
        data["strip_pre"] = strip_pre
    resp = nps.api_request("POST", "/api/tunnels", data=data)
    return resp.get("data") is not None


def _edit_tunnel_v2(
    nps: NPSClient,
    tunnel_id: int,
    client_id: int,
    tunnel_type: str,
    port: int,
    target: str,
    remark: str,
    password: str,
    server_ip: str,
    flow_limit: str,
    time_limit: str,
    local_proxy: int,
    local_path: str,
    strip_pre: str,
) -> bool:
    data: dict[str, Any] = {
        "client_id": client_id,
        "mode": tunnel_type,
        "port": port,
        "target": target,
        "remark": remark,
        "password": password,
    }
    if server_ip:
        data["server_ip"] = server_ip
    if local_proxy:
        data["local_proxy"] = bool(local_proxy)
    if local_path:
        data["local_path"] = local_path
    if strip_pre:
        data["strip_pre"] = strip_pre
    resp = nps.api_request(
        "POST", f"/api/tunnels/{tunnel_id}/actions/update", data=data
    )
    return resp.get("data") is not None


def _del_tunnel_v2(nps: NPSClient, tunnel_id: int) -> bool:
    resp = nps.api_request("POST", f"/api/tunnels/{tunnel_id}/actions/delete")
    return resp.get("data") is not None


def _start_tunnel_v2(nps: NPSClient, tunnel_id: int) -> bool:
    resp = nps.api_request("POST", f"/api/tunnels/{tunnel_id}/actions/start")
    return resp.get("data") is not None


def _stop_tunnel_v2(nps: NPSClient, tunnel_id: int) -> bool:
    resp = nps.api_request("POST", f"/api/tunnels/{tunnel_id}/actions/stop")
    return resp.get("data") is not None
