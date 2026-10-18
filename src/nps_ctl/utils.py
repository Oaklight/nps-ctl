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
