"""Tests for paginated NPS list endpoints."""

from __future__ import annotations

import threading
import time

from nps_ctl import client_mgmt, host, tunnel


class FakeNPS:
    """Serve a paginated list endpoint from an in-memory row set."""

    is_modern = False

    def __init__(self, rows, total=None, page_cap=None):
        self.rows = rows
        self.total = len(rows) if total is None else total
        self.page_cap = page_cap
        self.requests = []

    def request(self, path, method="POST", data=None):
        data = data or {}
        offset = int(data.get("offset", 0))
        limit = int(data.get("limit", 100))
        if self.page_cap is not None:
            limit = min(limit, self.page_cap)
        self.requests.append((path, offset, limit))
        return {
            "rows": self.rows[offset : offset + limit],
            "total": self.total,
        }


def _rows(count: int):
    return [{"Id": index} for index in range(count)]


def test_list_hosts_fetches_all_pages():
    nps = FakeNPS(_rows(151))

    rows = host.list_hosts(nps)

    assert len(rows) == 151
    assert nps.requests == [
        ("/index/hostlist", 0, 100),
        ("/index/hostlist", 100, 100),
    ]


def test_list_hosts_uses_short_page_as_end():
    nps = FakeNPS(_rows(150), total=0)

    rows = host.list_hosts(nps)

    assert len(rows) == 150
    assert len(nps.requests) == 2


def test_list_hosts_paginate_false_single_request():
    nps = FakeNPS(_rows(151))

    rows = host.list_hosts(nps, limit=1, paginate=False)

    assert len(rows) == 1
    assert nps.requests == [("/index/hostlist", 0, 1)]


def test_list_hosts_uses_total_when_server_caps_page_size():
    nps = FakeNPS(_rows(151), page_cap=10)

    rows = host.list_hosts(nps)

    assert len(rows) == 151
    assert [request[1] for request in nps.requests] == [
        0,
        10,
        20,
        30,
        40,
        50,
        60,
        70,
        80,
        90,
        100,
        110,
        120,
        130,
        140,
        150,
    ]


def test_list_clients_fetches_all_pages():
    nps = FakeNPS(_rows(250))

    rows = client_mgmt.list_clients(nps)

    assert len(rows) == 250
    assert [request[1] for request in nps.requests] == [0, 100, 200]


def test_list_tunnels_fetches_all_pages_for_type():
    nps = FakeNPS([{"Id": index, "Mode": "tcp"} for index in range(150)])

    rows = tunnel.list_tunnels(nps, tunnel_type="tcp")

    assert len(rows) == 150
    assert len(nps.requests) == 2


class TypeFilteringNPS:
    """Legacy NPS that filters tunnels by exact mode equality."""

    is_modern = False

    def __init__(self, rows):
        self.rows = rows
        self.types = []

    def request(self, path, method="POST", data=None):
        data = data or {}
        tunnel_type = data.get("type", "")
        self.types.append(tunnel_type)
        rows = [row for row in self.rows if row.get("Mode") == tunnel_type]
        offset = int(data.get("offset", 0))
        limit = int(data.get("limit", 100))
        return {"rows": rows[offset : offset + limit], "total": len(rows)}


def test_list_tunnels_queries_mixproxy_mode():
    """djylb/nps stores socks5/httpProxy tunnels as mixProxy."""
    nps = TypeFilteringNPS(
        [
            {"Id": 1, "Mode": "tcp"},
            {"Id": 2, "Mode": "mixProxy"},
        ]
    )

    rows = tunnel.list_tunnels(nps)

    assert [row["Id"] for row in rows] == [1, 2]
    assert nps.types == list(tunnel.TUNNEL_TYPES)
    assert "mixProxy" in nps.types


MIX_PROXY_ROWS = [
    {
        "Id": 1,
        "Mode": "mixProxy",
        "Socks5Proxy": True,
        "HttpProxy": False,
        "Port": 1080,
    },
    {
        "Id": 2,
        "Mode": "mixProxy",
        "Socks5Proxy": False,
        "HttpProxy": True,
        "Port": 8080,
    },
    {"Id": 3, "Mode": "tcp", "Port": 9000},
]


def test_list_tunnels_socks5_alias_selects_mixproxy_rows():
    nps = TypeFilteringNPS(MIX_PROXY_ROWS)

    rows = tunnel.list_tunnels(nps, tunnel_type="socks5")

    assert [row["Id"] for row in rows] == [1]
    assert nps.types == ["socks5", "mixProxy"]


def test_list_tunnels_httpproxy_alias_selects_mixproxy_rows():
    nps = TypeFilteringNPS(MIX_PROXY_ROWS)

    rows = tunnel.list_tunnels(nps, tunnel_type="httpProxy")

    assert [row["Id"] for row in rows] == [2]
    assert nps.types == ["httpProxy", "mixProxy"]


def test_list_tunnels_mixproxy_filter_returns_both_proxy_kinds():
    nps = TypeFilteringNPS(MIX_PROXY_ROWS)

    rows = tunnel.list_tunnels(nps, tunnel_type="mixProxy")

    assert [row["Id"] for row in rows] == [1, 2]
    assert nps.types == ["mixProxy"]


def test_list_tunnels_alias_without_flags_matches_either_proxy():
    nps = TypeFilteringNPS([{"Id": 1, "Mode": "mixProxy", "Port": 1080}])

    socks = tunnel.list_tunnels(nps, tunnel_type="socks5")
    http = tunnel.list_tunnels(nps, tunnel_type="httpProxy")

    assert [row["Id"] for row in socks] == [1]
    assert [row["Id"] for row in http] == [1]


class AllRowsNPS(TypeFilteringNPS):
    """Ignore the type filter and return every row."""

    def request(self, path, method="POST", data=None):
        data = data or {}
        self.types.append(data.get("type", ""))
        return {"rows": self.rows, "total": len(self.rows)}


def test_list_tunnels_alias_dedupes_overlapping_queries():
    nps = AllRowsNPS(MIX_PROXY_ROWS)

    rows = tunnel.list_tunnels(nps, tunnel_type="socks5")

    assert [row["Id"] for row in rows] == [1]


def test_list_tunnels_exact_filter_ignores_nonconforming_server():
    nps = AllRowsNPS(MIX_PROXY_ROWS)

    rows = tunnel.list_tunnels(nps, tunnel_type="tcp")

    assert [row["Id"] for row in rows] == [3]


def test_list_tunnels_unfiltered_dedupes_nonconforming_server():
    nps = AllRowsNPS(MIX_PROXY_ROWS)

    rows = tunnel.list_tunnels(nps)

    assert [row["Id"] for row in rows] == [1, 2, 3]


class SlowTypedNPS:
    """Serve one tunnel per type; earlier types answer slowest."""

    is_modern = False

    def __init__(self):
        self.lock = threading.Lock()
        self.active = 0
        self.peak = 0

    def request(self, path, method="POST", data=None):
        tunnel_type = (data or {})["type"]
        index = tunnel.TUNNEL_TYPES.index(tunnel_type)
        with self.lock:
            self.active += 1
            self.peak = max(self.peak, self.active)
        time.sleep(0.01 * (len(tunnel.TUNNEL_TYPES) - index))
        with self.lock:
            self.active -= 1
        return {"rows": [{"Id": index, "Mode": tunnel_type}], "total": 1}


def test_legacy_list_all_tunnels_runs_types_concurrently_in_order():
    nps = SlowTypedNPS()

    rows = tunnel.list_tunnels(nps)

    assert [row["Mode"] for row in rows] == list(tunnel.TUNNEL_TYPES)
    assert 1 < nps.peak <= tunnel.LEGACY_TYPE_WORKERS


class FakeModernNPS:
    """Serve a paginated modern /api/* list endpoint."""

    is_modern = True

    def __init__(self, rows, total=None, page_cap=None):
        self.rows = rows
        self.total = len(rows) if total is None else total
        self.page_cap = page_cap
        self.requests = []
        self.params = []

    def api_request(self, method, path, params=None, data=None):
        params = params or {}
        self.params.append(dict(params))
        offset = int(params.get("offset", 0))
        limit = int(params.get("limit", 100))
        if self.page_cap is not None:
            limit = min(limit, self.page_cap)
        self.requests.append((path, offset, limit))
        return {
            "data": self.rows[offset : offset + limit],
            "meta": {"pagination": {"total": self.total}},
        }


def test_modern_list_hosts_fetches_all_pages():
    nps = FakeModernNPS(_rows(151))

    rows = host.list_hosts(nps)

    assert len(rows) == 151
    assert nps.requests == [("/api/hosts", 0, 100), ("/api/hosts", 100, 100)]


def test_modern_list_clients_fetches_all_pages():
    nps = FakeModernNPS(_rows(250))

    rows = client_mgmt.list_clients(nps)

    assert len(rows) == 250
    assert [request[1] for request in nps.requests] == [0, 100, 200]


def test_modern_list_tunnels_uses_single_endpoint_and_pages():
    nps = FakeModernNPS(_rows(250))

    rows = tunnel.list_tunnels(nps)

    assert len(rows) == 250
    assert nps.requests == [
        ("/api/tunnels", 0, 100),
        ("/api/tunnels", 100, 100),
        ("/api/tunnels", 200, 100),
    ]


def test_modern_list_tunnels_filters_proxy_aliases_locally():
    nps = FakeModernNPS(
        [
            {"id": 1, "mode": "mixProxy", "enable_socks5": True, "enable_http": False},
            {"id": 2, "mode": "mixProxy", "enable_socks5": False, "enable_http": True},
            {"id": 3, "mode": "tcp"},
        ]
    )

    rows = tunnel.list_tunnels(nps, tunnel_type="socks5")

    assert [row["Id"] for row in rows] == [1]
    assert "mode" not in nps.params[0]


def test_modern_list_tunnels_httpproxy_alias_selects_only_http_rows():
    nps = FakeModernNPS(
        [
            {"id": 1, "mode": "mixProxy", "enable_socks5": True, "enable_http": False},
            {"id": 2, "mode": "mixProxy", "enable_socks5": False, "enable_http": True},
        ]
    )

    rows = tunnel.list_tunnels(nps, tunnel_type="httpProxy")

    assert [row["Id"] for row in rows] == [2]


def test_modern_list_tunnels_mixproxy_filters_both_proxy_kinds():
    nps = FakeModernNPS(
        [
            {"id": 1, "mode": "mixProxy", "enable_socks5": True, "enable_http": False},
            {"id": 2, "mode": "mixProxy", "enable_socks5": False, "enable_http": True},
            {"id": 3, "mode": "tcp"},
        ]
    )

    rows = tunnel.list_tunnels(nps, tunnel_type="mixProxy")

    assert [row["Id"] for row in rows] == [1, 2]
    assert "mode" not in nps.params[0]


def test_modern_list_tunnels_alias_without_flags_matches_either():
    nps = FakeModernNPS([{"id": 1, "mode": "mixProxy"}])

    socks = tunnel.list_tunnels(nps, tunnel_type="socks5")
    http = tunnel.list_tunnels(nps, tunnel_type="httpProxy")

    assert [row["Id"] for row in socks] == [1]
    assert [row["Id"] for row in http] == [1]


def test_modern_list_tunnels_sends_mode_for_exact_types():
    nps = FakeModernNPS([{"id": 3, "mode": "tcp"}])

    rows = tunnel.list_tunnels(nps, tunnel_type="tcp")

    assert nps.params[0]["mode"] == "tcp"
    assert [row["Id"] for row in rows] == [3]


def test_modern_list_hosts_paginate_false_single_request():
    nps = FakeModernNPS(_rows(151))

    rows = host.list_hosts(nps, paginate=False)

    assert len(rows) == 100
    assert nps.requests == [("/api/hosts", 0, 100)]


class DataPaginationModernNPS:
    """Serve total/has_more inside data, as some builds do."""

    is_modern = True

    def __init__(self, rows, total=None, page_cap=None):
        self.rows = rows
        self.total = len(rows) if total is None else total
        self.page_cap = page_cap
        self.requests = []

    def api_request(self, method, path, params=None, data=None):
        params = params or {}
        offset = int(params.get("offset", 0))
        limit = int(params.get("limit", 100))
        if self.page_cap is not None:
            limit = min(limit, self.page_cap)
        self.requests.append((path, offset, limit))
        page = self.rows[offset : offset + limit]
        return {
            "data": {
                "items": page,
                "total": self.total,
                "has_more": offset + len(page) < self.total,
            }
        }


def test_modern_list_reads_total_and_has_more_from_data():
    nps = DataPaginationModernNPS(_rows(151))

    rows = host.list_hosts(nps)

    assert len(rows) == 151
    assert nps.requests == [("/api/hosts", 0, 100), ("/api/hosts", 100, 100)]


def test_modern_list_honors_has_more_when_total_is_absent():
    nps = DataPaginationModernNPS(_rows(150), total=0)

    rows = host.list_hosts(nps)

    assert len(rows) == 100
    assert nps.requests == [("/api/hosts", 0, 100)]


class ShortPageHasMoreNPS:
    """Keep paging on has_more even when a page is shorter than the limit."""

    is_modern = True

    def __init__(self):
        self.requests = []

    def api_request(self, method, path, params=None, data=None):
        offset = int((params or {}).get("offset", 0))
        self.requests.append(offset)
        if offset == 0:
            return {"data": {"items": [{"id": 0}], "has_more": True}}
        return {"data": {"items": [{"id": 1}], "has_more": False}}


def test_modern_list_uses_has_more_over_short_page():
    nps = ShortPageHasMoreNPS()

    rows = host.list_hosts(nps)

    assert [row["Id"] for row in rows] == [0, 1]
    assert nps.requests == [0, 1]
