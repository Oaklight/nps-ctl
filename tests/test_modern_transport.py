"""Tests for modern API detection and token handling."""

from __future__ import annotations

import json

import nps_ctl.base as base


class FakeResponse:
    """Minimal context-manager HTTP response."""

    def __init__(self, payload):
        self.payload = json.dumps(payload).encode()

    def read(self):
        return self.payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def test_detect_modern_requires_health_payload(monkeypatch):
    client = base.NPSClient(
        base_url="https://nps.example.com",
        auth_key="key",
        username="admin",
        password="secret",
    )
    monkeypatch.setattr(
        base.urllib.request,
        "urlopen",
        lambda *args, **kwargs: FakeResponse({"data": {"ok": True}}),
    )
    assert client._detect_modern() is True

    monkeypatch.setattr(
        base.urllib.request,
        "urlopen",
        lambda *args, **kwargs: FakeResponse({"data": {"status": "ok"}}),
    )
    assert client._detect_modern() is False


def test_bearer_token_reads_nested_access_token():
    client = base.NPSClient(
        base_url="https://nps.example.com",
        auth_key="key",
        username="admin",
        password="secret",
    )
    client._request_with_retry = lambda *args, **kwargs: json.dumps(
        {"data": {"access_token": "token-123", "token_type": "Bearer"}}
    ).encode()

    assert client._get_bearer_token() == "token-123"


def _start_recorded_server(records, payloads):
    """Run an HTTP server that records requests and returns recorded bodies."""
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    class Handler(BaseHTTPRequestHandler):
        def _reply(self, status, payload):
            body = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            records.append(("GET", self.path, self.headers.get("X-Node-Token"), None))
            payload, status = payloads.get(self.path, ({"error": "not found"}, 404))
            self._reply(status, payload)

        def do_POST(self):
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length).decode()
            records.append(
                (
                    "POST",
                    self.path,
                    self.headers.get("X-Node-Token"),
                    json.loads(body) if body else None,
                )
            )
            payload, status = payloads.get(self.path, ({"error": "not found"}, 404))
            self._reply(status, payload)

        def log_message(self, format, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def test_modern_requests_match_recorded_http_contract():
    """Drive the client over real HTTP against captured 0.35.0 payloads."""
    from nps_ctl import host

    host_item = {
        "id": 7,
        "host": "app.example.com",
        "target": "127.0.0.1:8080",
        "auth": "admin=secret",
        "client": {"id": 1, "remark": "server"},
    }
    payloads = {
        "/api/hosts/7": ({"data": host_item, "meta": {"generated_at": 1}}, 200),
        "/api/hosts?offset=0&limit=100": (
            {
                "data": [host_item],
                "meta": {
                    "pagination": {
                        "offset": 0,
                        "limit": 100,
                        "returned": 1,
                        "total": 1,
                        "has_more": False,
                    }
                },
            },
            200,
        ),
        "/api/hosts/7/actions/update": (
            {"data": host_item, "meta": {"generated_at": 2}},
            200,
        ),
    }
    records = []
    server, thread = _start_recorded_server(records, payloads)
    try:
        client = base.NPSClient(
            base_url=f"http://127.0.0.1:{server.server_address[1]}",
            platform_token="platform-token",
            api_mode="modern",
        )

        assert host.get_host(client, 7)["Host"] == "app.example.com"
        assert len(host.list_hosts(client)) == 1
        assert host.edit_host(
            client,
            host_id=7,
            client_id=1,
            host="app.example.com",
            target="127.0.0.1:8080",
            auth="admin=secret",
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert [(method, path) for method, path, _, _ in records] == [
        ("GET", "/api/hosts/7"),
        ("GET", "/api/hosts?offset=0&limit=100"),
        ("POST", "/api/hosts/7/actions/update"),
    ]
    assert all(token == "platform-token" for _, _, token, _ in records)
    assert records[2][3]["auth"] == "admin=secret"
    assert records[2][3]["host"] == "app.example.com"
