"""Tests for CLI edge listing and partial-failure output."""

from __future__ import annotations

import argparse
import json
import re
from types import SimpleNamespace

import nps_ctl.cli.cmd_hosts as cmd_hosts
import nps_ctl.cli.cmd_status as cmd_status
from nps_ctl.cli import _dispatch_client_list
from nps_ctl.cli.cmd_status import cmd_edge_list
from nps_ctl.cli.helpers import build_edge_results_payload
from nps_ctl.types import EdgeResults, HostInfo

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


def _plain(text: str) -> str:
    """Remove ANSI escapes from captured output."""
    return _ANSI_RE.sub("", text)


EDGES_TOML = """[[edges]]
name = "nps-america"
api_url = "https://nps-america.invalid"
auth_key = "key"
region = "北美"
ssh_host = "cloud.usa1"

[[edges]]
name = "nps-america2"
api_url = "https://nps-america2.invalid"
auth_key = "key"
region = "北美"
ssh_host = "cloud.usa4"
"""


def test_edge_list_is_offline_and_shows_duplicate_region_edges(tmp_path, capsys):
    config = tmp_path / "edges.toml"
    config.write_text(EDGES_TOML, encoding="utf-8")

    assert cmd_edge_list(argparse.Namespace(config=str(config))) == 0

    out = _plain(capsys.readouterr().out)
    assert "nps-america2" in out
    assert "2 edges configured" in out


class FakeCluster:
    """Cluster stub with one healthy and one failing edge."""

    edge_names = ["nps-america", "nps-america2"]

    def get_edge(self, name):
        return SimpleNamespace(region="北美")

    def get_client(self, name):
        return None

    def get_all_hosts(self):
        hosts: list[HostInfo] = [{"Id": 1, "Host": "example.test"}]
        return EdgeResults(
            {"nps-america": hosts, "nps-america2": []},
            errors={"nps-america2": "connection refused"},
        )


def test_host_list_reports_failed_edge_and_exits_nonzero(monkeypatch, capsys):
    monkeypatch.setattr(cmd_hosts, "NPSCluster", lambda config: FakeCluster())

    code = cmd_hosts.cmd_hosts(
        argparse.Namespace(config="ignored", edge=None, all=False)
    )

    assert code == 1
    out = _plain(capsys.readouterr().out)
    assert "nps-america2" in out
    assert "connection refused" in out
    assert "2 edges: 1 ok, 1 failed" in out


def test_host_del_id_with_all_is_rejected(monkeypatch):
    monkeypatch.setattr(
        cmd_hosts,
        "NPSCluster",
        lambda config: SimpleNamespace(edge_names=["nps-america"]),
    )
    args = argparse.Namespace(
        config="ignored",
        id=1,
        domain=None,
        remark=None,
        edge="nps-america",
        all=True,
        yes=True,
    )

    assert cmd_hosts.cmd_host_del(args) == 2


def test_host_del_id_without_edge_is_rejected(monkeypatch):
    monkeypatch.setattr(
        cmd_hosts,
        "NPSCluster",
        lambda config: SimpleNamespace(edge_names=["nps-america"]),
    )
    args = argparse.Namespace(
        config="ignored",
        id=1,
        domain=None,
        remark=None,
        edge=None,
        all=False,
        yes=True,
    )

    assert cmd_hosts.cmd_host_del(args) == 2


def test_host_list_rejects_edge_and_all(monkeypatch):
    monkeypatch.setattr(cmd_hosts, "NPSCluster", lambda config: FakeCluster())

    code = cmd_hosts.cmd_hosts(
        argparse.Namespace(config="ignored", edge="nps-america", all=True)
    )

    assert code == 2


class FakeStatusCluster:
    """Cluster stub for edge status tests."""

    def __init__(self, edge_names, failing=(), host_failing=()):
        self.edge_names = edge_names
        self.failing = set(failing)
        self.host_failing = set(host_failing)

    def get_edge(self, name):
        return SimpleNamespace(region="region", api_url="https://example.invalid")

    def _names(self, edge_names):
        return self.edge_names if edge_names is None else edge_names

    def get_all_clients(self, edge_names=None, max_workers=4):
        names = self._names(edge_names)
        errors = {name: "connection refused" for name in names if name in self.failing}
        return EdgeResults(
            {
                name: (
                    [{"Id": 1, "IsConnect": True}] if name not in self.failing else []
                )
                for name in names
            },
            errors=errors,
        )

    def get_all_hosts(self, edge_names=None, max_workers=4):
        names = self._names(edge_names)
        errors = {
            name: "timeout" if name in self.host_failing else "connection refused"
            for name in names
            if name in self.failing or name in self.host_failing
        }
        failed = set(errors)
        return EdgeResults(
            {
                name: [{"Target": {"TargetStr": "example.test:8080"}}]
                if name not in failed
                else []
                for name in names
            },
            errors=errors,
        )


def test_edge_status_exits_zero_when_all_online(monkeypatch):
    monkeypatch.setattr(
        cmd_status, "NPSCluster", lambda config: FakeStatusCluster(["a", "b"])
    )

    assert cmd_status.cmd_status(argparse.Namespace(config="ignored")) == 0


def test_edge_status_exits_nonzero_when_an_edge_is_offline(monkeypatch):
    cluster = FakeStatusCluster(["a", "b"], failing={"b"})
    monkeypatch.setattr(cmd_status, "NPSCluster", lambda config: cluster)

    assert cmd_status.cmd_status(argparse.Namespace(config="ignored")) == 1


def test_edge_status_exits_nonzero_on_host_only_failure(monkeypatch):
    cluster = FakeStatusCluster(["a", "b"], host_failing={"b"})
    monkeypatch.setattr(cmd_status, "NPSCluster", lambda config: cluster)

    assert cmd_status.cmd_status(argparse.Namespace(config="ignored")) == 1


def test_edge_status_exits_nonzero_with_no_edges(monkeypatch):
    monkeypatch.setattr(cmd_status, "NPSCluster", lambda config: FakeStatusCluster([]))

    assert cmd_status.cmd_status(argparse.Namespace(config="ignored")) == 1


def test_edge_list_json(tmp_path, capsys):
    config = tmp_path / "edges.toml"
    config.write_text(EDGES_TOML, encoding="utf-8")

    assert cmd_edge_list(argparse.Namespace(config=str(config), json=True)) == 0

    payload = json.loads(capsys.readouterr().out)
    assert [edge["edge"] for edge in payload["edges"]] == [
        "nps-america",
        "nps-america2",
    ]
    assert payload["summary"] == {"configured": 2}


def test_host_list_json_reports_partial_failure(monkeypatch, capsys):
    monkeypatch.setattr(cmd_hosts, "NPSCluster", lambda config: FakeCluster())

    code = cmd_hosts.cmd_hosts(
        argparse.Namespace(config="ignored", edge=None, all=False, json=True)
    )

    assert code == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["summary"] == {"configured": 2, "ok": 1, "failed": 1}
    failed = [edge for edge in payload["edges"] if not edge["ok"]]
    assert failed == [
        {
            "edge": "nps-america2",
            "region": "北美",
            "ok": False,
            "error": "connection refused",
            "items": [],
        }
    ]


def test_edge_status_json(monkeypatch, capsys):
    cluster = FakeStatusCluster(["a", "b"], failing={"b"})
    monkeypatch.setattr(cmd_status, "NPSCluster", lambda config: cluster)

    code = cmd_status.cmd_status(argparse.Namespace(config="ignored", json=True))

    assert code == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["summary"] == {"configured": 2, "online": 1, "offline": 1}
    assert [edge["online"] for edge in payload["edges"]] == [True, False]
    assert payload["edges"][0]["clients_total"] == 1
    assert payload["edges"][0]["hosts_total"] == 1
    assert payload["edges"][0]["ports"] == 1
    assert payload["edges"][1]["clients_total"] is None
    assert payload["edges"][1]["hosts_total"] is None
    assert payload["edges"][1]["error"].startswith("clients: ")
    assert payload["totals"] == {
        "ok": 1,
        "failed": 1,
        "partial": 0,
        "clients": 1,
        "hosts": 1,
        "ports": 1,
    }


def test_piped_table_has_no_ansi(monkeypatch, capsys):
    monkeypatch.setattr(cmd_hosts, "NPSCluster", lambda config: FakeCluster())

    code = cmd_hosts.cmd_hosts(
        argparse.Namespace(config="ignored", edge=None, all=False)
    )

    assert code == 1
    assert "\x1b" not in capsys.readouterr().out


def test_long_host_name_is_not_truncated(monkeypatch, capsys):
    class LongHostCluster(FakeCluster):
        def get_all_hosts(self):
            hosts: list[HostInfo] = [
                {
                    "Id": 1,
                    "Host": "monitor.service.oaklight.cn",
                    "Target": {"TargetStr": ":18092"},
                    "Client": {"Remark": "homelab.tempest"},
                }
            ]
            return EdgeResults({"nps-america": hosts}, errors={})

    monkeypatch.setattr(cmd_hosts, "NPSCluster", lambda config: LongHostCluster())

    code = cmd_hosts.cmd_hosts(
        argparse.Namespace(config="ignored", edge=None, all=False)
    )

    assert code == 0
    assert "monitor.service.oaklight.cn" in _plain(capsys.readouterr().out)


def test_single_edge_json_reports_cluster_total(monkeypatch, capsys):
    class SingleEdgeCluster(FakeCluster):
        def get_client(self, name):
            return SimpleNamespace(name=name)

    monkeypatch.setattr(cmd_hosts, "NPSCluster", lambda config: SingleEdgeCluster())
    monkeypatch.setattr(
        cmd_hosts.host,
        "list_hosts",
        lambda nps: [{"Id": 1, "Host": "example.test"}],
    )

    code = cmd_hosts.cmd_hosts(
        argparse.Namespace(config="ignored", edge="nps-america", all=False, json=True)
    )

    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["summary"] == {"configured": 2, "ok": 1, "failed": 0}
    assert len(payload["edges"]) == 1


def test_payload_configured_override():
    payload = build_edge_results_payload(
        {"nps-america": []}, {}, lambda name: "北美", configured=4
    )

    assert payload["summary"] == {"configured": 4, "ok": 1, "failed": 0}


def test_client_list_json_rejected_with_update():
    args = argparse.Namespace(update=True, dry_run=False, edge="nps-america", json=True)

    assert _dispatch_client_list(args) == 2


def test_empty_cluster_json_exits_nonzero(monkeypatch, capsys):
    class EmptyCluster(FakeCluster):
        edge_names = []

    monkeypatch.setattr(cmd_hosts, "NPSCluster", lambda config: EmptyCluster())

    code = cmd_hosts.cmd_hosts(
        argparse.Namespace(config="ignored", edge=None, all=False, json=True)
    )

    assert code == 1
    assert json.loads(capsys.readouterr().out) == {"error": "No edges configured"}


def test_overwide_url_is_not_cropped(tmp_path, capsys):
    long_url = "https://" + ("a" * 280) + ".invalid"
    config = tmp_path / "edges.toml"
    config.write_text(
        f'[[edges]]\nname = "nps-long"\napi_url = "{long_url}"\n'
        'auth_key = "k"\nregion = "r"\nssh_host = "h"\n',
        encoding="utf-8",
    )

    assert cmd_edge_list(argparse.Namespace(config=str(config))) == 0
    assert long_url in capsys.readouterr().out
