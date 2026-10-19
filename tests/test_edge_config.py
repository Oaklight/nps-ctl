"""Tests for edges.toml editing and the edge primary/add/sync commands."""

from __future__ import annotations

import tomllib
from types import SimpleNamespace

import pytest

from nps_ctl.cli import cmd_edge_config, cmd_sync
from nps_ctl.cluster import NPSCluster
from nps_ctl.config_edit import append_edge_text, set_primary_text

CONFIG = """# Cluster config
auth_crypt_key = "k"

# Web credentials
[web]
username = "u"

[[edges]]
name = "edge-a"
api_url = "https://a.invalid"

[[edges]]
name = "edge-b"
api_url = "https://b.invalid"
"""


def _write(tmp_path, text=CONFIG):
    path = tmp_path / "edges.toml"
    path.write_text(text, encoding="utf-8")
    return path


def test_set_primary_inserts_top_level_key_and_keeps_comments():
    result = set_primary_text(CONFIG, "edge-b")

    parsed = tomllib.loads(result)
    assert parsed["primary"] == "edge-b"
    assert parsed["web"] == {"username": "u"}
    assert result.count("#") == CONFIG.count("#")
    # Inserted above the comment that introduces [web], not inside the table.
    assert result.index('primary = "edge-b"') < result.index("# Web credentials")


def test_set_primary_replaces_existing_value():
    once = set_primary_text(CONFIG, "edge-a")
    twice = set_primary_text(once, "edge-b")

    assert tomllib.loads(twice)["primary"] == "edge-b"
    assert twice.count("primary =") == 1


def test_set_primary_ignores_primary_keys_inside_tables():
    text = '[web]\nprimary = "not-top-level"\n'

    result = set_primary_text(text, "edge-a")

    parsed = tomllib.loads(result)
    assert parsed["primary"] == "edge-a"
    assert parsed["web"]["primary"] == "not-top-level"


def test_set_primary_quotes_value():
    result = set_primary_text(CONFIG, 'we"ird')

    assert tomllib.loads(result)["primary"] == 'we"ird'


def test_append_edge_adds_entry_and_rejects_duplicates():
    result = append_edge_text(
        CONFIG, name="edge-c", api_url="https://c.invalid", region="EU"
    )

    edges = tomllib.loads(result)["edges"]
    assert [edge["name"] for edge in edges] == ["edge-a", "edge-b", "edge-c"]
    assert edges[-1] == {
        "name": "edge-c",
        "api_url": "https://c.invalid",
        "region": "EU",
    }
    with pytest.raises(ValueError, match="already exists"):
        append_edge_text(result, name="edge-a", api_url="https://x.invalid")


def test_cluster_primary_edge(tmp_path):
    path = _write(tmp_path, set_primary_text(CONFIG, "edge-b"))
    assert NPSCluster(path).primary_edge == "edge-b"

    path = _write(tmp_path, set_primary_text(CONFIG, "missing"))
    cluster = NPSCluster(path)
    assert cluster.primary_edge is None
    assert cluster.configured_primary == "missing"

    assert NPSCluster(_write(tmp_path)).primary_edge is None


def test_edge_primary_sets_known_edge(tmp_path):
    path = _write(tmp_path)

    code = cmd_edge_config.cmd_edge_primary(
        SimpleNamespace(config=str(path), name="edge-a", json=False)
    )

    assert code == 0
    assert tomllib.loads(path.read_text())["primary"] == "edge-a"


def test_edge_primary_rejects_unknown_edge(tmp_path):
    path = _write(tmp_path)

    code = cmd_edge_config.cmd_edge_primary(
        SimpleNamespace(config=str(path), name="nope", json=False)
    )

    assert code == 1
    assert "primary" not in tomllib.loads(path.read_text())


def _add_args(path, **overrides):
    values = {
        "config": str(path),
        "name": "edge-c",
        "api_url": "https://c.invalid/",
        "region": "EU",
        "ssh_host": "",
        "no_auth_key": False,
        "yes": True,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_edge_add_reads_auth_key_from_env(tmp_path, monkeypatch):
    path = _write(tmp_path)
    monkeypatch.setenv("NPS_EDGE_AUTH_KEY", "secret-key")

    assert cmd_edge_config.cmd_edge_add(_add_args(path)) == 0

    edge = tomllib.loads(path.read_text())["edges"][-1]
    assert edge["name"] == "edge-c"
    assert edge["api_url"] == "https://c.invalid"
    assert edge["auth_key"] == "secret-key"


def test_edge_add_validates_url_and_name(tmp_path, monkeypatch):
    path = _write(tmp_path)
    monkeypatch.delenv("NPS_EDGE_AUTH_KEY", raising=False)

    assert cmd_edge_config.cmd_edge_add(_add_args(path, api_url="c.invalid")) == 2
    assert cmd_edge_config.cmd_edge_add(_add_args(path, name="edge-a")) == 1
    assert len(tomllib.loads(path.read_text())["edges"]) == 2


def test_edge_add_without_tty_fails_cleanly(tmp_path, monkeypatch):
    path = _write(tmp_path)
    monkeypatch.delenv("NPS_EDGE_AUTH_KEY", raising=False)

    def no_tty(prompt):
        raise EOFError

    monkeypatch.setattr(cmd_edge_config.getpass, "getpass", no_tty)

    assert cmd_edge_config.cmd_edge_add(_add_args(path)) == 2
    assert cmd_edge_config.cmd_edge_add(_add_args(path, no_auth_key=True)) == 0
    assert "auth_key" not in tomllib.loads(path.read_text())["edges"][-1]


def _sync_args(path, source=None):
    return SimpleNamespace(
        config=str(path),
        source=source,
        edge=None,
        type="all",
        yes=True,
        parallel=False,
        quiet=True,
        workers=4,
    )


def test_sync_without_source_or_primary_is_usage_error(tmp_path):
    assert cmd_sync.cmd_sync(_sync_args(_write(tmp_path))) == 2


def test_sync_defaults_source_to_primary(tmp_path, monkeypatch):
    path = _write(tmp_path, set_primary_text(CONFIG, "edge-b"))
    calls = {}

    def fake_sync_from(self, source, **kwargs):
        calls["source"] = source
        calls["targets"] = kwargs["target_edges"]
        return {}

    monkeypatch.setattr(NPSCluster, "sync_from", fake_sync_from)

    assert cmd_sync.cmd_sync(_sync_args(path)) == 0
    assert calls == {"source": "edge-b", "targets": ["edge-a"]}
