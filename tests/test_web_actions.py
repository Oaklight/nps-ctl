"""Tests for the dashboard write endpoints."""

from __future__ import annotations

import html
import json
import threading
import urllib.error
import urllib.request

import pytest

from nps_ctl import client_mgmt
from nps_ctl import host as host_mod
from nps_ctl.web import build_auth_header, create_server
from tests.test_web import FakeCluster, FakeNPS


def _serve(cluster, allow_writes=True):
    server = create_server(
        cluster,
        "127.0.0.1",
        0,
        username="admin",
        password="secret",
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
        "Authorization": build_auth_header("admin", "secret"),
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
        headers={"Authorization": build_auth_header("admin", "secret")},
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
    assert calls == {"source": "edge-a", "targets": ["edge-b", "edge-c"]}
    assert body["results"]["edge-b"]["ok"] is True
    assert body["results"]["edge-c"] == {
        "ok": False,
        "status": "2 checked",
        "failed": ["host:y"],
    }
    assert empty_status == 400


def test_writes_require_auth_on_public_bind():
    with pytest.raises(ValueError, match="enable writes"):
        create_server(
            FakeCluster(), "0.0.0.0", 0, allow_insecure=True, allow_writes=True
        )


def _raw(server, method, path, host, body=None):
    import http.client

    conn = http.client.HTTPConnection(*server.server_address[:2], timeout=5)
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


def test_page_forbids_framing(writable):
    request = urllib.request.Request(
        _url(writable, "/"),
        headers={"Authorization": build_auth_header("admin", "secret")},
    )
    with urllib.request.urlopen(request, timeout=5) as response:
        assert response.headers["X-Frame-Options"] == "DENY"
        assert "frame-ancestors 'none'" in response.headers["Content-Security-Policy"]
