"""Tests for tunnel type filters, including the mixProxy alias."""

from __future__ import annotations

import argparse
from types import SimpleNamespace

import nps_ctl.cli.cmd_tunnels as cmd_tunnels
from nps_ctl import tunnel as tunnel_module
from nps_ctl.types import EdgeResults

ROWS = [
    {
        "Id": 1,
        "Mode": "mixProxy",
        "Socks5Proxy": True,
        "HttpProxy": False,
        "Port": 1080,
        "Remark": "socks",
    },
    {
        "Id": 2,
        "Mode": "mixProxy",
        "Socks5Proxy": False,
        "HttpProxy": True,
        "Port": 8080,
        "Remark": "http",
    },
    {"Id": 3, "Mode": "tcp", "Port": 9000, "Remark": "tcp"},
]


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


def test_find_tunnels_matches_socks5_alias_by_port():
    found = cmd_tunnels._find_tunnels(
        TypeFilteringNPS(ROWS), port=1080, tunnel_type="socks5"
    )

    assert [tunnel["Id"] for tunnel in found] == [1]


def test_find_tunnels_matches_httpproxy_alias_by_port():
    found = cmd_tunnels._find_tunnels(
        TypeFilteringNPS(ROWS), port=8080, tunnel_type="httpProxy"
    )

    assert [tunnel["Id"] for tunnel in found] == [2]


def test_find_tunnels_mixproxy_matches_both_proxy_kinds():
    socks = cmd_tunnels._find_tunnels(
        TypeFilteringNPS(ROWS), port=1080, tunnel_type="mixProxy"
    )
    http = cmd_tunnels._find_tunnels(
        TypeFilteringNPS(ROWS), port=8080, tunnel_type="mixProxy"
    )

    assert [tunnel["Id"] for tunnel in socks] == [1]
    assert [tunnel["Id"] for tunnel in http] == [2]


def test_find_tunnels_matches_a_port_inside_a_range():
    rows = [
        {
            "Id": 9,
            "Mode": "mixProxy",
            "Socks5Proxy": True,
            "HttpProxy": False,
            "Port": 0,
            "Ports": "9000-9002",
        }
    ]

    found = cmd_tunnels._find_tunnels(
        TypeFilteringNPS(rows), port=9001, tunnel_type="socks5"
    )

    assert [tunnel["Id"] for tunnel in found] == [9]


def test_find_tunnels_rejects_wrong_type_for_a_port():
    found = cmd_tunnels._find_tunnels(
        TypeFilteringNPS(ROWS), port=8080, tunnel_type="socks5"
    )

    assert found == []


def test_apply_tunnel_edit_preserves_proxy_flags(monkeypatch):
    calls = []

    def fake_edit(nps, **kwargs):
        calls.append(kwargs)
        return True

    monkeypatch.setattr(tunnel_module, "edit_tunnel", fake_edit)
    current = {
        "Mode": "mixProxy",
        "Port": 1080,
        "Remark": "socks",
        "Target": {"TargetStr": "10.0.0.9:1090"},
        "Client": {"Id": 5},
        "Socks5Proxy": True,
        "HttpProxy": False,
    }

    assert cmd_tunnels._apply_tunnel_edit(
        None, 1, current, new_target="10.0.0.10:1090", new_port=None, new_remark=None
    )

    assert calls[0]["enable_socks5"] is True
    assert calls[0]["enable_http"] is False


def test_apply_tunnel_edit_omits_flags_for_tcp(monkeypatch):
    calls = []

    def fake_edit(nps, **kwargs):
        calls.append(kwargs)
        return True

    monkeypatch.setattr(tunnel_module, "edit_tunnel", fake_edit)
    current = {
        "Mode": "tcp",
        "Port": 9000,
        "Remark": "web",
        "Target": {"TargetStr": "127.0.0.1:80"},
        "Client": {"Id": 5},
        "Socks5Proxy": False,
        "HttpProxy": False,
    }

    assert cmd_tunnels._apply_tunnel_edit(
        None, 2, current, new_target=None, new_port=None, new_remark="web2"
    )

    assert calls[0]["enable_socks5"] is None
    assert calls[0]["enable_http"] is None


def test_edit_tunnel_v1_sends_proxy_flags():
    class RecordingNPS:
        is_modern = False

        def __init__(self):
            self.data = None

        def request(self, path, method="POST", data=None):
            self.data = data
            return {"status": 1}

    nps = RecordingNPS()

    assert tunnel_module.edit_tunnel(
        nps,
        tunnel_id=1,
        client_id=5,
        tunnel_type="mixProxy",
        port=1080,
        target="10.0.0.9:1090",
        enable_socks5=True,
        enable_http=False,
    )
    assert nps.data is not None
    assert nps.data["enable_socks5"] is True
    assert nps.data["enable_http"] is False


class ClusterStub:
    """Cluster stub for the all-edges list path."""

    edge_names = ["edge-a"]

    def __init__(self):
        self.type_calls: list[str] = []

    def get_edge(self, name):
        return SimpleNamespace(region="region-a")

    def get_all_tunnels(self, tunnel_type="", **kwargs):
        self.type_calls.append(tunnel_type)
        return EdgeResults({"edge-a": ROWS})


def _args(**overrides):
    values = {
        "config": "ignored",
        "edge": None,
        "all": False,
        "type": "",
        "json": False,
        "no_color": False,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


def test_tunnel_list_passes_type_filter_to_all_edges(monkeypatch, capsys):
    cluster = ClusterStub()
    monkeypatch.setattr(cmd_tunnels, "NPSCluster", lambda config: cluster)

    code = cmd_tunnels.cmd_tunnels(_args(all=True, type="socks5", json=True))

    assert code == 0
    assert cluster.type_calls == ["socks5"]
    assert '"edge": "edge-a"' in capsys.readouterr().out
