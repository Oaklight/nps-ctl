"""Tests for ``edge sync --prune``."""

from __future__ import annotations

import pytest

from nps_ctl import client_mgmt, host, tunnel
from nps_ctl.cluster import NPSCluster, _TargetSnapshot
from nps_ctl.exceptions import NPSError

SOURCE_CLIENTS = [
    {"Id": 1, "VerifyKey": "vkey-a", "Remark": "alpha"},
    {"Id": 2, "VerifyKey": "vkey-b", "Remark": "beta"},
]
SOURCE_TUNNELS = [
    {
        "Id": 100,
        "Mode": "tcp",
        "Port": 80,
        "Client": {"Id": 1, "VerifyKey": "vkey-a"},
        "Remark": "web",
    }
]
SOURCE_HOSTS = [{"Id": 300, "Host": "app.example.com", "Location": ""}]


def _snapshot():
    clients = [
        {"Id": 10, "VerifyKey": "vkey-a", "Remark": "alpha"},
        {"Id": 11, "VerifyKey": "vkey-c", "Remark": "gamma"},
        {"Id": 12, "VerifyKey": "", "Remark": "no-key"},
    ]
    tunnels = [
        {
            "Id": 200,
            "Mode": "tcp",
            "Port": 80,
            "Client": {"Id": 10, "VerifyKey": "vkey-a"},
            "Remark": "web",
        },
        {
            "Id": 201,
            "Mode": "tcp",
            "Port": 81,
            "Client": {"Id": 10, "VerifyKey": "vkey-a"},
            "Remark": "old",
        },
        {
            "Id": 202,
            "Mode": "tcp",
            "Port": 82,
            "Client": {"Id": 11, "VerifyKey": "vkey-c"},
            "Remark": "gamma-old",
        },
    ]
    hosts = [
        {"Id": 300, "Host": "app.example.com", "Location": ""},
        {"Id": 301, "Host": "old.example.com", "Location": "/"},
    ]
    return _TargetSnapshot(
        clients=clients,
        vkeys={client["VerifyKey"] for client in clients},
        tunnels=tunnels,
        tunnel_keys={
            (item["Client"]["Id"], item["Mode"], item["Port"]) for item in tunnels
        },
        hosts=hosts,
        host_keys={(item["Host"], item["Location"] or "/") for item in hosts},
    )


class _NPS:
    """Minimal NPS client stub for the cluster's destructor."""

    def cleanup(self) -> None:
        pass


def _cluster():
    cluster = object.__new__(NPSCluster)
    cluster._clients = {"edge-b": _NPS()}
    return cluster


def test_prune_deletes_extras_in_dependency_order(monkeypatch):
    calls: list[tuple[str, int]] = []
    monkeypatch.setattr(
        tunnel, "del_tunnel", lambda nps, tid: calls.append(("tunnel", tid)) or True
    )
    monkeypatch.setattr(
        host, "del_host", lambda nps, hid: calls.append(("host", hid)) or True
    )
    monkeypatch.setattr(
        client_mgmt,
        "del_client",
        lambda nps, cid: calls.append(("client", cid)) or True,
    )

    results = _cluster()._prune_target(
        "edge-b",
        _snapshot(),
        SOURCE_CLIENTS,
        SOURCE_TUNNELS,
        SOURCE_HOSTS,
        sync_clients=True,
        sync_tunnels=True,
        sync_hosts=True,
    )

    assert results == {
        "prune:tunnel:old": True,
        "prune:tunnel:gamma-old": True,
        "prune:host:old.example.com": True,
        "prune:client:gamma": True,
    }
    # Descendants are removed before the owning client, and resources with
    # no stable identity (the empty-vkey client) are kept.
    assert calls == [
        ("tunnel", 201),
        ("tunnel", 202),
        ("host", 301),
        ("client", 11),
    ]


def test_prune_respects_selected_types(monkeypatch):
    calls: list[tuple[str, int]] = []
    monkeypatch.setattr(
        tunnel, "del_tunnel", lambda nps, tid: calls.append(("tunnel", tid)) or True
    )
    monkeypatch.setattr(
        host, "del_host", lambda nps, hid: calls.append(("host", hid)) or True
    )
    monkeypatch.setattr(
        client_mgmt,
        "del_client",
        lambda nps, cid: calls.append(("client", cid)) or True,
    )

    results = _cluster()._prune_target(
        "edge-b",
        _snapshot(),
        SOURCE_CLIENTS,
        SOURCE_TUNNELS,
        SOURCE_HOSTS,
        sync_clients=False,
        sync_tunnels=True,
        sync_hosts=False,
    )

    assert set(results) == {"prune:tunnel:old", "prune:tunnel:gamma-old"}
    assert calls == [("tunnel", 201), ("tunnel", 202)]


def test_prune_reports_rows_without_ids(monkeypatch):
    calls: list[tuple[str, int]] = []
    monkeypatch.setattr(
        tunnel, "del_tunnel", lambda nps, tid: calls.append(("tunnel", tid)) or True
    )
    monkeypatch.setattr(
        host, "del_host", lambda nps, hid: calls.append(("host", hid)) or True
    )
    monkeypatch.setattr(
        client_mgmt,
        "del_client",
        lambda nps, cid: calls.append(("client", cid)) or True,
    )
    snapshot = _snapshot()
    snapshot.tunnels.append(
        {
            "Id": 0,
            "Mode": "tcp",
            "Port": 83,
            "Client": {"Id": 10, "VerifyKey": "vkey-a"},
            "Remark": "no-id",
        }
    )
    snapshot.tunnel_keys.add((10, "tcp", 83))

    results = _cluster()._prune_target(
        "edge-b",
        snapshot,
        SOURCE_CLIENTS,
        SOURCE_TUNNELS,
        SOURCE_HOSTS,
        sync_clients=False,
        sync_tunnels=True,
        sync_hosts=False,
    )

    assert results["prune:tunnel:no-id"] is False
    assert ("tunnel", 0) not in calls


class _FailingNPS:
    is_modern = False

    def request(self, *args, **kwargs):
        raise NPSError("connection refused")


def test_strict_source_fetch_aborts_before_pruning():
    cluster = _cluster()

    with pytest.raises(NPSError, match="incomplete source data"):
        cluster._fetch_source_data(
            _FailingNPS(), True, False, False, "edge-a", strict=True
        )

    assert cluster._fetch_source_data(
        _FailingNPS(), True, False, False, "edge-a", strict=False
    ) == ([], [], [])


def test_prune_tunnels_without_source_clients_aborts(monkeypatch):
    """A missing source client list must never look like an empty source."""
    calls: list[int] = []
    monkeypatch.setattr(
        tunnel, "del_tunnel", lambda nps, tid: calls.append(tid) or True
    )

    with pytest.raises(NPSError, match="no source client could be mapped"):
        _cluster()._prune_target(
            "edge-b",
            _snapshot(),
            [],
            SOURCE_TUNNELS,
            SOURCE_HOSTS,
            sync_clients=False,
            sync_tunnels=True,
            sync_hosts=False,
        )

    assert calls == []


def test_prune_keeps_tunnels_when_a_source_client_is_anonymous(monkeypatch):
    """An anonymous source row may be any target client, so keep its tunnels."""
    calls: list[int] = []
    monkeypatch.setattr(
        tunnel, "del_tunnel", lambda nps, tid: calls.append(tid) or True
    )
    source_clients = [
        {"Id": 1, "VerifyKey": "vkey-a"},
        {"Id": 3, "VerifyKey": ""},
    ]
    source_tunnels = [
        {"Id": 100, "Mode": "tcp", "Port": 80, "Client": {"Id": 1}},
        {"Id": 101, "Mode": "tcp", "Port": 3306, "Client": {"Id": 3}},
    ]

    results = _cluster()._prune_target(
        "edge-b",
        _snapshot(),
        source_clients,
        source_tunnels,
        SOURCE_HOSTS,
        sync_clients=False,
        sync_tunnels=True,
        sync_hosts=False,
    )

    # The tunnel under mapped client 10 is provably extra and goes; the one
    # under unmapped client 11 is kept because the anonymous source row could
    # be that client.
    assert calls == [201]
    assert results == {"prune:tunnel:old": True}


def test_prune_tunnels_aborts_for_wholly_anonymous_source_client(monkeypatch):
    """The clementine repro: same tunnel, source row lost its VerifyKey."""
    calls: list[int] = []
    monkeypatch.setattr(
        tunnel, "del_tunnel", lambda nps, tid: calls.append(tid) or True
    )
    monkeypatch.setattr(
        client_mgmt, "del_client", lambda nps, cid: calls.append(cid) or True
    )
    source_clients = [{"Id": 5, "VerifyKey": ""}]
    source_tunnels = [
        {"Id": 400, "Mode": "tcp", "Port": 3306, "Client": {"Id": 5}},
    ]

    with pytest.raises(NPSError):
        _cluster()._prune_target(
            "edge-b",
            _snapshot(),
            source_clients,
            source_tunnels,
            [],
            sync_clients=True,
            sync_tunnels=True,
            sync_hosts=False,
        )

    assert calls == []


def test_prune_clients_without_verify_keys_aborts(monkeypatch):
    calls: list[int] = []
    monkeypatch.setattr(
        client_mgmt,
        "del_client",
        lambda nps, cid: calls.append(cid) or True,
    )

    with pytest.raises(NPSError, match="a source client has no VerifyKey"):
        _cluster()._prune_target(
            "edge-b",
            _snapshot(),
            [{"Id": 1, "VerifyKey": ""}],
            [],
            [],
            sync_clients=True,
            sync_tunnels=False,
            sync_hosts=False,
        )

    assert calls == []


def test_prune_clients_with_empty_source_aborts(monkeypatch):
    calls: list[int] = []
    monkeypatch.setattr(
        client_mgmt, "del_client", lambda nps, cid: calls.append(cid) or True
    )

    with pytest.raises(NPSError, match="returned no clients"):
        _cluster()._prune_target(
            "edge-b",
            _snapshot(),
            [],
            [],
            [],
            sync_clients=True,
            sync_tunnels=False,
            sync_hosts=False,
        )

    assert calls == []


def test_prune_tunnels_with_anonymous_source_tunnel_aborts(monkeypatch):
    calls: list[int] = []
    monkeypatch.setattr(
        tunnel, "del_tunnel", lambda nps, tid: calls.append(tid) or True
    )

    with pytest.raises(NPSError, match="source tunnel's client has no identity"):
        _cluster()._prune_target(
            "edge-b",
            _snapshot(),
            SOURCE_CLIENTS,
            [{"Id": 100, "Mode": "tcp", "Port": 80, "Client": {}}],
            SOURCE_HOSTS,
            sync_clients=False,
            sync_tunnels=True,
            sync_hosts=False,
        )

    assert calls == []


def test_strict_source_rejects_anonymous_client(monkeypatch):
    monkeypatch.setattr(
        client_mgmt, "list_clients", lambda nps: [{"Id": 1, "VerifyKey": ""}]
    )

    with pytest.raises(NPSError, match="a source client has no VerifyKey"):
        _cluster()._fetch_source_data(_NPS(), True, False, False, "edge-a", strict=True)


def test_sync_from_fetches_clients_for_tunnel_prune(monkeypatch):
    cluster = _cluster()
    cluster._clients["edge-a"] = _NPS()
    seen: dict[str, object] = {}

    def fake_fetch(source, sync_clients, sync_tunnels, sync_hosts, name, *, strict):
        seen.update(
            clients=sync_clients,
            tunnels=sync_tunnels,
            hosts=sync_hosts,
            strict=strict,
        )
        return SOURCE_CLIENTS, SOURCE_TUNNELS, []

    cluster._fetch_source_data = fake_fetch  # type: ignore[method-assign]
    cluster._sync_from_sequential = lambda **kwargs: {}  # type: ignore[method-assign]
    cluster._print_sync_summary = lambda *args, **kwargs: None  # type: ignore[method-assign]

    cluster.sync_from(
        "edge-a",
        sync_clients=False,
        sync_tunnels=True,
        sync_hosts=False,
        target_edges=["edge-b"],
        prune=True,
        quiet=True,
    )

    # Tunnels are pruned by client identity, so the client list is required
    # even though clients themselves are not synced.
    assert seen == {"clients": True, "tunnels": True, "hosts": False, "strict": True}


def test_prune_refuses_empty_source_tunnels_when_target_has_rows(monkeypatch):
    calls: list[int] = []
    monkeypatch.setattr(
        tunnel, "del_tunnel", lambda nps, tid: calls.append(tid) or True
    )

    with pytest.raises(NPSError, match="returned no tunnels"):
        _cluster()._prune_target(
            "edge-b",
            _snapshot(),
            SOURCE_CLIENTS,
            [],
            SOURCE_HOSTS,
            sync_clients=False,
            sync_tunnels=True,
            sync_hosts=False,
        )

    assert calls == []


def test_prune_refuses_empty_source_hosts_when_target_has_rows(monkeypatch):
    calls: list[int] = []
    monkeypatch.setattr(host, "del_host", lambda nps, hid: calls.append(hid) or True)

    with pytest.raises(NPSError, match="returned no hosts"):
        _cluster()._prune_target(
            "edge-b",
            _snapshot(),
            SOURCE_CLIENTS,
            SOURCE_TUNNELS,
            [],
            sync_clients=False,
            sync_tunnels=False,
            sync_hosts=True,
        )

    assert calls == []
