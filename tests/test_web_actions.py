"""Tests for the dashboard write endpoints."""

from __future__ import annotations

import html
import json
import threading
import tomllib
import urllib.error
import urllib.request

import pytest

from nps_ctl import client_mgmt
from nps_ctl import host as host_mod
from nps_ctl import tunnel as tunnel_mod
from nps_ctl.cluster import NPSCluster
from nps_ctl.web import build_auth_header, create_server
from tests.test_web import PASSWORD, FakeCluster, FakeNPS


def _serve(cluster, allow_writes=True):
    server = create_server(
        cluster,
        "127.0.0.1",
        0,
        username="admin",
        password=PASSWORD,
        allow_writes=allow_writes,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


@pytest.fixture
def writable():
    server, thread = _serve(FakeCluster())
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@pytest.fixture
def readonly():
    server, thread = _serve(FakeCluster(), allow_writes=False)
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def _url(server, path):
    host, port = server.server_address[:2]
    return f"http://{host}:{port}{path}"


def _post(server, path, payload, *, csrf=True, origin=None, content_type=None):
    headers = {
        "Authorization": build_auth_header("admin", PASSWORD),
        "Content-Type": content_type or "application/json",
    }
    if csrf:
        headers["X-CSRF-Token"] = server.csrf_token
    if origin:
        headers["Origin"] = origin
    request = urllib.request.Request(
        _url(server, path),
        data=json.dumps(payload).encode(),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status, json.load(response)
    except urllib.error.HTTPError as e:
        return e.code, json.load(e)


def _page(server):
    request = urllib.request.Request(
        _url(server, "/"),
        headers={"Authorization": build_auth_header("admin", PASSWORD)},
    )
    with urllib.request.urlopen(request, timeout=5) as response:
        return response.read().decode()


HOST_PAYLOAD = {
    "host": "new.example.com",
    "client": "alpha",
    "target": "127.0.0.1:9000",
    "edges": ["edge-a"],
}


def test_writes_disabled_by_default(readonly):
    status, body = _post(readonly, "/api/actions/hosts", HOST_PAYLOAD)

    assert status == 403
    assert "--allow-writes" in body["error"]


def test_readonly_page_has_no_csrf_token(readonly):
    page = _page(readonly)

    assert readonly.csrf_token not in page
    assert html.escape('"writes": false', quote=True) in page


def test_writable_page_embeds_csrf_token(writable):
    assert writable.csrf_token in _page(writable)


def test_missing_csrf_token_rejected(writable):
    status, _ = _post(writable, "/api/actions/hosts", HOST_PAYLOAD, csrf=False)

    assert status == 403


def test_cross_origin_rejected(writable):
    status, body = _post(
        writable, "/api/actions/hosts", HOST_PAYLOAD, origin="https://evil.invalid"
    )

    assert status == 403
    assert "Cross-origin" in body["error"]


def test_non_json_rejected(writable):
    status, _ = _post(
        writable, "/api/actions/hosts", HOST_PAYLOAD, content_type="text/plain"
    )

    assert status == 415


def test_unknown_edge_is_bad_request(writable):
    status, body = _post(
        writable, "/api/actions/hosts", {**HOST_PAYLOAD, "edges": ["nope"]}
    )

    assert status == 400
    assert "nope" in body["error"]


def test_edges_are_required(writable):
    status, _ = _post(writable, "/api/actions/hosts", {**HOST_PAYLOAD, "edges": []})

    assert status == 400


def test_add_host_resolves_client_and_adds(writable, monkeypatch):
    calls = []

    def fake_add_host(nps, **kwargs):
        calls.append(kwargs)
        return True

    monkeypatch.setattr(host_mod, "add_host", fake_add_host)
    origin = _url(writable, "")

    status, body = _post(writable, "/api/actions/hosts", HOST_PAYLOAD, origin=origin)

    assert status == 200
    assert body["results"] == {"edge-a": {"ok": True, "status": "added"}}
    assert calls[0]["client_id"] == 1
    assert calls[0]["host"] == "new.example.com"


def test_add_host_skips_existing_mapping(writable, monkeypatch):
    monkeypatch.setattr(
        host_mod, "add_host", lambda *a, **k: pytest.fail("should not add")
    )

    status, body = _post(
        writable, "/api/actions/hosts", {**HOST_PAYLOAD, "host": "app.example.com"}
    )

    assert status == 200
    assert body["results"]["edge-a"] == {"ok": True, "status": "exists"}


def test_add_host_reports_missing_client(writable):
    status, body = _post(
        writable, "/api/actions/hosts", {**HOST_PAYLOAD, "client": "ghost"}
    )

    assert status == 200
    assert body["results"]["edge-a"]["ok"] is False
    assert "ghost" in body["results"]["edge-a"]["error"]


def test_add_client_shares_generated_vkey(writable, monkeypatch):
    calls = []

    def fake_add_client(nps, **kwargs):
        calls.append(kwargs)
        return True

    monkeypatch.setattr(client_mgmt, "add_client", fake_add_client)

    status, body = _post(
        writable, "/api/actions/clients", {"remark": "beta", "edges": ["edge-a"]}
    )

    assert status == 200
    assert body["results"]["edge-a"]["status"] == "added"
    assert len(body["vkey"]) == 16
    assert calls == [{"remark": "beta", "vkey": body["vkey"]}]


def test_add_tunnel_validates_port(writable):
    status, body = _post(
        writable,
        "/api/actions/tunnels",
        {"client": "alpha", "port": 70000, "target": ":22", "edges": ["edge-a"]},
    )

    assert status == 400
    assert "port" in body["error"]


def test_sync_excludes_source_and_reports_per_edge():
    cluster = FakeCluster(
        edge_data={"edge-a": FakeNPS(), "edge-b": FakeNPS(), "edge-c": FakeNPS()}
    )
    calls = {}

    def sync_from(source, **kwargs):
        calls["source"] = source
        calls["targets"] = kwargs["target_edges"]
        calls["prune"] = kwargs.get("prune")
        return {
            "edge-b": {"client:x": True},
            "edge-c": {"client:x": True, "host:y": False},
        }

    cluster.sync_from = sync_from
    server, thread = _serve(cluster)
    try:
        status, body = _post(
            server,
            "/api/actions/sync",
            {"source": "edge-a", "edges": ["edge-a", "edge-b", "edge-c"]},
        )
        empty_status, _ = _post(
            server,
            "/api/actions/sync",
            {"source": "edge-a", "types": [], "edges": ["edge-b"]},
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert status == 200
    assert calls == {
        "source": "edge-a",
        "targets": ["edge-b", "edge-c"],
        "prune": False,
    }
    assert body["results"]["edge-b"]["ok"] is True
    assert body["results"]["edge-c"] == {
        "ok": False,
        "status": "2 checked",
        "failed": ["host:y"],
    }
    assert empty_status == 400


def test_sync_passes_prune_and_validates_it():
    cluster = FakeCluster(edge_data={"edge-a": FakeNPS(), "edge-b": FakeNPS()})
    seen = {}

    def sync_from(source, **kwargs):
        seen["prune"] = kwargs.get("prune")
        return {"edge-b": {}}

    cluster.sync_from = sync_from
    server, thread = _serve(cluster)
    try:
        status, body = _post(
            server,
            "/api/actions/sync",
            {"source": "edge-a", "edges": ["edge-b"], "prune": True},
        )
        bad_status, bad_body = _post(
            server,
            "/api/actions/sync",
            {"source": "edge-a", "edges": ["edge-b"], "prune": "yes"},
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert status == 200
    assert seen["prune"] is True
    assert body["prune"] is True
    assert bad_status == 400
    assert "prune" in bad_body["error"]


def test_writes_require_auth_on_public_bind():
    with pytest.raises(ValueError, match="enable writes"):
        create_server(
            FakeCluster(), "0.0.0.0", 0, allow_insecure=True, allow_writes=True
        )


def _raw(server, method, path, host, body=None):
    import http.client

    address = server.server_address[:2]
    if address[0] in {"0.0.0.0", "::"}:
        address = ("127.0.0.1", address[1])
    conn = http.client.HTTPConnection(*address, timeout=5)
    headers = {"Host": host, "Content-Type": "application/json"}
    if body is not None:
        headers["X-CSRF-Token"] = server.csrf_token
        headers["Origin"] = f"http://{host}"
    conn.request(method, path, body=body, headers=headers)
    response = conn.getresponse()
    response.read()
    conn.close()
    return response.status


def test_rebinding_host_rejected_without_auth():
    server = create_server(FakeCluster(), "127.0.0.1", 0, allow_writes=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = server.server_address[1]
    body = json.dumps(HOST_PAYLOAD)
    try:
        assert _raw(server, "GET", "/", f"evil.example:{port}") == 403
        assert (
            _raw(server, "POST", "/api/actions/hosts", f"evil.example:{port}", body)
            == 403
        )
        assert _raw(server, "GET", "/", f"127.0.0.1:{port}") == 200
        assert _raw(server, "GET", "/", f"localhost:{port}") == 200
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_insecure_network_bind_still_serves():
    server = create_server(FakeCluster(), "0.0.0.0", 0, allow_insecure=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = server.server_address[1]
    try:
        assert _raw(server, "GET", "/", f"192.168.1.50:{port}") == 200
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_page_forbids_framing(writable):
    request = urllib.request.Request(
        _url(writable, "/"),
        headers={"Authorization": build_auth_header("admin", PASSWORD)},
    )
    with urllib.request.urlopen(request, timeout=5) as response:
        assert response.headers["X-Frame-Options"] == "DENY"
        assert "frame-ancestors 'none'" in response.headers["Content-Security-Policy"]


CONFIG = """# cluster
[[edges]]
name = "edge-a"
api_url = "https://a.invalid"
"""


def test_add_edge_writes_config_and_reloads(tmp_path):
    path = tmp_path / "edges.toml"
    path.write_text(CONFIG, encoding="utf-8")
    cluster = NPSCluster(path)
    server, thread = _serve(cluster)
    try:
        status, body = _post(
            server,
            "/api/actions/edges",
            {
                "name": "edge-b",
                "api_url": "https://b.invalid/",
                "auth_key": "secret-key",
                "region": "EU",
                "ssh_host": "b.example.com",
            },
        )
        duplicate_status, duplicate_body = _post(
            server,
            "/api/actions/edges",
            {"name": "edge-b", "api_url": "https://b2.invalid"},
        )
        bad_status, bad_body = _post(
            server,
            "/api/actions/edges",
            {"name": "edge-c", "api_url": "ftp://c.invalid"},
        )
        assert server.cluster.edge_names == ["edge-a", "edge-b"]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    edges = tomllib.loads(path.read_text(encoding="utf-8"))["edges"]
    assert status == 200
    assert body["results"] == {"edge-b": {"ok": True, "status": "added"}}
    assert "secret-key" not in json.dumps(body)
    assert edges[-1] == {
        "name": "edge-b",
        "api_url": "https://b.invalid",
        "auth_key": "secret-key",
        "region": "EU",
        "ssh_host": "b.example.com",
    }
    assert duplicate_status == 400
    assert "already exists" in duplicate_body["error"]
    assert bad_status == 400
    assert "api_url" in bad_body["error"]
    assert [edge["name"] for edge in edges] == ["edge-a", "edge-b"]


def test_edit_client_preserves_credentials(writable, monkeypatch):
    current = {
        "Id": 1,
        "Remark": "alpha",
        "VerifyKey": "vkey-secret",
        "RateLimit": 10,
        "MaxConn": 5,
        "WebUserName": "wu",
        "WebPassword": "wp",
        "Cnf": {"U": "bu", "P": "bp"},
    }
    calls = {}
    monkeypatch.setattr(client_mgmt, "get_client", lambda nps, cid: current)

    def fake_edit(nps, client_id, **kwargs):
        calls["id"] = client_id
        calls.update(kwargs)
        return True

    monkeypatch.setattr(client_mgmt, "edit_client", fake_edit)

    status, body = _post(
        writable,
        "/api/actions/clients/edit",
        {"edge": "edge-a", "id": 1, "remark": "beta", "vkey": ""},
    )

    assert status == 200
    assert body["results"]["edge-a"] == {"ok": True, "status": "updated"}
    assert calls == {
        "id": 1,
        "remark": "beta",
        "vkey": "vkey-secret",
        "basic_username": "bu",
        "basic_password": "bp",
        "rate_limit": 10,
        "max_conn": 5,
        "web_username": "wu",
        "web_password": "wp",
    }


def test_delete_client_requires_existing_item(writable, monkeypatch):
    calls = []
    monkeypatch.setattr(
        client_mgmt, "get_client", lambda nps, cid: {"Id": cid} if cid == 1 else None
    )
    monkeypatch.setattr(
        client_mgmt, "del_client", lambda nps, cid: calls.append(cid) or True
    )

    status, body = _post(
        writable, "/api/actions/clients/delete", {"edge": "edge-a", "id": 1}
    )
    missing_status, missing_body = _post(
        writable, "/api/actions/clients/delete", {"edge": "edge-a", "id": 2}
    )

    assert status == 200
    assert body["results"]["edge-a"] == {"ok": True, "status": "deleted"}
    assert calls == [1]
    assert missing_status == 400
    assert "not found" in missing_body["error"]


def test_edit_tunnel_preserves_password_and_flags(writable, monkeypatch):
    current = {
        "Id": 7,
        "Mode": "mixProxy",
        "Port": 1080,
        "Password": "pw",
        "Target": {"TargetStr": "127.0.0.1:1080"},
        "Client": {"Id": 1},
        "UserAuth": {"Content": "u=p"},
        "Socks5Proxy": True,
        "HttpProxy": False,
    }
    calls = {}
    monkeypatch.setattr(tunnel_mod, "get_tunnel", lambda nps, tid: current)

    def fake_edit(nps, tunnel_id, **kwargs):
        calls["id"] = tunnel_id
        calls.update(kwargs)
        return True

    monkeypatch.setattr(tunnel_mod, "edit_tunnel", fake_edit)

    status, body = _post(
        writable,
        "/api/actions/tunnels/edit",
        {
            "edge": "edge-a",
            "id": 7,
            "remark": "new",
            "port": 1081,
            "target": "127.0.0.1:8080",
        },
    )

    assert status == 200
    assert body["results"]["edge-a"] == {"ok": True, "status": "updated"}
    assert calls["id"] == 7
    assert calls["tunnel_type"] == "mixProxy"
    assert calls["port"] == 1081
    assert calls["target"] == "127.0.0.1:8080"
    assert calls["remark"] == "new"
    assert calls["password"] == "pw"
    assert calls["auth"] == "u=p"
    assert calls["enable_socks5"] is True
    assert calls["enable_http"] is False


def test_delete_tunnel_missing_item_is_bad_request(writable, monkeypatch):
    monkeypatch.setattr(tunnel_mod, "get_tunnel", lambda nps, tid: None)

    status, body = _post(
        writable, "/api/actions/tunnels/delete", {"edge": "edge-a", "id": 99}
    )

    assert status == 400
    assert "not found" in body["error"]


def test_edit_host_preserves_unedited_fields(writable, monkeypatch):
    current = {
        "Id": 2,
        "Host": "app.example.com",
        "Location": "/api",
        "Scheme": "https",
        "HeaderChange": "X-Test: 1",
        "HostChange": "example",
        "Remark": "old",
        "Client": {"Id": 1},
        "Target": {"TargetStr": "127.0.0.1:9000"},
        "UserAuth": {"Content": "u=p"},
    }
    calls = {}
    monkeypatch.setattr(host_mod, "get_host", lambda nps, hid: current)

    def fake_edit(nps, host_id, **kwargs):
        calls["id"] = host_id
        calls.update(kwargs)
        return True

    monkeypatch.setattr(host_mod, "edit_host", fake_edit)

    status, body = _post(
        writable,
        "/api/actions/hosts/edit",
        {
            "edge": "edge-a",
            "id": 2,
            "host": "new.example.com",
            "target": "127.0.0.1:9001",
            "location": "/api",
            "remark": "new",
            "scheme": "https",
        },
    )

    assert status == 200
    assert body["results"]["edge-a"] == {"ok": True, "status": "updated"}
    assert calls["id"] == 2
    assert calls["client_id"] == 1
    assert calls["host"] == "new.example.com"
    assert calls["target"] == "127.0.0.1:9001"
    assert calls["location"] == "/api"
    assert calls["scheme"] == "https"
    assert calls["header_change"] == "X-Test: 1"
    assert calls["host_change"] == "example"
    assert calls["auth"] == "u=p"


def test_mutations_validate_edge_and_id(writable):
    unknown_status, _ = _post(
        writable,
        "/api/actions/clients/delete",
        {"edge": "nope", "id": 1},
    )
    id_status, id_body = _post(
        writable,
        "/api/actions/clients/delete",
        {"edge": "edge-a", "id": 0},
    )

    assert unknown_status == 400
    assert id_status == 400
    assert "'id'" in id_body["error"]


def test_edit_tunnel_keeps_existing_zero_port(writable, monkeypatch):
    current = {
        "Id": 8,
        "Mode": "httpProxy",
        "Port": 0,
        "Password": "",
        "Target": {"TargetStr": ""},
        "Client": {"Id": 1},
        "UserAuth": {"Content": ""},
    }
    calls = {}
    monkeypatch.setattr(tunnel_mod, "get_tunnel", lambda nps, tid: current)
    monkeypatch.setattr(
        tunnel_mod,
        "edit_tunnel",
        lambda nps, tid, **kwargs: calls.update(kwargs) or True,
    )

    status, body = _post(
        writable,
        "/api/actions/tunnels/edit",
        {"edge": "edge-a", "id": 8, "remark": "renamed"},
    )

    assert status == 200
    assert body["results"]["edge-a"] == {"ok": True, "status": "updated"}
    assert calls["port"] == 0


def test_edit_tunnel_rejects_clearing_a_port(writable, monkeypatch):
    current = {
        "Id": 8,
        "Mode": "httpProxy",
        "Port": 1080,
        "Password": "",
        "Target": {"TargetStr": ""},
        "Client": {"Id": 1},
        "UserAuth": {"Content": ""},
    }
    monkeypatch.setattr(tunnel_mod, "get_tunnel", lambda nps, tid: current)
    monkeypatch.setattr(
        tunnel_mod, "edit_tunnel", lambda *a, **k: pytest.fail("should not edit")
    )

    status, body = _post(
        writable,
        "/api/actions/tunnels/edit",
        {"edge": "edge-a", "id": 8, "port": 0},
    )

    assert status == 400
    assert "port" in body["error"]


def test_delete_requires_a_second_click():
    from nps_ctl.web import _DASHBOARD_HTML

    assert "kind === 'delete' ? 'Delete permanently' : 'Apply'" in _DASHBOARD_HTML
    assert "if (kind === 'edit' && !confirming)" not in _DASHBOARD_HTML
    assert "if (!confirming) {" in _DASHBOARD_HTML


def test_reload_cleans_up_replaced_clients(tmp_path, monkeypatch):
    path = tmp_path / "edges.toml"
    path.write_text(CONFIG, encoding="utf-8")
    cluster = NPSCluster(path)
    old = cluster._clients["edge-a"]
    cleaned = []
    monkeypatch.setattr(old, "cleanup", lambda: cleaned.append(True))

    cluster.reload()

    assert cleaned == [True]
    assert cluster._clients["edge-a"] is not old
