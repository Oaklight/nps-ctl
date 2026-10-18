"""Tests for non-zero CLI exit codes after partial remote failures."""

from __future__ import annotations

import argparse
from types import SimpleNamespace

import pytest

import nps_ctl.cli.cmd_npc as cmd_npc
import nps_ctl.cli.cmd_sync as cmd_sync
from nps_ctl.cluster import NPSCluster


class FakeNPCCluster:
    """Cluster with two clients for status command tests."""

    npc_client_names = ["client-a", "client-b"]

    def get_npc_client(self, name: str):
        return SimpleNamespace(ssh_host=name, ssh_user="root", edges=[])


class FakeSyncCluster:
    """Cluster stub that prints the normal edge summary and returns set results."""

    edge_names = ["source", "target-a", "target-b"]

    def __init__(self, results: dict[str, dict[str, bool]]) -> None:
        self.results = results

    def sync_from(self, _source: str, **kwargs) -> dict[str, dict[str, bool]]:
        NPSCluster._print_sync_summary(
            self, self.results, elapsed_ms=0, quiet=kwargs["quiet"]
        )
        return self.results


def _status_args(parallel: bool) -> argparse.Namespace:
    return argparse.Namespace(config="ignored", client=None, parallel=parallel)


@pytest.mark.parametrize("parallel", [False, True])
def test_client_status_exits_nonzero_when_a_remote_check_fails(
    monkeypatch, capsys, parallel
):
    monkeypatch.setattr(cmd_npc, "NPSCluster", lambda config: FakeNPCCluster())

    def check_status(ssh_host: str, ssh_user: str):
        if ssh_host == "client-b":
            return SimpleNamespace(
                success=False,
                stdout="",
                message="Command failed with exit code 255",
            )
        return SimpleNamespace(
            success=True,
            stdout=(
                "=== NPC Version ===\n1.2.3\n=== Service Status ===\nactive (running)\n"
            ),
            message="",
        )

    monkeypatch.setattr(cmd_npc, "check_npc_status", check_status)

    result = cmd_npc.cmd_npc_status(_status_args(parallel))

    assert result == 1
    output = capsys.readouterr().out
    assert "client-b" in output
    assert "1 ok, 1 failed" in output


@pytest.mark.parametrize("parallel", [False, True])
def test_client_status_exits_zero_when_all_remote_checks_succeed(
    monkeypatch, capsys, parallel
):
    monkeypatch.setattr(cmd_npc, "NPSCluster", lambda config: FakeNPCCluster())
    monkeypatch.setattr(
        cmd_npc,
        "check_npc_status",
        lambda ssh_host, ssh_user: SimpleNamespace(
            success=True,
            stdout=(
                "=== NPC Version ===\n1.2.3\n=== Service Status ===\nactive (running)\n"
            ),
            message="",
        ),
    )

    result = cmd_npc.cmd_npc_status(_status_args(parallel))

    assert result == 0
    assert "2 ok, 0 failed" in capsys.readouterr().out


def _sync_args(parallel: bool = False) -> argparse.Namespace:
    return argparse.Namespace(
        config="ignored",
        proxy=None,
        socks_proxy=None,
        quiet=False,
        source="source",
        type="clients",
        edge=None,
        parallel=parallel,
        workers=2,
        yes=True,
    )


def test_edge_sync_exits_nonzero_and_summarizes_connection_failure(monkeypatch, capsys):
    results = {
        "target-a": {"client:one": True},
        "target-b": {"_edge_failed": False},
    }
    monkeypatch.setattr(
        cmd_sync, "NPSCluster", lambda *args, **kwargs: FakeSyncCluster(results)
    )

    result = cmd_sync.cmd_sync(_sync_args())

    assert result == 1
    output = capsys.readouterr().out
    assert "target-b: connection failed" in output
    assert output.rstrip().endswith("Targets: 1 ok, 1 failed")


def test_edge_sync_exits_nonzero_when_an_operation_fails(monkeypatch, capsys):
    results = {"target-a": {"client:one": False}}
    monkeypatch.setattr(
        cmd_sync, "NPSCluster", lambda *args, **kwargs: FakeSyncCluster(results)
    )

    result = cmd_sync.cmd_sync(_sync_args(parallel=True))

    assert result == 1
    assert "Targets: 0 ok, 1 failed" in capsys.readouterr().out


def test_edge_sync_exits_zero_when_all_targets_succeed(monkeypatch, capsys):
    results = {
        "target-a": {"client:one": True},
        "target-b": {"client:one": True},
    }
    monkeypatch.setattr(
        cmd_sync, "NPSCluster", lambda *args, **kwargs: FakeSyncCluster(results)
    )

    result = cmd_sync.cmd_sync(_sync_args())

    assert result == 0
    assert "Targets: 2 ok, 0 failed" in capsys.readouterr().out
