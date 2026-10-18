"""Tests for `nps-ctl tunnel status`."""

from __future__ import annotations

import argparse
import json
import re
from types import SimpleNamespace

import nps_ctl.cli.cmd_tunnels as cmd_tunnels
from nps_ctl.types import EdgeResults

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


def _plain(text: str) -> str:
    return _ANSI_RE.sub("", text)


class TunnelStatusCluster:
    """Cluster stub with one healthy edge and one tunnel-only failure."""

    edge_names = ["edge-a", "edge-b"]

    def __init__(self):
        self.client_calls: list[list[str] | None] = []
        self.tunnel_calls: list[list[str] | None] = []
        self.host_calls: list[list[str] | None] = []

    def get_edge(self, name):
        if name not in self.edge_names:
            return None
        return SimpleNamespace(
            region=f"region-{name}", api_url=f"https://{name}.invalid"
        )

    def _names(self, edge_names):
        return self.edge_names if edge_names is None else edge_names

    def get_all_clients(self, edge_names=None, max_workers=4):
        self.client_calls.append(edge_names)
        names = self._names(edge_names)
        clients = {
            "edge-a": [
                {"Id": 1, "IsConnect": True},
                {"Id": 2, "IsConnect": False},
            ],
            "edge-b": [{"Id": 3, "IsConnect": True}],
        }
        return EdgeResults({name: clients.get(name, []) for name in names})

    def get_all_tunnels(self, edge_names=None, max_workers=4):
        self.tunnel_calls.append(edge_names)
        names = self._names(edge_names)
        tunnels = {
            "edge-a": [
                {"Id": 1, "Port": 8080, "RunStatus": True},
                {"Id": 2, "Port": 8080, "RunStatus": False},
                {"Id": 3, "Port": 9000, "RunStatus": True},
            ]
        }
        return EdgeResults(
            {name: tunnels.get(name, []) for name in names},
            errors={"edge-b": "timeout"},
        )

    def get_all_hosts(self, edge_names=None, max_workers=4):
        self.host_calls.append(edge_names)
        raise AssertionError("tunnel status must not fetch hosts")


class EmptyCluster:
    edge_names: list[str] = []


def _args(**overrides):
    values = {
        "config": "ignored",
        "edge": None,
        "all": False,
        "json": False,
        "no_color": False,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


def test_tunnel_status_renders_healthy_and_partial(monkeypatch, capsys):
    cluster = TunnelStatusCluster()
    monkeypatch.setattr(cmd_tunnels, "NPSCluster", lambda config: cluster)

    code = cmd_tunnels.cmd_tunnel_status(_args())

    out = _plain(capsys.readouterr().out)
    assert code == 1
    assert "NPS Tunnel Status" in out
    assert "✓ Online" in out
    assert "⚠ Partial" in out
    assert "1/2" in out  # edge-a clients online/total
    assert "2/2 edges online" in out
    assert "- tunnels" in out
    assert "edge-b: tunnels: timeout" in out
    assert cluster.host_calls == []


def test_tunnel_status_single_edge_contacts_only_that_edge(monkeypatch, capsys):
    cluster = TunnelStatusCluster()
    monkeypatch.setattr(cmd_tunnels, "NPSCluster", lambda config: cluster)

    code = cmd_tunnels.cmd_tunnel_status(_args(edge="edge-a"))

    capsys.readouterr()
    assert code == 0
    assert cluster.client_calls == [["edge-a"]]
    assert cluster.tunnel_calls == [["edge-a"]]
    assert cluster.host_calls == []


def test_tunnel_status_rejects_edge_and_all(monkeypatch, capsys):
    cluster = TunnelStatusCluster()
    monkeypatch.setattr(cmd_tunnels, "NPSCluster", lambda config: cluster)

    code = cmd_tunnels.cmd_tunnel_status(_args(edge="edge-a", all=True))

    out = _plain(capsys.readouterr().out)
    assert code == 2
    assert "either -e/--edge or -a/--all" in out
    assert cluster.client_calls == []
    assert cluster.tunnel_calls == []


def test_tunnel_status_unknown_edge_exits_one(monkeypatch, capsys):
    cluster = TunnelStatusCluster()
    monkeypatch.setattr(cmd_tunnels, "NPSCluster", lambda config: cluster)

    code = cmd_tunnels.cmd_tunnel_status(_args(edge="missing"))

    out = _plain(capsys.readouterr().out)
    assert code == 1
    assert "Edge 'missing' not found" in out
    assert cluster.client_calls == []
    assert cluster.tunnel_calls == []


def test_tunnel_status_json_includes_host_nulls(monkeypatch, capsys):
    cluster = TunnelStatusCluster()
    monkeypatch.setattr(cmd_tunnels, "NPSCluster", lambda config: cluster)

    code = cmd_tunnels.cmd_tunnel_status(_args(json=True))

    payload = json.loads(capsys.readouterr().out)
    assert code == 1
    assert payload["summary"] == {"configured": 2, "online": 2, "offline": 0}
    assert payload["totals"]["tunnels"] is None
    assert payload["totals"]["hosts"] is None
    assert payload["totals"]["ports"] is None

    healthy = payload["edges"][0]
    assert healthy["tunnels_ok"] is True
    assert healthy["tunnels_total"] == 3
    assert healthy["tunnels_running"] == 2
    assert healthy["tunnel_ports"] == 2
    assert healthy["hosts_ok"] is None
    assert healthy["hosts_total"] is None
    assert healthy["ports"] is None

    partial = payload["edges"][1]
    assert partial["online"] is True
    assert partial["partial"] is True
    assert partial["tunnels_ok"] is False
    assert partial["tunnels_total"] is None
    assert partial["error"] == "tunnels: timeout"


def test_tunnel_status_empty_cluster_json(monkeypatch, capsys):
    monkeypatch.setattr(cmd_tunnels, "NPSCluster", lambda config: EmptyCluster())

    code = cmd_tunnels.cmd_tunnel_status(_args(json=True))

    assert code == 1
    assert json.loads(capsys.readouterr().out) == {"error": "No edges configured"}


def test_tunnel_status_piped_output_has_no_ansi(monkeypatch, capsys):
    cluster = TunnelStatusCluster()
    monkeypatch.setattr(cmd_tunnels, "NPSCluster", lambda config: cluster)

    cmd_tunnels.cmd_tunnel_status(_args())

    assert "\x1b" not in capsys.readouterr().out
