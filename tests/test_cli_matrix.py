"""Tests for the host matrix view."""

from __future__ import annotations

import argparse
import json
import re
from types import SimpleNamespace

import nps_ctl.cli.cmd_hosts as cmd_hosts
from nps_ctl.types import EdgeResults, HostInfo

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


def _plain(text: str) -> str:
    """Remove ANSI escapes from captured output."""
    return _ANSI_RE.sub("", text)


def _host(host_id: int, domain: str) -> HostInfo:
    return {"Id": host_id, "Host": domain}


class MatrixCluster:
    """Cluster stub with configurable host results."""

    edge_names = ["edge-a", "edge-b", "edge-c"]

    def __init__(self, results=None, errors=None):
        self._results = results or {
            "edge-a": [_host(1, "alpha.test"), _host(2, "beta.test")],
            "edge-b": [_host(1, "alpha.test")],
            "edge-c": [],
        }
        self._errors = errors or {}

    def get_edge(self, name):
        return SimpleNamespace(region="region")

    def get_client(self, name):
        return SimpleNamespace(name=name)

    def get_all_hosts(self):
        return EdgeResults(self._results, errors=self._errors)


def _args(**kwargs) -> argparse.Namespace:
    values = {
        "config": "ignored",
        "edge": None,
        "all": False,
        "json": False,
        "matrix": True,
    }
    values.update(kwargs)
    return argparse.Namespace(**values)


def test_matrix_table_marks_presence_and_absence(monkeypatch, capsys):
    monkeypatch.setattr(cmd_hosts, "NPSCluster", lambda config: MatrixCluster())

    assert cmd_hosts.cmd_hosts(_args()) == 0

    out = _plain(capsys.readouterr().out)
    assert out.index("alpha.test") < out.index("beta.test")
    assert out.count("✓") == 3
    assert "domains: 2, edges: 3, failed: 0" in out


def test_matrix_json_reports_presence(monkeypatch, capsys):
    monkeypatch.setattr(cmd_hosts, "NPSCluster", lambda config: MatrixCluster())

    assert cmd_hosts.cmd_hosts(_args(json=True)) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["summary"] == {"domains": 2, "edges": 3, "failed_edges": 0}
    rows = {row["host"]: row["edges"] for row in payload["domains"]}
    assert rows["alpha.test"] == {
        "edge-a": True,
        "edge-b": True,
        "edge-c": False,
    }
    assert rows["beta.test"] == {
        "edge-a": True,
        "edge-b": False,
        "edge-c": False,
    }


def test_matrix_marks_failed_edge_as_null(monkeypatch, capsys):
    cluster = MatrixCluster(
        results={
            "edge-a": [_host(1, "alpha.test")],
            "edge-b": [],
            "edge-c": [_host(1, "alpha.test")],
        },
        errors={"edge-b": "timeout"},
    )
    monkeypatch.setattr(cmd_hosts, "NPSCluster", lambda config: cluster)

    assert cmd_hosts.cmd_hosts(_args(json=True)) == 1

    payload = json.loads(capsys.readouterr().out)
    assert payload["summary"] == {"domains": 1, "edges": 3, "failed_edges": 1}
    assert payload["domains"][0]["edges"]["edge-b"] is None


def test_matrix_table_marks_failed_edge(monkeypatch, capsys):
    cluster = MatrixCluster(
        results={
            "edge-a": [_host(1, "alpha.test")],
            "edge-b": [],
            "edge-c": [_host(1, "alpha.test")],
        },
        errors={"edge-b": "timeout"},
    )
    monkeypatch.setattr(cmd_hosts, "NPSCluster", lambda config: cluster)

    assert cmd_hosts.cmd_hosts(_args()) == 1

    out = _plain(capsys.readouterr().out)
    assert "!" in out
    assert "failed: 1" in out
    assert "timeout" in out
    assert "edge-b!" in out


def test_matrix_single_edge(monkeypatch, capsys):
    monkeypatch.setattr(cmd_hosts, "NPSCluster", lambda config: MatrixCluster())
    monkeypatch.setattr(
        cmd_hosts.host,
        "list_hosts",
        lambda nps: [_host(1, "alpha.test")],
    )

    assert cmd_hosts.cmd_hosts(_args(edge="edge-a", json=True)) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["summary"] == {"domains": 1, "edges": 1, "failed_edges": 0}
    assert payload["domains"][0]["edges"] == {"edge-a": True}
