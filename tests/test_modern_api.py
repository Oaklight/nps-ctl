"""Tests for modern /api/* dispatch and normalization."""

from __future__ import annotations

from nps_ctl import client_mgmt, host, tunnel


class ModernNPS:
    """Capture modern API calls and return a successful envelope."""

    is_modern = True

    def __init__(self, item=None, items=None):
        self.item = item
        self.items = items or []
        self.calls = []

    def api_request(self, method, path, params=None, data=None):
        self.calls.append((method, path, params or {}, data or {}))
        if method == "GET" and self.item is not None:
            return {"data": self.item}
        return {
            "data": self.items,
            "meta": {"pagination": {"total": len(self.items)}},
        }


def test_host_crud_uses_modern_paths_and_fields():
    nps = ModernNPS()

    assert host.add_host(
        nps,
        client_id=1,
        host="app.example.com",
        target="127.0.0.1:8080",
        header_change="X-Test: 1",
        host_change="old.example.com",
        auth="admin=secret",
    )
    assert host.edit_host(
        nps,
        host_id=7,
        client_id=1,
        host="app.example.com",
        target="127.0.0.1:9090",
        auth="admin=new",
    )
    assert host.del_host(nps, host_id=7)

    add_call, edit_call, del_call = nps.calls
    assert add_call[:2] == ("POST", "/api/hosts")
    assert add_call[3]["header"] == "X-Test: 1"
    assert add_call[3]["host_change"] == "old.example.com"
    assert add_call[3]["auth"] == "admin=secret"
    assert edit_call[:2] == ("POST", "/api/hosts/7/actions/update")
    assert edit_call[3]["auth"] == "admin=new"
    assert del_call[:2] == ("POST", "/api/hosts/7/actions/delete")


def test_host_get_normalizes_modern_response():
    nps = ModernNPS(
        item={
            "id": 7,
            "host": "app.example.com",
            "target": "127.0.0.1:8080",
            "header": "X-Test: 1",
            "host_change": "old.example.com",
            "auth": "admin=secret",
            "client": {"id": 1, "remark": "server", "is_connect": True},
        }
    )

    result = host.get_host(nps, 7)

    assert nps.calls[0][:2] == ("GET", "/api/hosts/7")
    assert result is not None
    assert result["Host"] == "app.example.com"
    assert result["Target"]["TargetStr"] == "127.0.0.1:8080"
    assert result["HeaderChange"] == "X-Test: 1"
    assert result["HostChange"] == "old.example.com"
    assert result["UserAuth"]["Content"] == "admin=secret"
    assert result["Client"]["Remark"] == "server"


def test_client_crud_uses_modern_paths_and_fields():
    nps = ModernNPS()

    assert client_mgmt.add_client(
        nps,
        remark="server",
        vkey="key-1",
        basic_username="user",
        basic_password="pass",
        rate_limit=10,
        max_conn=50,
    )
    assert client_mgmt.edit_client(
        nps,
        client_id=3,
        remark="server-v2",
        vkey="key-1",
        rate_limit=20,
    )
    assert client_mgmt.del_client(nps, client_id=3)

    add_call, edit_call, del_call = nps.calls
    assert add_call[:2] == ("POST", "/api/clients")
    assert add_call[3]["verify_key"] == "key-1"
    assert add_call[3]["username"] == "user"
    assert add_call[3]["password"] == "pass"
    assert add_call[3]["max_connections"] == 50
    assert add_call[3]["rate_limit_total_bps"] == 10 * 1024
    assert edit_call[:2] == ("POST", "/api/clients/3/actions/update")
    assert edit_call[3]["rate_limit_total_bps"] == 20 * 1024
    assert del_call[:2] == ("POST", "/api/clients/3/actions/delete")


def test_tunnel_crud_uses_modern_paths_and_fields():
    nps = ModernNPS()

    assert tunnel.add_tunnel(
        nps,
        client_id=1,
        tunnel_type="tcp",
        port=8080,
        target="127.0.0.1:80",
        remark="web",
    )
    assert tunnel.edit_tunnel(
        nps,
        tunnel_id=9,
        client_id=1,
        tunnel_type="udp",
        port=9090,
        target="127.0.0.1:53",
    )
    assert tunnel.start_tunnel(nps, tunnel_id=9)
    assert tunnel.stop_tunnel(nps, tunnel_id=9)
    assert tunnel.del_tunnel(nps, tunnel_id=9)

    add_call, edit_call, start_call, stop_call, del_call = nps.calls
    assert add_call[:2] == ("POST", "/api/tunnels")
    assert add_call[3]["mode"] == "tcp"
    assert add_call[3]["target"] == "127.0.0.1:80"
    assert edit_call[:2] == ("POST", "/api/tunnels/9/actions/update")
    assert edit_call[3]["mode"] == "udp"
    assert start_call[:2] == ("POST", "/api/tunnels/9/actions/start")
    assert stop_call[:2] == ("POST", "/api/tunnels/9/actions/stop")
    assert del_call[:2] == ("POST", "/api/tunnels/9/actions/delete")


def test_client_get_normalizes_rate_limit_to_kb():
    nps = ModernNPS(
        item={
            "id": 3,
            "remark": "server",
            "rate_limit_total_bps": 20480,
            "max_connections": 50,
            "config_conn_allow": True,
        }
    )

    result = client_mgmt.get_client(nps, 3)

    assert result is not None
    assert result["RateLimit"] == 20
    assert result["MaxConn"] == 50
    assert result["ConfigConnAllow"] is True


def test_tunnel_get_normalizes_modern_response():
    nps = ModernNPS(
        item={
            "id": 9,
            "port": 8080,
            "ports": "8001-8003",
            "mode": "tcp",
            "target": "127.0.0.1:80",
            "remark": "web",
            "service_in_bytes": 12,
            "service_out_bytes": 34,
            "client": {"id": 1, "remark": "server"},
        }
    )

    result = tunnel.get_tunnel(nps, 9)

    assert nps.calls[0][:2] == ("GET", "/api/tunnels/9")
    assert result is not None
    assert result["Mode"] == "tcp"
    assert result["Ports"] == "8001-8003"
    assert result["Target"]["TargetStr"] == "127.0.0.1:80"
    assert result["Flow"]["InletFlow"] == 12
    assert result["Flow"]["ExportFlow"] == 34


class WrappedItemNPS:
    """Serve the single-resource wrapper shape some builds use."""

    is_modern = True

    def __init__(self, item):
        self.item = item

    def api_request(self, method, path, params=None, data=None):
        return {
            "data": {
                "config_epoch": "epoch-1",
                "generated_at": 1792000000,
                "item": self.item,
            }
        }


def test_get_host_accepts_wrapped_item_envelope():
    nps = WrappedItemNPS(
        {
            "id": 7,
            "host": "app.example.com",
            "target": "127.0.0.1:8080",
            "auth": "admin=secret",
            "client": {"id": 1, "remark": "server"},
        }
    )

    result = host.get_host(nps, 7)

    assert result is not None
    assert result["Host"] == "app.example.com"
    assert result["Target"]["TargetStr"] == "127.0.0.1:8080"
    assert result["UserAuth"]["Content"] == "admin=secret"


def test_get_client_accepts_wrapped_item_envelope():
    nps = WrappedItemNPS(
        {
            "id": 3,
            "remark": "server",
            "verify_key": "key-1",
            "rate_limit_total_bps": 20480,
        }
    )

    result = client_mgmt.get_client(nps, 3)

    assert result is not None
    assert result["Id"] == 3
    assert result["Remark"] == "server"
    assert result["VerifyKey"] == "key-1"
    assert result["RateLimit"] == 20


def test_get_tunnel_accepts_wrapped_item_envelope():
    nps = WrappedItemNPS(
        {
            "id": 9,
            "port": 8080,
            "mode": "tcp",
            "target": "127.0.0.1:80",
            "remark": "web",
            "client": {"id": 1, "remark": "server"},
        }
    )

    result = tunnel.get_tunnel(nps, 9)

    assert result is not None
    assert result["Id"] == 9
    assert result["Mode"] == "tcp"
    assert result["Port"] == 8080
    assert result["Target"]["TargetStr"] == "127.0.0.1:80"


def test_tunnel_quotas_map_to_modern_fields():
    nps = ModernNPS()

    assert tunnel.add_tunnel(
        nps,
        client_id=1,
        tunnel_type="tcp",
        port=8080,
        target="127.0.0.1:80",
        flow_limit="100",
        time_limit="30d",
    )
    assert tunnel.edit_tunnel(
        nps,
        tunnel_id=9,
        client_id=1,
        tunnel_type="tcp",
        port=8080,
        target="127.0.0.1:80",
        flow_limit="250",
        time_limit="7d",
    )

    add_call, edit_call = nps.calls
    assert add_call[3]["flow_limit_total_bytes"] == 100 * 1024 * 1024
    assert add_call[3]["expire_at"] == "30d"
    assert edit_call[3]["flow_limit_total_bytes"] == 250 * 1024 * 1024
    assert edit_call[3]["expire_at"] == "7d"
