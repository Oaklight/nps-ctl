"""Tests for finding and removing host mappings left by an interrupted run."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

import nps_ctl.cli.cmd_check as cmd_check
from nps_ctl import host
from nps_ctl.check.leftovers import Leftover, find_leftovers, remove_leftovers
from nps_ctl.check.session import DOMAIN_SUFFIX, REMARK
from nps_ctl.cli.parser import create_parser

EDGE = "edge-a"
DOMAIN = "nps-ctl-check-abcd1234" + DOMAIN_SUFFIX


class FakeCluster:
    edge_names = ["edge-a", "edge-b"]
    npc_client_names: list[str] = []

    def __init__(self, with_api=("edge-a", "edge-b")):
        self.with_api = set(with_api)

    def get_client(self, edge):
        return SimpleNamespace(edge=edge) if edge in self.with_api else None


def _parse(*argv):
    return create_parser().parse_args(["--config", "c.toml", *argv])


@pytest.fixture
def nps_world(monkeypatch):
    state = {"rows": {}, "deleted": []}

    def list_hosts(nps, search="", **kwargs):
        return [dict(row) for row in state["rows"].get(nps.edge, [])]

    def del_host(nps, host_id):
        state["deleted"].append((nps.edge, host_id))
        state["rows"][nps.edge] = [
            row for row in state["rows"].get(nps.edge, []) if row["Id"] != host_id
        ]
        return True

    monkeypatch.setattr(host, "list_hosts", list_hosts)
    monkeypatch.setattr(host, "del_host", del_host)
    return state


def _row(host_id=11, domain=DOMAIN, remark=REMARK, target="127.0.0.1:4321"):
    return {
        "Id": host_id,
        "Host": domain,
        "Remark": remark,
        "Target": {"TargetStr": target},
    }


def test_find_leftovers_returns_only_ephemeral_mappings(nps_world):
    nps_world["rows"]["edge-a"] = [
        _row(11),
        _row(12, remark="a real site", domain="app.example.test"),
        _row(13, domain="other.test"),
    ]

    found = find_leftovers(FakeCluster(), ["edge-a"])

    assert [item.host_id for item in found] == [11]
    assert found[0].target == "127.0.0.1:4321"
    assert found[0].to_dict()["edge"] == "edge-a"


def test_find_leftovers_scans_every_requested_edge(nps_world):
    nps_world["rows"]["edge-a"] = [_row(11)]
    nps_world["rows"]["edge-b"] = [_row(21)]

    found = find_leftovers(FakeCluster(), ["edge-a", "edge-b"])

    assert [(item.edge, item.host_id) for item in found] == [
        ("edge-a", 11),
        ("edge-b", 21),
    ]


def test_find_leftovers_skips_an_edge_with_no_api_client(nps_world):
    nps_world["rows"]["edge-b"] = [_row(21)]

    assert find_leftovers(FakeCluster(with_api=("edge-a",)), ["edge-b"]) == []


def test_find_leftovers_tolerates_a_row_without_a_target(nps_world):
    row = _row(11)
    del row["Target"]
    nps_world["rows"]["edge-a"] = [row]

    (found,) = find_leftovers(FakeCluster(), ["edge-a"])

    assert found.target == ""


def test_remove_leftovers_deletes_and_confirms(nps_world):
    nps_world["rows"]["edge-a"] = [_row(11)]
    leftover = Leftover("edge-a", 11, DOMAIN, "127.0.0.1:4321")

    assert remove_leftovers(FakeCluster(), [leftover]) == []
    assert nps_world["deleted"] == [("edge-a", 11)]
    assert nps_world["rows"]["edge-a"] == []


def test_remove_leftovers_collects_failures_and_keeps_going(nps_world, monkeypatch):
    nps_world["rows"]["edge-a"] = [_row(11), _row(12)]

    def del_host(nps, host_id):
        if host_id == 11:
            raise RuntimeError("edge unreachable")
        nps_world["rows"][nps.edge] = [
            row for row in nps_world["rows"][nps.edge] if row["Id"] != host_id
        ]
        return True

    monkeypatch.setattr(host, "del_host", del_host)
    leftovers = [Leftover("edge-a", 11, DOMAIN, ""), Leftover("edge-a", 12, DOMAIN, "")]

    failures = remove_leftovers(FakeCluster(), leftovers)

    assert [item.host_id for item, _ in failures] == [11]
    assert "edge unreachable" in failures[0][1]
    assert [row["Id"] for row in nps_world["rows"]["edge-a"]] == [11]


# --- CLI ---


@pytest.fixture
def cli_env(monkeypatch):
    cluster = FakeCluster()
    monkeypatch.setattr(cmd_check, "NPSCluster", lambda config: cluster)
    state = {"found": [], "failures": []}
    monkeypatch.setattr(
        cmd_check, "find_leftovers", lambda c, edges: list(state["found"])
    )
    monkeypatch.setattr(
        cmd_check, "remove_leftovers", lambda c, items: list(state["failures"])
    )
    return state


def test_leftovers_clean_exits_zero(cli_env, capsys):
    code = cmd_check.cmd_check_leftovers(_parse("check", "leftovers", "--json"))

    assert code == 0
    assert json.loads(capsys.readouterr().out)["summary"]["found"] == 0


def test_leftovers_found_exits_one_and_lists_them(cli_env, capsys):
    cli_env["found"] = [Leftover("edge-a", 11, DOMAIN, "127.0.0.1:4321")]

    code = cmd_check.cmd_check_leftovers(_parse("check", "leftovers", "--json"))

    payload = json.loads(capsys.readouterr().out)
    assert code == 1
    assert payload["leftovers"][0]["domain"] == DOMAIN
    assert payload["summary"]["removed"] == 0


def test_leftovers_delete_needs_an_explicit_target(cli_env, capsys):
    code = cmd_check.cmd_check_leftovers(
        _parse("check", "leftovers", "--delete", "--json")
    )

    assert code == 2
    assert "-e/--edge" in json.loads(capsys.readouterr().out)["error"]


def test_leftovers_delete_all_removes_them(cli_env, capsys):
    cli_env["found"] = [Leftover("edge-a", 11, DOMAIN, "")]

    code = cmd_check.cmd_check_leftovers(
        _parse("check", "leftovers", "--delete", "-a", "-y", "--json")
    )

    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["summary"]["removed"] == 1


def test_leftovers_json_delete_refuses_without_yes(cli_env, capsys):
    cli_env["found"] = [Leftover("edge-a", 11, DOMAIN, "")]

    code = cmd_check.cmd_check_leftovers(
        _parse("check", "leftovers", "--delete", "-a", "--json")
    )

    assert code == 2
    assert "pass -y" in json.loads(capsys.readouterr().out)["error"]


def test_leftovers_delete_failure_exits_one(cli_env, capsys):
    leftover = Leftover("edge-a", 11, DOMAIN, "")
    cli_env["found"] = [leftover]
    cli_env["failures"] = [(leftover, "edge refuses")]

    code = cmd_check.cmd_check_leftovers(
        _parse("check", "leftovers", "--delete", "-a", "-y", "--json")
    )

    payload = json.loads(capsys.readouterr().out)
    assert code == 1
    assert payload["failures"][0]["error"] == "edge refuses"
    assert payload["summary"]["removed"] == 0


def test_leftovers_rejects_both_edge_and_all(cli_env, capsys):
    code = cmd_check.cmd_check_leftovers(
        _parse("check", "leftovers", "-e", "edge-a", "-a", "--json")
    )

    assert code == 2


def test_leftovers_rejects_an_unknown_edge(cli_env, capsys):
    code = cmd_check.cmd_check_leftovers(
        _parse("check", "leftovers", "-e", "ghost", "--json")
    )

    assert code == 2
    assert "ghost" in json.loads(capsys.readouterr().out)["error"]


def test_leftovers_declined_confirmation_aborts(cli_env, monkeypatch, capsys):
    cli_env["found"] = [Leftover("edge-a", 11, DOMAIN, "")]
    monkeypatch.setattr("builtins.input", lambda: "n")

    code = cmd_check.cmd_check_leftovers(
        _parse("check", "leftovers", "--delete", "-a", "--no-color")
    )

    assert code == 0
    assert "Aborted" in capsys.readouterr().out
