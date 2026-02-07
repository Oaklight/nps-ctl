"""NPS client (NPC) management API functions.

This module provides functions for managing NPC clients on an NPS server,
including listing, adding, editing, and deleting clients.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from nps_ctl.types import ClientInfo

if TYPE_CHECKING:
    from nps_ctl.base import NPSClient


def list_clients(
    nps: NPSClient,
    search: str = "",
    order: str = "asc",
    offset: int = 0,
    limit: int = 100,
) -> list[ClientInfo]:
    """List all clients.

    Args:
        nps: NPSClient instance.
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
    result = nps.request("/client/list", method="POST", data=data)
    return result.get("rows", [])


def get_client(nps: NPSClient, client_id: int) -> ClientInfo | None:
    """Get a single client by ID.

    Args:
        nps: NPSClient instance.
        client_id: The client ID.

    Returns:
        Client information or None if not found.
    """
    result = nps.request("/client/getclient", data={"id": client_id})
    if result.get("status") == 1:
        return result.get("data")
    return None


def add_client(
    nps: NPSClient,
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
        nps: NPSClient instance.
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
    result = nps.request("/client/add", method="POST", data=data)
    return result.get("status") == 1


def edit_client(
    nps: NPSClient,
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
        nps: NPSClient instance.
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
    result = nps.request("/client/edit", method="POST", data=data)
    return result.get("status") == 1


def del_client(nps: NPSClient, client_id: int) -> bool:
    """Delete a client.

    Args:
        nps: NPSClient instance.
        client_id: The client ID to delete.

    Returns:
        True if successful.
    """
    result = nps.request("/client/del", method="POST", data={"id": client_id})
    return result.get("status") == 1
