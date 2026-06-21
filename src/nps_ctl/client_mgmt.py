"""NPS client (NPC) management API functions.

This module provides functions for managing NPC clients on an NPS server,
including listing, adding, editing, and deleting clients.

Supports both legacy (/client/*) and modern (/api/*) API endpoints.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .types import ClientInfo

if TYPE_CHECKING:
    from .base import NPSClient


# --- Public API (dispatch to v1/v2) ---


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
    if nps.is_modern:
        return _list_clients_v2(nps, search, order, offset, limit)
    return _list_clients_v1(nps, search, order, offset, limit)


def get_client(nps: NPSClient, client_id: int) -> ClientInfo | None:
    """Get a single client by ID.

    Args:
        nps: NPSClient instance.
        client_id: The client ID.

    Returns:
        Client information or None if not found.
    """
    if nps.is_modern:
        return _get_client_v2(nps, client_id)
    return _get_client_v1(nps, client_id)


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
    if nps.is_modern:
        return _add_client_v2(
            nps,
            remark,
            vkey,
            basic_username,
            basic_password,
            rate_limit,
            max_conn,
            web_username,
            web_password,
        )
    return _add_client_v1(
        nps,
        remark,
        vkey,
        basic_username,
        basic_password,
        rate_limit,
        max_conn,
        web_username,
        web_password,
    )


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
    if nps.is_modern:
        return _edit_client_v2(
            nps,
            client_id,
            remark,
            vkey,
            basic_username,
            basic_password,
            rate_limit,
            max_conn,
            web_username,
            web_password,
        )
    return _edit_client_v1(
        nps,
        client_id,
        remark,
        vkey,
        basic_username,
        basic_password,
        rate_limit,
        max_conn,
        web_username,
        web_password,
    )


def del_client(nps: NPSClient, client_id: int) -> bool:
    """Delete a client.

    Args:
        nps: NPSClient instance.
        client_id: The client ID to delete.

    Returns:
        True if successful.
    """
    if nps.is_modern:
        return _del_client_v2(nps, client_id)
    return _del_client_v1(nps, client_id)


# --- Legacy API (v1) ---


def _list_clients_v1(
    nps: NPSClient, search: str, order: str, offset: int, limit: int
) -> list[ClientInfo]:
    data = {
        "search": search,
        "order": order,
        "offset": offset,
        "limit": limit,
    }
    result = nps.request("/client/list", method="POST", data=data)
    return result.get("rows", [])


def _get_client_v1(nps: NPSClient, client_id: int) -> ClientInfo | None:
    result = nps.request("/client/getclient", data={"id": client_id})
    if result.get("status") == 1:
        return result.get("data")
    return None


def _add_client_v1(
    nps: NPSClient,
    remark: str,
    vkey: str,
    basic_username: str,
    basic_password: str,
    rate_limit: int,
    max_conn: int,
    web_username: str,
    web_password: str,
) -> bool:
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


def _edit_client_v1(
    nps: NPSClient,
    client_id: int,
    remark: str,
    vkey: str,
    basic_username: str,
    basic_password: str,
    rate_limit: int,
    max_conn: int,
    web_username: str,
    web_password: str,
) -> bool:
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


def _del_client_v1(nps: NPSClient, client_id: int) -> bool:
    result = nps.request("/client/del", method="POST", data={"id": client_id})
    return result.get("status") == 1


# --- Modern API (v2) ---


def _normalize_client(item: dict[str, Any]) -> ClientInfo:
    """Normalize modern API client response to legacy ClientInfo format.

    Args:
        item: Client data from modern API response.

    Returns:
        ClientInfo dict with PascalCase keys matching legacy format.
    """
    config = item.get("config") or {}
    return {
        "Id": item.get("id", 0),
        "VerifyKey": item.get("verify_key", ""),
        "Addr": item.get("addr", ""),
        "Remark": item.get("remark", ""),
        "Status": item.get("status", False),
        "IsConnect": item.get("is_connect", False),
        "RateLimit": item.get("rate_limit_total_bps", 0),
        "Flow": {
            "InletFlow": item.get("service_in_bytes", 0),
            "ExportFlow": item.get("service_out_bytes", 0),
        },
        "MaxConn": item.get("max_connections", 0),
        "NowConn": item.get("now_conn", 0),
        "WebUserName": "",
        "WebPassword": "",
        "ConfigConnAllow": item.get("config_conn_allow", True),
        "Cnf": {
            "U": config.get("user", ""),
            "Compress": config.get("compress", False),
            "Crypt": config.get("crypt", False),
        },
    }


def _list_clients_v2(
    nps: NPSClient, search: str, order: str, offset: int, limit: int
) -> list[ClientInfo]:
    params: dict[str, Any] = {"offset": offset, "limit": limit, "order": order}
    if search:
        params["search"] = search
    resp = nps.api_request("GET", "/api/clients", params=params)
    items = resp.get("data", {}).get("items") or []
    return [_normalize_client(i) for i in items]


def _get_client_v2(nps: NPSClient, client_id: int) -> ClientInfo | None:
    resp = nps.api_request("GET", f"/api/clients/{client_id}")
    item = resp.get("data", {}).get("item")
    if item is None:
        return None
    return _normalize_client(item)


def _add_client_v2(
    nps: NPSClient,
    remark: str,
    vkey: str,
    basic_username: str,
    basic_password: str,
    rate_limit: int,
    max_conn: int,
    web_username: str,
    web_password: str,
) -> bool:
    data: dict[str, Any] = {
        "remark": remark,
        "verify_key": vkey,
        "config_conn_allow": True,
        "max_connections": max_conn,
    }
    if basic_username:
        data["username"] = basic_username
    if basic_password:
        data["password"] = basic_password
    if rate_limit:
        # Legacy rate_limit is KB/s, modern API uses bytes/s
        data["rate_limit_total_bps"] = rate_limit * 1024
    resp = nps.api_request("POST", "/api/clients", data=data)
    return resp.get("data") is not None


def _edit_client_v2(
    nps: NPSClient,
    client_id: int,
    remark: str,
    vkey: str,
    basic_username: str,
    basic_password: str,
    rate_limit: int,
    max_conn: int,
    web_username: str,
    web_password: str,
) -> bool:
    data: dict[str, Any] = {
        "remark": remark,
        "verify_key": vkey,
        "config_conn_allow": True,
        "max_connections": max_conn,
    }
    if basic_username:
        data["username"] = basic_username
    if basic_password:
        data["password"] = basic_password
    if rate_limit:
        data["rate_limit_total_bps"] = rate_limit * 1024
    resp = nps.api_request(
        "POST", f"/api/clients/{client_id}/actions/update", data=data
    )
    return resp.get("data") is not None


def _del_client_v2(nps: NPSClient, client_id: int) -> bool:
    resp = nps.api_request("POST", f"/api/clients/{client_id}/actions/delete")
    return resp.get("data") is not None
