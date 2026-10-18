"""Tests for CLI edge listing and partial-failure output."""

from __future__ import annotations

import argparse
import re
from types import SimpleNamespace

import nps_ctl.cli.cmd_hosts as cmd_hosts
import nps_ctl.cli.cmd_status as cmd_status
from nps_ctl.cli.cmd_status import cmd_edge_list
from nps_ctl.exceptions import NPSError
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

    def __init__(self, edge_names, failing=()):
        self.edge_names = edge_names
        self.failing = set(failing)

    def get_edge(self, name):
        return SimpleNamespace(region="region", api_url="https://example.invalid")

    def get_client(self, name):
        return SimpleNamespace(name=name)


def test_edge_status_exits_zero_when_all_online(monkeypatch):
    cluster = FakeStatusCluster(["a", "b"])
    monkeypatch.setattr(cmd_status, "NPSCluster", lambda config: cluster)
    monkeypatch.setattr(cmd_status.client_mgmt, "list_clients", lambda nps, limit=1: [])

    assert cmd_status.cmd_status(argparse.Namespace(config="ignored")) == 0


def test_edge_status_exits_nonzero_when_an_edge_is_offline(monkeypatch):
    cluster = FakeStatusCluster(["a", "b"], failing={"b"})

    def fake_list(nps, limit=1):
        if nps.name in cluster.failing:
            raise NPSError("connection refused")
        return []

    monkeypatch.setattr(cmd_status, "NPSCluster", lambda config: cluster)
    monkeypatch.setattr(cmd_status.client_mgmt, "list_clients", fake_list)

    assert cmd_status.cmd_status(argparse.Namespace(config="ignored")) == 1


def test_edge_status_exits_nonzero_with_no_edges(monkeypatch):
    monkeypatch.setattr(cmd_status, "NPSCluster", lambda config: FakeStatusCluster([]))

    assert cmd_status.cmd_status(argparse.Namespace(config="ignored")) == 1
