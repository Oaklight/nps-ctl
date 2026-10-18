"""Tests for non-zero exits on remote failures."""

from __future__ import annotations

import argparse
from types import SimpleNamespace

import nps_ctl.cli.cmd_npc as cmd_npc
import nps_ctl.cli.cmd_sync as cmd_sync


class FakeNPCCluster:
    """NPC cluster stub with optional configured clients."""

    def __init__(self, client_names, missing=()):
        self.npc_client_names = client_names
        self.missing = set(missing)

    def get_npc_client(self, name):
        if name in self.missing:
            return None
        return SimpleNamespace(
            ssh_host=f"{name}.invalid",
            ssh_user="root",
            edges=["nps-america"],
        )


class FakeSyncCluster:
    """Sync cluster stub returning canned per-edge results."""

    edge_names = ["nps-source", "nps-good", "nps-bad"]

    def __init__(self, results):
        self.results = results

    def sync_from(self, source, **kwargs):
        return self.results


def _npc_args(parallel=False):
    return argparse.Namespace(config="ignored", client=None, parallel=parallel)


def _sync_args(**kwargs):
    values = {
        "config": "ignored",
        "source": "nps-source",
        "type": "all",
        "edge": None,
        "yes": True,
        "parallel": False,
        "quiet": True,
        "workers": 4,
    }
    values.update(kwargs)
    return argparse.Namespace(**values)


def _ssh_result(success, message=""):
    return SimpleNamespace(
        success=success,
        stdout="=== NPC Version ===\nv0.26.0\n=== Service Status ===\nrunning\n",
        message=message,
    )


def test_client_status_all_ok_exits_zero(monkeypatch, capsys):
    cluster = FakeNPCCluster(["alpha", "beta"])
    monkeypatch.setattr(cmd_npc, "NPSCluster", lambda config: cluster)
    monkeypatch.setattr(cmd_npc, "check_npc_status", lambda **kwargs: _ssh_result(True))

    assert cmd_npc.cmd_npc_status(_npc_args()) == 0

    assert "ok: 2, failed: 0" in capsys.readouterr().out


def test_client_status_remote_error_exits_nonzero(monkeypatch, capsys):
    cluster = FakeNPCCluster(["alpha", "beta"])
    monkeypatch.setattr(cmd_npc, "NPSCluster", lambda config: cluster)

    def fake_check(ssh_host, ssh_user):
        if ssh_host.startswith("beta"):
            return _ssh_result(False, "Command failed with exit code 255")
        return _ssh_result(True)

    monkeypatch.setattr(cmd_npc, "check_npc_status", fake_check)

    assert cmd_npc.cmd_npc_status(_npc_args()) == 1

    out = capsys.readouterr().out
    assert "ok: 1, failed: 1" in out
    assert "Command failed with exit code 255" in out


def test_client_status_parallel_remote_error_exits_nonzero(monkeypatch, capsys):
    cluster = FakeNPCCluster(["alpha", "beta"])
    monkeypatch.setattr(cmd_npc, "NPSCluster", lambda config: cluster)
    monkeypatch.setattr(
        cmd_npc, "check_npc_status", lambda **kwargs: _ssh_result(False, "timeout")
    )

    assert cmd_npc.cmd_npc_status(_npc_args(parallel=True)) == 1

    assert "ok: 0, failed: 2" in capsys.readouterr().out


def test_client_status_missing_config_exits_nonzero(monkeypatch, capsys):
    cluster = FakeNPCCluster(["alpha"], missing={"alpha"})
    monkeypatch.setattr(cmd_npc, "NPSCluster", lambda config: cluster)

    assert cmd_npc.cmd_npc_status(_npc_args()) == 1

    out = capsys.readouterr().out
    assert "Config Not Found" in out
    assert "ok: 0, failed: 1" in out


def test_edge_sync_all_ok_exits_zero(monkeypatch, capsys):
    cluster = FakeSyncCluster({"nps-good": {"client alpha": True}})
    monkeypatch.setattr(cmd_sync, "NPSCluster", lambda *args, **kwargs: cluster)

    assert cmd_sync.cmd_sync(_sync_args()) == 0

    assert "edges ok: 1, failed: 0" in capsys.readouterr().out


def test_edge_sync_failed_edge_exits_nonzero(monkeypatch, capsys):
    cluster = FakeSyncCluster(
        {
            "nps-good": {"client alpha": True},
            "nps-bad": {"_edge_failed": True},
        }
    )
    monkeypatch.setattr(cmd_sync, "NPSCluster", lambda *args, **kwargs: cluster)

    assert cmd_sync.cmd_sync(_sync_args()) == 1

    assert "edges ok: 1, failed: 1" in capsys.readouterr().out


def test_edge_sync_failed_operation_exits_nonzero(monkeypatch, capsys):
    cluster = FakeSyncCluster(
        {
            "nps-good": {"client alpha": True},
            "nps-bad": {"client alpha": False},
        }
    )
    monkeypatch.setattr(cmd_sync, "NPSCluster", lambda *args, **kwargs: cluster)

    assert cmd_sync.cmd_sync(_sync_args()) == 1

    assert "edges ok: 1, failed: 1" in capsys.readouterr().out
