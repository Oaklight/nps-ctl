"""NPS host (domain) management API functions.

This module provides functions for managing host (domain) mappings on an
NPS server, including listing, adding, editing, and deleting hosts.

Supports both legacy (/index/*) and modern (/api/*) API endpoints.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .types import HostInfo

if TYPE_CHECKING:
    from .base import NPSClient


# --- Public API (dispatch to v1/v2) ---


def list_hosts(
    nps: NPSClient,
    client_id: int | None = None,
    search: str = "",
    offset: int = 0,
    limit: int = 100,
) -> list[HostInfo]:
    """List all host (domain) mappings.

    Args:
        nps: NPSClient instance.
        client_id: Filter by client ID (None for all).
        search: Search keyword.
        offset: Pagination offset.
        limit: Maximum number of results.

    Returns:
        List of host information dictionaries.
    """
    if nps.is_modern:
        return _list_hosts_v2(nps, client_id, search, offset, limit)
    return _list_hosts_v1(nps, client_id, search, offset, limit)


def get_host(nps: NPSClient, host_id: int) -> HostInfo | None:
    """Get a single host by ID.

    Args:
        nps: NPSClient instance.
        host_id: The host ID.

    Returns:
        Host information or None if not found.
    """
    if nps.is_modern:
        return _get_host_v2(nps, host_id)
    return _get_host_v1(nps, host_id)


def add_host(
    nps: NPSClient,
    client_id: int,
    host: str,
    target: str,
    remark: str = "",
    location: str = "",
    scheme: str = "all",
    header_change: str = "",
    host_change: str = "",
    auth: str = "",
) -> bool:
    """Add a new host (domain) mapping.

    Args:
        nps: NPSClient instance.
        client_id: The client ID.
        host: The domain name (e.g., "app.example.com").
        target: Target address (e.g., "127.0.0.1:8080").
        remark: Host remark.
        location: URL path prefix (e.g., "/api").
        scheme: URL scheme ("http", "https", "all").
        header_change: Header modification rules.
        host_change: Host header modification.
        auth: HTTP Basic Auth credentials (format: "user1=pass1\\nuser2=pass2").

    Returns:
        True if successful.
    """
    if nps.is_modern:
        return _add_host_v2(
            nps,
            client_id,
            host,
            target,
            remark,
            location,
            scheme,
            header_change,
            host_change,
            auth,
        )
    return _add_host_v1(
        nps,
        client_id,
        host,
        target,
        remark,
        location,
        scheme,
        header_change,
        host_change,
        auth,
    )


def edit_host(
    nps: NPSClient,
    host_id: int,
    client_id: int,
    host: str,
    target: str,
    remark: str = "",
    location: str = "",
    scheme: str = "all",
    header_change: str = "",
    host_change: str = "",
    auth: str = "",
) -> bool:
    """Edit an existing host mapping.

    Args:
        nps: NPSClient instance.
        host_id: The host ID to edit.
        client_id: The client ID.
        host: The domain name.
        target: Target address.
        remark: Host remark.
        location: URL path prefix.
        scheme: URL scheme.
        header_change: Header modification rules.
        host_change: Host header modification.
        auth: HTTP Basic Auth credentials (format: "user1=pass1\\nuser2=pass2").

    Returns:
        True if successful.
    """
    if nps.is_modern:
        return _edit_host_v2(
            nps,
            host_id,
            client_id,
            host,
            target,
            remark,
            location,
            scheme,
            header_change,
            host_change,
            auth,
        )
    return _edit_host_v1(
        nps,
        host_id,
        client_id,
        host,
        target,
        remark,
        location,
        scheme,
        header_change,
        host_change,
        auth,
    )


def del_host(nps: NPSClient, host_id: int) -> bool:
    """Delete a host mapping.

    Args:
        nps: NPSClient instance.
        host_id: The host ID to delete.

    Returns:
        True if successful.
    """
    if nps.is_modern:
        return _del_host_v2(nps, host_id)
    return _del_host_v1(nps, host_id)


# --- Legacy API (v1) ---


def _list_hosts_v1(
    nps: NPSClient,
    client_id: int | None,
    search: str,
    offset: int,
    limit: int,
) -> list[HostInfo]:
    data: dict[str, Any] = {
        "search": search,
        "offset": offset,
        "limit": limit,
    }
    if client_id is not None:
        data["client_id"] = client_id
    result = nps.request("/index/hostlist", method="POST", data=data)
    return result.get("rows", [])


def _get_host_v1(nps: NPSClient, host_id: int) -> HostInfo | None:
    result = nps.request("/index/gethost", method="POST", data={"id": host_id})
    if result.get("status") == 1:
        return result.get("data")
    return None


def _add_host_v1(
    nps: NPSClient,
    client_id: int,
    host: str,
    target: str,
    remark: str,
    location: str,
    scheme: str,
    header_change: str,
    host_change: str,
    auth: str,
) -> bool:
    data = {
        "client_id": client_id,
        "host": host,
        "target": target,
        "remark": remark,
        "location": location,
        "scheme": scheme,
        "header": header_change,
        "hostchange": host_change,
        "auth": auth,
    }
    result = nps.request("/index/addhost", method="POST", data=data)
    return result.get("status") == 1


def _edit_host_v1(
    nps: NPSClient,
    host_id: int,
    client_id: int,
    host: str,
    target: str,
    remark: str,
    location: str,
    scheme: str,
    header_change: str,
    host_change: str,
    auth: str,
) -> bool:
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
        "auth": auth,
    }
    result = nps.request("/index/edithost", method="POST", data=data)
    return result.get("status") == 1


def _del_host_v1(nps: NPSClient, host_id: int) -> bool:
    result = nps.request("/index/delhost", method="POST", data={"id": host_id})
    return result.get("status") == 1


# --- Modern API (v2) ---


def _normalize_host(item: dict[str, Any]) -> HostInfo:
    """Normalize modern API host response to legacy HostInfo format.

    Args:
        item: Host data from modern API response.

    Returns:
        HostInfo dict with PascalCase keys matching legacy format.
    """
    client_data = item.get("client") or {}
    target_str = item.get("target", "")

    return {
        "Id": item.get("id", 0),
        "Host": item.get("host", ""),
        "HeaderChange": item.get("header", ""),
        "HostChange": item.get("host_change", ""),
        "Location": item.get("location", ""),
        "Remark": item.get("remark", ""),
        "Scheme": item.get("scheme", "all"),
        "CertFilePath": item.get("cert_file", ""),
        "KeyFilePath": item.get("key_file", ""),
        "NoStore": item.get("no_store", False),
        "IsClose": item.get("is_close", False),
        "AutoHttps": item.get("auto_https", False),
        "Client": {
            "Id": client_data.get("id", 0),
            "Remark": client_data.get("remark", ""),
            "VerifyKey": client_data.get("verify_key", ""),
            "Status": client_data.get("status", False),
            "IsConnect": client_data.get("is_connect", False),
        },
        "Target": {"TargetStr": target_str},
        "UserAuth": {"Content": item.get("auth", "")},
    }


def _list_hosts_v2(
    nps: NPSClient,
    client_id: int | None,
    search: str,
    offset: int,
    limit: int,
) -> list[HostInfo]:
    params: dict[str, Any] = {"offset": offset, "limit": limit}
    if search:
        params["search"] = search
    if client_id is not None:
        params["client_id"] = client_id
    resp = nps.api_request("GET", "/api/hosts", params=params)
    items = resp.get("data", {}).get("items") or []
    return [_normalize_host(i) for i in items]


def _get_host_v2(nps: NPSClient, host_id: int) -> HostInfo | None:
    resp = nps.api_request("GET", f"/api/hosts/{host_id}")
    item = resp.get("data", {}).get("item")
    if item is None:
        return None
    return _normalize_host(item)


def _add_host_v2(
    nps: NPSClient,
    client_id: int,
    host: str,
    target: str,
    remark: str,
    location: str,
    scheme: str,
    header_change: str,
    host_change: str,
    auth: str,
) -> bool:
    data: dict[str, Any] = {
        "client_id": client_id,
        "host": host,
        "target": target,
        "remark": remark,
        "location": location,
        "scheme": scheme,
        "header": header_change,
        "host_change": host_change,
        "auth": auth,
    }
    resp = nps.api_request("POST", "/api/hosts", data=data)
    return resp.get("data") is not None


def _edit_host_v2(
    nps: NPSClient,
    host_id: int,
    client_id: int,
    host: str,
    target: str,
    remark: str,
    location: str,
    scheme: str,
    header_change: str,
    host_change: str,
    auth: str,
) -> bool:
    data: dict[str, Any] = {
        "client_id": client_id,
        "host": host,
        "target": target,
        "remark": remark,
        "location": location,
        "scheme": scheme,
        "header": header_change,
        "host_change": host_change,
        "auth": auth,
    }
    resp = nps.api_request("POST", f"/api/hosts/{host_id}/actions/update", data=data)
    return resp.get("data") is not None


def _del_host_v2(nps: NPSClient, host_id: int) -> bool:
    resp = nps.api_request("POST", f"/api/hosts/{host_id}/actions/delete")
    return resp.get("data") is not None
