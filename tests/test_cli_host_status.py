"""Tests for `nps-ctl host status`."""

from __future__ import annotations

import argparse
import json
import re
from types import SimpleNamespace

import nps_ctl.cli.cmd_hosts as cmd_hosts
from nps_ctl.types import EdgeResults

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


def _plain(text: str) -> str:
    return _ANSI_RE.sub("", text)


class StatusCluster:
    """Cluster stub with one healthy and one host-only failure."""

    edge_names = ["edge-a", "edge-b"]

    def __init__(self):
        self.client_calls: list[list[str] | None] = []
        self.host_calls: list[list[str] | None] = []

    def get_edge(self, name):
        return SimpleNamespace(
            region=f"region-{name}", api_url=f"https://{name}.invalid"
        )

    def _names(self, edge_names):
        return self.edge_names if edge_names is None else edge_names

    def get_all_clients(self, edge_names=None, max_workers=4):
        self.client_calls.append(edge_names)
        names = self._names(edge_names)
        clients = {
            "edge-a": [{"Id": 1, "IsConnect": True}, {"Id": 2, "IsConnect": False}],
            "edge-b": [{"Id": 3, "IsConnect": True}],
        }
        return EdgeResults({name: clients.get(name, []) for name in names})

    def get_all_hosts(self, edge_names=None, max_workers=4):
        self.host_calls.append(edge_names)
        names = self._names(edge_names)
        hosts = {
            "edge-a": [
                {"Id": 1, "Target": {"TargetStr": "127.0.0.1:8080"}},
                {"Id": 2, "Target": {"TargetStr": "127.0.0.1:8080,127.0.0.1:9090"}},
            ]
        }
        return EdgeResults(
            {name: hosts.get(name, []) for name in names},
            errors={"edge-b": "timeout"},
        )

    def get_all_tunnels(self, edge_names=None, max_workers=4):
        raise AssertionError("host status must not fetch tunnels")


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


def test_host_status_renders_healthy_and_partial(monkeypatch, capsys):
    cluster = StatusCluster()
    monkeypatch.setattr(cmd_hosts, "NPSCluster", lambda config: cluster)

    code = cmd_hosts.cmd_host_status(_args())

    out = _plain(capsys.readouterr().out)
    assert code == 1
    assert "NPS Host Status" in out
    assert "✓ Online" in out
    assert "⚠ Partial" in out
    assert "1/2" in out  # edge-a clients
    assert "2" in out  # host mappings / ports
    assert (
        "2/2 edges online; clients 2/3 online, - host mappings, - target ports" in out
    )
    assert "edge-b: hosts: timeout" in out


def test_host_status_single_edge_contacts_only_that_edge(monkeypatch, capsys):
    cluster = StatusCluster()
    monkeypatch.setattr(cmd_hosts, "NPSCluster", lambda config: cluster)

    code = cmd_hosts.cmd_host_status(_args(edge="edge-a"))

    capsys.readouterr()
    assert code == 0
    assert cluster.client_calls == [["edge-a"]]
    assert cluster.host_calls == [["edge-a"]]


def test_host_status_rejects_edge_and_all(monkeypatch, capsys):
    cluster = StatusCluster()
    monkeypatch.setattr(cmd_hosts, "NPSCluster", lambda config: cluster)

    code = cmd_hosts.cmd_host_status(_args(edge="edge-a", all=True))

    out = _plain(capsys.readouterr().out)
    assert code == 2
    assert "either -e/--edge or -a/--all" in out
    assert cluster.client_calls == []


def test_host_status_unknown_edge_exits_one(monkeypatch, capsys):
    cluster = StatusCluster()
    monkeypatch.setattr(cmd_hosts, "NPSCluster", lambda config: cluster)

    code = cmd_hosts.cmd_host_status(_args(edge="missing"))

    out = _plain(capsys.readouterr().out)
    assert code == 1
    assert "Edge 'missing' not found" in out
    assert cluster.client_calls == [[]]


def test_host_status_json_uses_shared_payload(monkeypatch, capsys):
    cluster = StatusCluster()
    monkeypatch.setattr(cmd_hosts, "NPSCluster", lambda config: cluster)

    code = cmd_hosts.cmd_host_status(_args(json=True))

    payload = json.loads(capsys.readouterr().out)
    assert code == 1
    assert payload["summary"] == {"configured": 2, "online": 2, "offline": 0}
    assert payload["totals"] == {
        "ok": 1,
        "failed": 0,
        "partial": 1,
        "clients": 3,
        "hosts": None,
        "ports": None,
        "tunnels": None,
        "tunnels_running": None,
        "tunnel_ports": None,
    }
    failed = payload["edges"][1]
    assert failed["edge"] == "edge-b"
    assert failed["partial"] is True
    assert failed["hosts_total"] is None
    assert failed["ports"] is None
    assert failed["tunnels_ok"] is None
    assert failed["tunnels_total"] is None
    assert failed["error"] == "hosts: timeout"
