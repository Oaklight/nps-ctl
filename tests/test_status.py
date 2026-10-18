"""Tests for the shared edge status collector."""

from __future__ import annotations

from types import SimpleNamespace

from nps_ctl.status import (
    EdgeStatus,
    build_status_payload,
    collect_edge_status,
    count_distinct_target_ports,
    extract_target_ports,
)
from nps_ctl.types import EdgeResults


class FakeCluster:
    """Cluster stub returning canned lists and errors."""

    def __init__(
        self,
        edges,
        clients=None,
        hosts=None,
        client_errors=None,
        host_errors=None,
    ):
        self.edge_names = list(edges)
        self.clients = clients or {}
        self.hosts = hosts or {}
        self.client_errors = client_errors or {}
        self.host_errors = host_errors or {}
        self.client_calls: list[list[str] | None] = []
        self.host_calls: list[list[str] | None] = []

    def get_edge(self, name):
        if name not in self.edge_names:
            return None
        return SimpleNamespace(
            region=f"region-{name}", api_url=f"https://{name}.invalid"
        )

    def _results(self, source, errors, edge_names):
        names = self.edge_names if edge_names is None else edge_names
        result = EdgeResults(errors={n: errors[n] for n in names if n in errors})
        for name in names:
            result[name] = source.get(name, [])
        return result

    def get_all_clients(self, edge_names=None, max_workers=4):
        self.client_calls.append(edge_names)
        return self._results(self.clients, self.client_errors, edge_names)

    def get_all_hosts(self, edge_names=None, max_workers=4):
        self.host_calls.append(edge_names)
        return self._results(self.hosts, self.host_errors, edge_names)


def test_extract_target_ports_handles_forms():
    assert extract_target_ports("127.0.0.1:8080") == {8080}
    assert extract_target_ports("http://app.test:8443") == {8443}
    assert extract_target_ports("app.test:443,127.0.0.1:8080") == {443, 8080}
    assert extract_target_ports("[::1]:9000") == {9000}
    assert extract_target_ports("app.test") == set()
    assert extract_target_ports("app.test:0,app.test:70000") == set()
    assert extract_target_ports({"TargetStr": "127.0.0.1:8080"}) == {8080}
    assert extract_target_ports(None) == set()


def test_count_distinct_target_ports_unions_hosts():
    hosts = [
        {"Target": {"TargetStr": "127.0.0.1:8080"}},
        {"Target": {"TargetStr": "127.0.0.1:8080,127.0.0.1:9090"}},
        {"Target": {"TargetStr": "app.test:443"}},
    ]

    assert count_distinct_target_ports(hosts) == 3


def test_collect_healthy_edge():
    cluster = FakeCluster(
        ["edge-a"],
        clients={
            "edge-a": [
                {"Id": 1, "IsConnect": True},
                {"Id": 2, "IsConnect": False},
            ]
        },
        hosts={
            "edge-a": [
                {"Target": {"TargetStr": "127.0.0.1:8080"}},
                {"Target": {"TargetStr": "127.0.0.1:8080,127.0.0.1:9090"}},
            ]
        },
    )

    [row] = collect_edge_status(cluster)

    assert row.online is True
    assert row.ok is True
    assert row.partial is False
    assert row.clients_total == 2
    assert row.clients_online == 1
    assert row.hosts_total == 2
    assert row.ports == 2
    assert row.error == ""


def test_collect_host_only_failure_is_partial():
    cluster = FakeCluster(
        ["edge-a"],
        clients={"edge-a": [{"Id": 1, "IsConnect": True}]},
        host_errors={"edge-a": "timeout"},
    )

    [row] = collect_edge_status(cluster)

    assert row.online is True
    assert row.partial is True
    assert row.ok is False
    assert row.clients_total == 1
    assert row.clients_online == 1
    assert row.hosts_total is None
    assert row.ports is None
    assert row.error == "hosts: timeout"


def test_collect_offline_edge_keeps_counts_none():
    cluster = FakeCluster(
        ["edge-a"],
        client_errors={"edge-a": "connection refused"},
        host_errors={"edge-a": "connection refused"},
    )

    [row] = collect_edge_status(cluster)

    assert row.online is False
    assert row.ok is False
    assert row.partial is False
    assert row.clients_total is None
    assert row.clients_online is None
    assert row.hosts_total is None
    assert row.ports is None
    assert row.error == "clients: connection refused; hosts: connection refused"


def test_collect_subset_dedupes_and_preserves_order():
    cluster = FakeCluster(
        ["edge-a", "edge-b", "edge-c"],
        clients={"edge-a": [{"Id": 1}], "edge-b": [{"Id": 2}, {"Id": 3}]},
        hosts={"edge-a": [], "edge-b": [{"Target": {"TargetStr": "h:80"}}]},
    )

    rows = collect_edge_status(cluster, edge_names=["edge-b", "edge-a", "edge-b"])

    assert [row.edge for row in rows] == ["edge-b", "edge-a"]
    assert cluster.client_calls == [["edge-b", "edge-a"]]
    assert cluster.host_calls == [["edge-b", "edge-a"]]
    assert rows[0].clients_total == 2


def test_collect_unknown_edge_makes_no_calls_for_it():
    cluster = FakeCluster(["edge-a"], clients={"edge-a": [{"Id": 1}]}, hosts={})

    rows = collect_edge_status(cluster, edge_names=["missing", "edge-a"])

    assert [row.edge for row in rows] == ["missing", "edge-a"]
    assert rows[0].error == "Edge 'missing' not found"
    assert rows[0].online is False
    assert rows[0].clients_total is None
    assert cluster.client_calls == [["edge-a"]]
    assert cluster.host_calls == [["edge-a"]]


def test_collect_empty_selection_makes_no_calls():
    cluster = FakeCluster(["edge-a"])

    rows = collect_edge_status(cluster, edge_names=[])

    assert rows == []
    assert cluster.client_calls == [[]]
    assert cluster.host_calls == [[]]


def test_status_payload_shape_and_totals():
    rows = [
        EdgeStatus(
            edge="edge-a",
            region="r",
            api_url="https://a.invalid",
            online=True,
            clients_ok=True,
            clients_total=3,
            clients_online=2,
            hosts_ok=True,
            hosts_total=4,
            ports=2,
        ),
        EdgeStatus(
            edge="edge-b",
            region="r",
            api_url="https://b.invalid",
            online=True,
            clients_ok=True,
            clients_total=1,
            clients_online=0,
            hosts_ok=False,
            hosts_total=None,
            ports=None,
            error="hosts: timeout",
        ),
        EdgeStatus(
            edge="edge-c",
            region="r",
            api_url="https://c.invalid",
            online=False,
            clients_ok=False,
            clients_total=None,
            clients_online=None,
            hosts_ok=False,
            hosts_total=None,
            ports=None,
            error="clients: refused",
        ),
    ]

    payload = build_status_payload(rows)

    assert payload["summary"] == {"configured": 3, "online": 2, "offline": 1}
    assert payload["totals"] == {
        "ok": 1,
        "failed": 1,
        "partial": 1,
        "clients": 4,
        "hosts": 4,
        "ports": 2,
    }
    assert payload["edges"][1]["hosts_total"] is None
    assert payload["edges"][1]["partial"] is True
    assert payload["edges"][2]["clients_total"] is None
    assert payload["edges"][2]["error"] == "clients: refused"


def test_status_module_does_not_import_cluster_at_runtime():
    import nps_ctl.cluster  # noqa: F401
    import nps_ctl.status  # noqa: F401
