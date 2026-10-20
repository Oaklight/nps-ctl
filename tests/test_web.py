"""Tests for the read-only web dashboard."""

from __future__ import annotations

import json
import secrets
import sys
import threading
import urllib.error
import urllib.request
from types import SimpleNamespace

import pytest

from nps_ctl.types import EdgeResults
from nps_ctl.web import _DASHBOARD_HTML, _overview, build_auth_header, create_server
from nps_ctl.web_auth import verify_password

PASSWORD = secrets.token_urlsafe(16)


class FakeNPS:
    """Serve legacy list payloads for one edge."""

    is_modern = False

    def __init__(self, clients=None, tunnels=None, hosts=None):
        self.clients = clients or []
        self.tunnels = tunnels or []
        self.hosts = hosts or []

    def request(self, path, method="POST", data=None):
        data = data or {}
        if path == "/client/list":
            rows = self.clients
        elif path == "/index/gettunnel":
            rows = self.tunnels if data.get("type") == "tcp" else []
        elif path == "/index/hostlist":
            rows = self.hosts
        else:
            rows = []
        return {"rows": rows, "total": len(rows)}


class FakeCluster:
    """Cluster stub shared by the dashboard handlers."""

    def __init__(self, edge_data=None, errors=None, tunnel_errors=None):
        self.edge_data = edge_data or {
            "edge-a": FakeNPS(
                clients=[
                    {
                        "Id": 1,
                        "Remark": "alpha",
                        "VerifyKey": "vkey-secret",
                        "WebUserName": "wu",
                        "WebPassword": "web-secret",
                    }
                ],
                tunnels=[
                    {
                        "Id": 7,
                        "Mode": "tcp",
                        "Port": 8080,
                        "Password": "tunnel-secret",
                        "UserAuth": {
                            "Content": "admin=secret",
                            "AccountMap": {"admin": "secret"},
                        },
                        "Client": {
                            "Id": 1,
                            "Remark": "server",
                            "VerifyKey": "client-vkey-secret",
                            "WebUserName": "wu",
                            "WebPassword": "client-web-secret",
                            "Cnf": {"U": "bridge", "P": "bridge-secret"},
                        },
                    }
                ],
                hosts=[
                    {
                        "Id": 2,
                        "Host": "app.example.com",
                        "Client": {
                            "Id": 1,
                            "Remark": "server",
                            "VerifyKey": "client-vkey-secret",
                        },
                    }
                ],
            )
        }
        self.errors = errors or {}
        self.tunnel_errors = tunnel_errors or {}
        self.edge_names = list(self.edge_data)

    def get_edge(self, name):
        return SimpleNamespace(region="Asia", api_url=f"https://{name}.invalid")

    def get_client(self, name):
        return self.edge_data.get(name)

    def _results(self, attribute, edge_names=None, errors=None):
        names = self.edge_names if edge_names is None else edge_names
        active_errors = self.errors if errors is None else errors
        return EdgeResults(
            {name: getattr(self.edge_data[name], attribute) for name in names},
            errors={
                name: active_errors[name] for name in names if name in active_errors
            },
        )

    def get_all_clients(self, edge_names=None, max_workers=4):
        return self._results("clients", edge_names)

    def get_all_tunnels(self, edge_names=None, max_workers=4):
        return self._results("tunnels", edge_names, self.tunnel_errors)

    def get_all_hosts(self, edge_names=None, max_workers=4):
        return self._results("hosts", edge_names)


@pytest.fixture
def server():
    dashboard = create_server(
        FakeCluster(), "127.0.0.1", 0, username="admin", password=PASSWORD
    )
    thread = threading.Thread(target=dashboard.serve_forever, daemon=True)
    thread.start()
    try:
        yield dashboard
    finally:
        dashboard.shutdown()
        dashboard.server_close()
        thread.join(timeout=5)


def _url(server, path):
    host, port = server.server_address[:2]
    return f"http://{host}:{port}{path}"


def _get(server, path, auth=True):
    headers = {}
    if auth:
        headers["Authorization"] = build_auth_header("admin", PASSWORD)
    request = urllib.request.Request(_url(server, path), headers=headers)
    return urllib.request.urlopen(request, timeout=5)


def test_dashboard_requires_basic_auth(server):
    with pytest.raises(urllib.error.HTTPError) as excinfo:
        _get(server, "/api/overview", auth=False)

    assert excinfo.value.code == 401
    assert excinfo.value.headers["WWW-Authenticate"] == 'Basic realm="nps-ctl"'


def test_overview_reports_edges_and_counts(server):
    with _get(server, "/api/overview") as response:
        payload = json.load(response)

    assert payload["summary"] == {
        "edges": 1,
        "online": 1,
        "ok": 1,
        "partial": 0,
        "clients": 1,
        "tunnels": 1,
        "hosts": 1,
        "in_sync": 1,
        "replicated": {"clients": 1, "tunnels": 1, "hosts": 1},
    }
    assert payload["edges"][0]["missing"] == {"clients": 0, "tunnels": 0, "hosts": 0}
    assert payload["edges"][0]["name"] == "edge-a"
    assert payload["edges"][0]["region"] == "Asia"
    assert payload["edges"][0]["online"] is True
    assert payload["edges"][0]["ok"] is True
    assert payload["edges"][0]["partial"] is False
    assert payload["edges"][0]["tunnels_running"] == 0
    assert payload["edges"][0]["tunnel_ports"] == 1


def test_overview_reports_partial_and_null_counts():
    cluster = FakeCluster(
        edge_data={
            "edge-a": FakeNPS(
                clients=[{"Id": 1, "VerifyKey": "vkey-a"}],
                tunnels=[{"Id": 7, "Port": 8080, "RunStatus": True}],
                hosts=[{"Id": 2, "Host": "app.example.com"}],
            ),
            "edge-b": FakeNPS(
                clients=[{"Id": 3, "VerifyKey": "vkey-b"}], tunnels=[], hosts=[]
            ),
        },
        tunnel_errors={"edge-b": "timeout"},
    )

    payload = _overview(cluster)

    assert payload["summary"] == {
        "edges": 2,
        "online": 2,
        "ok": 1,
        "partial": 1,
        "clients": 2,
        "tunnels": 1,
        "hosts": 1,
        "in_sync": 0,
        "replicated": {"clients": 2, "tunnels": None, "hosts": 1},
    }
    assert payload["edges"][0]["missing"] == {"clients": 1, "tunnels": 0, "hosts": 0}
    assert payload["edges"][1]["missing"] == {"clients": 1, "hosts": 1}
    assert payload["edges"][1]["unknown"] == ["tunnels"]
    assert payload["edges"][1]["in_sync"] is False
    edge_b = payload["edges"][1]
    assert edge_b["name"] == "edge-b"
    assert edge_b["online"] is True
    assert edge_b["ok"] is False
    assert edge_b["partial"] is True
    assert edge_b["tunnels"] is None
    assert edge_b["error"] == "tunnels: timeout"


def test_dashboard_summary_renders_ok_and_partial():
    assert "card(s.ok + '/' + s.edges, 'edges ok')" in _DASHBOARD_HTML
    assert (
        "if (s.partial) cards.splice(1, 0, card(s.partial, 'partial'));"
        in _DASHBOARD_HTML
    )


def test_edge_resources_redact_credentials(server):
    with _get(server, "/api/edges/edge-a/tunnels") as response:
        tunnels = json.load(response)
    with _get(server, "/api/edges/edge-a/clients") as response:
        clients = json.load(response)
    with _get(server, "/api/edges/edge-a/hosts") as response:
        hosts = json.load(response)

    assert tunnels["items"][0]["UserAuth"] == {
        "Content": "**redacted**",
        "AccountMap": {},
    }
    assert tunnels["items"][0]["Password"] == "**redacted**"
    assert clients["items"][0]["VerifyKey"] == "**redacted**"
    assert clients["items"][0]["WebPassword"] == "**redacted**"

    nested = tunnels["items"][0]["Client"]
    assert nested["VerifyKey"] == "**redacted**"
    assert nested["WebPassword"] == "**redacted**"
    assert nested["Cnf"]["P"] == "**redacted**"
    assert nested["WebUserName"] == "wu"
    assert hosts["items"][0]["Client"]["VerifyKey"] == "**redacted**"

    for payload in (tunnels, clients, hosts):
        body = json.dumps(payload)
        for secret in (
            "vkey-secret",
            "web-secret",
            "tunnel-secret",
            "admin=secret",
            "client-vkey-secret",
            "client-web-secret",
            "bridge-secret",
        ):
            assert secret not in body


def test_unknown_edge_returns_404(server):
    with pytest.raises(urllib.error.HTTPError) as excinfo:
        _get(server, "/api/edges/missing/clients")

    assert excinfo.value.code == 404


def test_dashboard_rejects_public_bind_without_auth():
    with pytest.raises(ValueError, match="Refusing to expose"):
        create_server(FakeCluster(), "0.0.0.0", 0)


def test_dashboard_rejects_username_without_password():
    with pytest.raises(ValueError, match="requires a non-empty password"):
        create_server(FakeCluster(), "127.0.0.1", 0, username="admin", password="")


def test_dashboard_allows_public_bind_with_auth():
    dashboard = create_server(
        FakeCluster(), "0.0.0.0", 0, username="admin", password=PASSWORD
    )
    try:
        user = dashboard.users["admin"]
        assert user.role == "operator"
        assert verify_password(PASSWORD, user.password_hash)
        assert not verify_password(PASSWORD + "-wrong", user.password_hash)
    finally:
        dashboard.server_close()


def test_web_routes_through_main(monkeypatch, tmp_path):
    import nps_ctl.cli as cli
    import nps_ctl.cli.cmd_web as cmd_web_module

    called = {}

    def fake_cmd_web(args):
        called["args"] = args
        return 0

    monkeypatch.setattr(cmd_web_module, "cmd_web", fake_cmd_web)
    config = tmp_path / "edges.toml"
    config.write_text("")
    monkeypatch.setattr(
        sys,
        "argv",
        ["nps-ctl", "--config", str(config), "web", "--port", "8799"],
    )

    assert cli.main() == 0
    assert called["args"].command == "web"
    assert called["args"].leaf_command is True


def test_web_rejects_password_without_username(monkeypatch):
    import nps_ctl.cli.cmd_web as cmd_web_module

    monkeypatch.setattr(cmd_web_module, "NPSCluster", lambda config: object())
    args = SimpleNamespace(
        config="ignored",
        host="127.0.0.1",
        port=0,
        username="",
        password=PASSWORD,
        insecure=False,
    )

    assert cmd_web_module.cmd_web(args) == 2


def test_web_reports_missing_password_without_tty(monkeypatch):
    import nps_ctl.cli.cmd_web as cmd_web_module

    monkeypatch.setattr(cmd_web_module, "NPSCluster", lambda config: object())
    monkeypatch.delenv("NPS_WEB_PASSWORD", raising=False)

    def no_tty(prompt):
        raise EOFError

    monkeypatch.setattr(cmd_web_module.getpass, "getpass", no_tty)
    args = SimpleNamespace(
        config="ignored",
        host="127.0.0.1",
        port=0,
        username="admin",
        password="",
        insecure=False,
    )

    assert cmd_web_module.cmd_web(args) == 2


def test_web_rejects_empty_password_from_prompt(monkeypatch):
    import nps_ctl.cli.cmd_web as cmd_web_module

    monkeypatch.setattr(cmd_web_module, "NPSCluster", lambda config: object())
    monkeypatch.delenv("NPS_WEB_PASSWORD", raising=False)
    monkeypatch.setattr(cmd_web_module.getpass, "getpass", lambda prompt: "")
    args = SimpleNamespace(
        config="ignored",
        host="127.0.0.1",
        port=0,
        username="admin",
        password="",
        insecure=False,
    )

    assert cmd_web_module.cmd_web(args) == 2


def test_unauthorized_response_has_security_headers(server):
    with pytest.raises(urllib.error.HTTPError) as excinfo:
        _get(server, "/", auth=False)

    headers = excinfo.value.headers
    assert headers["X-Content-Type-Options"] == "nosniff"
    assert "default-src 'none'" in headers["Content-Security-Policy"]
