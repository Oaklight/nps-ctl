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
    assert push_args.yes is True
    # The reloaded cluster sees the entry just written to clients.toml.
    assert npc is not None
    assert npc.vkey == "vkey-new"
    assert npc.edges == ["edge-a", "edge-b"]
