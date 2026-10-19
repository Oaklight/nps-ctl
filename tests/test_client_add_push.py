"""Tests for `client add --push`."""

from __future__ import annotations

import tomllib
from types import SimpleNamespace

from nps_ctl.cli import cmd_npc

EDGES = """[[edges]]
name = "edge-a"
api_url = "https://a.invalid"

[[edges]]
name = "edge-b"
api_url = "https://b.invalid"
"""


def _args(path, **overrides):
    values = {
        "config": str(path),
        "name": "cloud.new",
        "ssh_host": "cloud.new",
        "edges": ["edge-a", "edge-b"],
        "vkey": "vkey-new",
        "conn_type": "tls",
        "push": False,
        "yes": True,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _setup(tmp_path, monkeypatch):
    path = tmp_path / "edges.toml"
    path.write_text(EDGES, encoding="utf-8")
    calls = []

    def fake_push(args, cluster):
        calls.append((args, cluster.get_npc_client(args.client)))
        return len(calls) - 1 if args.client == "cloud.fail" else 0

    monkeypatch.setattr(cmd_npc, "handle_client_push", fake_push)
    return path, calls


def test_client_add_without_push_only_writes_config(tmp_path, monkeypatch):
    path, calls = _setup(tmp_path, monkeypatch)

    assert cmd_npc.cmd_client_add(_args(path)) == 0

    clients = tomllib.loads((tmp_path / "clients.toml").read_text())["clients"]
    assert [c["name"] for c in clients] == ["cloud.new"]
    assert calls == []


def test_client_add_push_pushes_only_the_new_client(tmp_path, monkeypatch):
    path, calls = _setup(tmp_path, monkeypatch)

    assert cmd_npc.cmd_client_add(_args(path, push=True)) == 0

    [(push_args, npc)] = calls
    assert push_args.client == "cloud.new"
    assert push_args.edge is None
    assert push_args.dry_run is False
    assert push_args.yes is True  # add was confirmed; no second prompt
    # The reloaded cluster sees the entry just written to clients.toml.
    assert npc is not None
    assert npc.vkey == "vkey-new"
    assert npc.edges == ["edge-a", "edge-b"]


def test_client_add_push_exits_nonzero_on_failed_push(tmp_path, monkeypatch):
    path, calls = _setup(tmp_path, monkeypatch)
    calls.append(None)  # make fake_push report one failure

    assert cmd_npc.cmd_client_add(_args(path, name="cloud.fail", push=True)) == 1


class PushNPS:
    """Legacy edge that lists given clients and records adds."""

    is_modern = False

    def __init__(self, clients):
        self.clients = clients
        self.added = []

    def request(self, path, method="POST", data=None):
        if path == "/client/list":
            return {"rows": self.clients, "total": len(self.clients)}
        if path == "/client/add":
            self.added.append(data)
            return {"status": 1}
        return {}


def _push_cluster(npc, nps):
    from types import SimpleNamespace

    return SimpleNamespace(
        get_npc_client=lambda name: npc if name == npc.name else None,
        npc_client_names=[npc.name],
        edge_names=["edge-a"],
        get_client=lambda name: nps,
    )


def _push_args(name):
    return SimpleNamespace(
        client=name, edge=None, dry_run=False, update=False, yes=True
    )


def test_push_matches_existing_client_by_vkey():
    from nps_ctl.types import NPCClientConfig

    npc = NPCClientConfig(name="cloud.two", ssh_host="x", edges=["edge-a"], vkey="vk2")
    nps = PushNPS([{"Id": 1, "Remark": "renamed", "VerifyKey": "vk2"}])

    assert (
        cmd_npc.handle_client_push(_push_args("cloud.two"), _push_cluster(npc, nps))
        == 0
    )
    assert nps.added == []


def test_push_adds_when_no_vkey_or_remark_matches():
    from nps_ctl.types import NPCClientConfig

    npc = NPCClientConfig(name="cloud.two", ssh_host="x", edges=["edge-a"], vkey="vk2")
    nps = PushNPS([{"Id": 1, "Remark": "cloud.one", "VerifyKey": "vk1"}])

    assert (
        cmd_npc.handle_client_push(_push_args("cloud.two"), _push_cluster(npc, nps))
        == 0
    )
    assert len(nps.added) == 1
    assert nps.added[0]["remark"] == "cloud.two"
