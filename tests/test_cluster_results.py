"""Tests for deterministic multi-edge fetching and failure reporting."""

from __future__ import annotations

import time

from nps_ctl import cluster as cluster_module
from nps_ctl.cluster import NPSCluster
from nps_ctl.exceptions import NPSError


class FakeClient:
    """Minimal stand-in for NPSClient used by the cluster fetcher."""

    def __init__(self, name: str) -> None:
        self.name = name

    def cleanup(self) -> None:
        """Match NPSClient.cleanup; nothing to release."""


def _write_config(tmp_path, names: list[str]):
    edges = "\n".join(
        f'[[edges]]\nname = "{name}"\napi_url = "https://{name}.invalid"\n'
        f'auth_key = "key"\nregion = "region-{name}"\nssh_host = "{name}"'
        for name in names
    )
    path = tmp_path / "edges.toml"
    path.write_text(edges + "\n", encoding="utf-8")
    return path


def _cluster(tmp_path, names: list[str]) -> NPSCluster:
    cluster = NPSCluster(str(_write_config(tmp_path, names)))
    cluster._clients = {name: FakeClient(name) for name in names}
    return cluster


def test_parallel_fetch_preserves_configured_order(tmp_path, monkeypatch):
    names = ["edge-a", "edge-b", "edge-c", "edge-d"]
    cluster = _cluster(tmp_path, names)
    delays = {"edge-a": 0.04, "edge-b": 0.03, "edge-c": 0.02, "edge-d": 0.01}

    def fake_list(nps):
        time.sleep(delays[nps.name])
        return [{"Id": 1, "Remark": nps.name}]

    monkeypatch.setattr(cluster_module.client_mgmt, "list_clients", fake_list)

    result = cluster.get_all_clients()

    assert list(result) == names
    assert result.errors == {}


def test_failed_edge_is_reported_and_kept_in_order(tmp_path, monkeypatch):
    names = ["edge-a", "edge-b", "edge-c"]
    cluster = _cluster(tmp_path, names)

    def fake_list(nps):
        if nps.name == "edge-b":
            raise NPSError("connection refused")
        return [{"Id": 1}]

    monkeypatch.setattr(cluster_module.client_mgmt, "list_clients", fake_list)

    result = cluster.get_all_clients()

    assert list(result) == names
    assert result["edge-b"] == []
    assert result.errors == {"edge-b": "connection refused"}
    assert result.failed_edges == ["edge-b"]
    assert result.ok_edges == ["edge-a", "edge-c"]


def test_host_fetch_failure_is_reported(tmp_path, monkeypatch):
    names = ["edge-a", "edge-b"]
    cluster = _cluster(tmp_path, names)

    def fake_list(nps):
        if nps.name == "edge-b":
            raise NPSError("timeout")
        return [{"Id": 1, "Host": "example.test"}]

    monkeypatch.setattr(cluster_module.host, "list_hosts", fake_list)

    result = cluster.get_all_hosts()

    assert result["edge-b"] == []
    assert result.errors == {"edge-b": "timeout"}
