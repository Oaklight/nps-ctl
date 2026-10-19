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


def test_get_all_tunnels_limits_to_requested_edges(tmp_path, monkeypatch):
    names = ["edge-a", "edge-b", "edge-c"]
    cluster = _cluster(tmp_path, names)
    called = []

    def fake_list(nps):
        called.append(nps.name)
        return [{"Id": 1, "Port": 8080}]

    monkeypatch.setattr(cluster_module.tunnel, "list_tunnels", fake_list)

    result = cluster.get_all_tunnels(edge_names=["edge-b"])

    assert list(result) == ["edge-b"]
    assert result.errors == {}
    assert called == ["edge-b"]


def test_get_all_tunnels_passes_type_filter(tmp_path, monkeypatch):
    cluster = _cluster(tmp_path, ["edge-a"])
    calls = []

    def fake_list(nps, tunnel_type=""):
        calls.append((nps.name, tunnel_type))
        return []

    monkeypatch.setattr(cluster_module.tunnel, "list_tunnels", fake_list)

    result = cluster.get_all_tunnels(tunnel_type="tcp")

    assert result == {"edge-a": []}
    assert calls == [("edge-a", "tcp")]


def test_get_all_tunnels_empty_selection_makes_no_calls(tmp_path, monkeypatch):
    cluster = _cluster(tmp_path, ["edge-a", "edge-b"])
    called = []

    def fake_list(nps):
        called.append(nps.name)
        return []

    monkeypatch.setattr(cluster_module.tunnel, "list_tunnels", fake_list)

    result = cluster.get_all_tunnels(edge_names=[])

    assert result == {}
    assert called == []


def test_get_all_tunnels_unknown_edge_reports_error(tmp_path, monkeypatch):
    cluster = _cluster(tmp_path, ["edge-a"])

    def fake_list(nps):
        return []

    monkeypatch.setattr(cluster_module.tunnel, "list_tunnels", fake_list)

    result = cluster.get_all_tunnels(edge_names=["missing"])

    assert list(result) == ["missing"]
    assert result["missing"] == []
    assert result.errors == {"missing": "Edge 'missing' not found"}


def test_get_all_clients_contacts_only_selected_edges(tmp_path, monkeypatch):
    names = ["edge-a", "edge-b", "edge-c"]
    cluster = _cluster(tmp_path, names)
    called = []

    def fake_list(nps):
        called.append(nps.name)
        return [{"Id": 1, "Remark": nps.name}]

    monkeypatch.setattr(cluster_module.client_mgmt, "list_clients", fake_list)

    result = cluster.get_all_clients(edge_names=["edge-c", "edge-a"])

    assert called == ["edge-c", "edge-a"]
    assert list(result) == ["edge-c", "edge-a"]
    assert result.errors == {}


def test_get_all_hosts_contacts_only_selected_edges(tmp_path, monkeypatch):
    names = ["edge-a", "edge-b"]
    cluster = _cluster(tmp_path, names)
    called = []

    def fake_list(nps):
        called.append(nps.name)
        return [{"Id": 1, "Host": f"{nps.name}.test"}]

    monkeypatch.setattr(cluster_module.host, "list_hosts", fake_list)

    result = cluster.get_all_hosts(edge_names=["edge-b"])

    assert called == ["edge-b"]
    assert list(result) == ["edge-b"]
    assert result["edge-b"][0]["Host"] == "edge-b.test"


def test_empty_edge_selection_makes_no_calls(tmp_path, monkeypatch):
    cluster = _cluster(tmp_path, ["edge-a", "edge-b"])

    def fail(nps):
        raise AssertionError("no edge should be contacted")

    monkeypatch.setattr(cluster_module.client_mgmt, "list_clients", fail)

    result = cluster.get_all_clients(edge_names=[])

    assert dict(result) == {}
    assert result.errors == {}


def test_unknown_edge_produces_clean_error(tmp_path, monkeypatch):
    cluster = _cluster(tmp_path, ["edge-a"])
    monkeypatch.setattr(
        cluster_module.client_mgmt, "list_clients", lambda nps: [{"Id": 1}]
    )

    result = cluster.get_all_clients(edge_names=["edge-a", "missing"])

    assert list(result) == ["edge-a", "missing"]
    assert result["missing"] == []
    assert result.errors == {"missing": "Edge 'missing' not found"}
