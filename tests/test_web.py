"""Tests for the read-only web dashboard."""

from __future__ import annotations

import base64
import json
import sys
import threading
import urllib.error
import urllib.request
from types import SimpleNamespace

import pytest

from nps_ctl.types import EdgeResults
from nps_ctl.web import build_auth_header, create_server


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

    def __init__(self, edge_data=None, errors=None):
        self.edge_data = edge_data or {
            "edge-a": FakeNPS(
                clients=[{"Id": 1, "Remark": "alpha", "VerifyKey": "vkey-secret"}],
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
                    }
                ],
                hosts=[{"Id": 2, "Host": "app.example.com"}],
            )
        }
        self.errors = errors or {}
        self.edge_names = list(self.edge_data)

    def get_edge(self, name):
        return SimpleNamespace(region="Asia", api_url=f"https://{name}.invalid")

    def get_client(self, name):
        return self.edge_data.get(name)

    def _results(self, attribute):
        return EdgeResults(
            {name: getattr(nps, attribute) for name, nps in self.edge_data.items()},
            errors=self.errors,
        )

    def get_all_clients(self):
        return self._results("clients")

    def get_all_tunnels(self):
        return self._results("tunnels")

    def get_all_hosts(self):
        return self._results("hosts")


@pytest.fixture
def server():
    dashboard = create_server(
        FakeCluster(), "127.0.0.1", 0, username="admin", password="secret"
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
        headers["Authorization"] = build_auth_header("admin", "secret")
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
        "clients": 1,
        "tunnels": 1,
        "hosts": 1,
    }
    assert payload["edges"][0]["name"] == "edge-a"
    assert payload["edges"][0]["region"] == "Asia"


def test_edge_resources_redact_credentials(server):
    with _get(server, "/api/edges/edge-a/tunnels") as response:
        tunnels = json.load(response)
    with _get(server, "/api/edges/edge-a/clients") as response:
        clients = json.load(response)

    assert tunnels["items"][0]["UserAuth"] == {
        "Content": "**redacted**",
        "AccountMap": {},
    }
    assert tunnels["items"][0]["Password"] == "**redacted**"
    assert clients["items"][0]["VerifyKey"] == "**redacted**"


def test_unknown_edge_returns_404(server):
    with pytest.raises(urllib.error.HTTPError) as excinfo:
        _get(server, "/api/edges/missing/clients")

    assert excinfo.value.code == 404


def test_dashboard_rejects_public_bind_without_auth():
    with pytest.raises(ValueError, match="Refusing to expose"):
        create_server(FakeCluster(), "0.0.0.0", 0)


def test_dashboard_allows_public_bind_with_auth():
    dashboard = create_server(
        FakeCluster(), "0.0.0.0", 0, username="admin", password="secret"
    )
    try:
        expected = base64.b64encode(b"admin:secret").decode()
        assert dashboard.auth_header == f"Basic {expected}"
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
        password="secret",
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
