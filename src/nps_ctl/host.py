"""NPS host (domain) management API functions.

This module provides functions for managing host (domain) mappings on an
NPS server, including listing, adding, editing, and deleting hosts.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .types import HostInfo

if TYPE_CHECKING:
    from .base import NPSClient


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
    data: dict[str, Any] = {
        "search": search,
        "offset": offset,
        "limit": limit,
    }
    if client_id is not None:
        data["client_id"] = client_id

    result = nps.request("/index/hostlist", method="POST", data=data)
    return result.get("rows", [])


def get_host(nps: NPSClient, host_id: int) -> HostInfo | None:
    """Get a single host by ID.

    Args:
        nps: NPSClient instance.
        host_id: The host ID.

    Returns:
        Host information or None if not found.
    """
    result = nps.request("/index/gethost", method="POST", data={"id": host_id})
    if result.get("status") == 1 or result.get("code") == 1:
        return result.get("data")
    return None


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


def del_host(nps: NPSClient, host_id: int) -> bool:
    """Delete a host mapping.

    Args:
        nps: NPSClient instance.
        host_id: The host ID to delete.

    Returns:
        True if successful.
    """
    result = nps.request("/index/delhost", method="POST", data={"id": host_id})
    return result.get("status") == 1
