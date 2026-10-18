"""Utility functions for NPS management.

This module provides utility functions that can be used independently
or as part of the nps-ctl CLI.
"""

from __future__ import annotations

import base64
import secrets
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .base import NPSClient


def fetch_all_pages(
    nps: NPSClient,
    path: str,
    data: dict[str, Any],
    *,
    limit: int = 100,
    max_pages: int = 1000,
) -> list[dict[str, Any]]:
    """Fetch every page from a paginated NPS list endpoint.

    NPS list endpoints return ``{"rows": [...], "total": N}``. This helper
    advances ``offset`` until the reported total is reached, the page is
    empty, or the safety page cap is hit. When ``total`` is present it is
    authoritative, so a server that clamps ``limit`` below the requested page
    size still gets every row. The server must honour ``offset``.

    Args:
        nps: NPSClient instance.
        path: API path, for example ``/index/hostlist``.
        data: Base request payload. ``offset`` and ``limit`` are overwritten.
        limit: Requested page size.
        max_pages: Maximum number of requests to make.

    Returns:
        All rows across pages.
    """
    rows: list[dict[str, Any]] = []
    offset = int(data.get("offset", 0) or 0)

    for _ in range(max_pages):
        page_data = dict(data)
        page_data["offset"] = offset
        page_data["limit"] = limit
        result = nps.request(path, method="POST", data=page_data)
        page = result.get("rows", [])
        rows.extend(page)
        offset += len(page)

        total = int(result.get("total", 0) or 0)
        if not page:
            break
        if total:
            if offset >= total:
                break
        elif len(page) < limit:
            break

    return rows


def extract_api_items(resp: dict[str, Any]) -> list[dict[str, Any]]:
    """Return the row list from a modern list response.

    Accepts the documented ``{"data": [...]}`` envelope and the wrapper
    variants some builds use (``data.items``, ``data.rows``, or a top-level
    ``rows`` array).

    Args:
        resp: Decoded ``/api/*`` response.

    Returns:
        The row list, or an empty list when the payload is not a list.
    """
    data = resp.get("data")
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("items", "rows"):
            rows = data.get(key)
            if isinstance(rows, list):
                return rows
    rows = resp.get("rows")
    return rows if isinstance(rows, list) else []


def extract_api_item(resp: dict[str, Any]) -> dict[str, Any] | None:
    """Return the resource object from a modern single-item response.

    The server normally puts the resource directly in ``data``. Some
    builds wrap it as ``{"data": {"item": {...}}}``; accept both so callers
    never merge an empty record into an edit payload.

    Args:
        resp: Decoded ``/api/*`` response.

    Returns:
        The resource dictionary, or None when no object is present.
    """
    data = resp.get("data")
    if not isinstance(data, dict):
        return None
    for key in ("item", "data"):
        nested = data.get(key)
        if isinstance(nested, dict) and set(data) <= {key, "meta"}:
            return nested
    return data


def fetch_all_api_pages(
    nps: NPSClient,
    path: str,
    params: dict[str, Any],
    *,
    limit: int = 100,
    max_pages: int = 1000,
) -> list[dict[str, Any]]:
    """Fetch every page from a modern ``/api/*`` list endpoint.

    Modern list responses return the rows directly in ``data`` and pagination
    under ``meta.pagination``::

        {"data": [...], "meta": {"pagination": {"total": N, "has_more": bool}}}

    When ``total`` is present it is authoritative; ``has_more`` is honoured
    when present; otherwise a short page ends the walk. The server must
    honour ``offset``. If the server reports neither ``total`` nor
    ``has_more`` and clamps ``limit`` below the requested size, the walk
    ends early and the caller cannot distinguish that from a complete list.

    Args:
        nps: NPSClient instance.
        path: API path, for example ``/api/hosts``.
        params: Base query parameters. ``offset`` and ``limit`` are
            overwritten.
        limit: Requested page size.
        max_pages: Maximum number of requests to make.

    Returns:
        All items across pages.
    """
    items: list[dict[str, Any]] = []
    offset = int(params.get("offset", 0) or 0)

    for _ in range(max_pages):
        page_params = dict(params)
        page_params["offset"] = offset
        page_params["limit"] = limit
        resp = nps.api_request("GET", path, params=page_params)
        page = extract_api_items(resp)
        items.extend(page)
        offset += len(page)

        meta_raw = resp.get("meta")
        meta: dict[str, Any] = meta_raw if isinstance(meta_raw, dict) else {}
        pagination_raw = meta.get("pagination")
        pagination: dict[str, Any] = (
            pagination_raw if isinstance(pagination_raw, dict) else {}
        )
        data_raw = resp.get("data")
        data: dict[str, Any] = data_raw if isinstance(data_raw, dict) else {}
        total = 0
        for container in (pagination, meta, data):
            if container.get("total") is not None:
                total = int(container.get("total") or 0)
                break
        has_more = pagination.get("has_more")
        if has_more is None:
            has_more = meta.get("has_more")
        if has_more is None:
            has_more = data.get("has_more")
        if not page:
            break
        if has_more is False:
            break
        if total:
            if offset >= total:
                break
        elif has_more is not True and len(page) < limit:
            break

    return items


def generate_auth_key(length: int = 43) -> str:
    """Generate a random auth key for NPS API authentication.

    The generated key uses URL-safe base64 encoding, which is compatible
    with NPS auth_key requirements.

    Args:
        length: Length of the auth key. Default is 43, matching NPS default.

    Returns:
        A random URL-safe base64 encoded string of the specified length.

    Examples:
        >>> key = generate_auth_key()
        >>> len(key)
        43
        >>> key = generate_auth_key(32)
        >>> len(key)
        32
    """
    # Generate random bytes and encode as URL-safe base64
    # base64 encoding produces 4 characters for every 3 bytes
    num_bytes = (length * 3 + 3) // 4
    random_bytes = secrets.token_bytes(num_bytes)
    return base64.urlsafe_b64encode(random_bytes).decode("ascii")[:length]
