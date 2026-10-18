"""Tests for HTTP Basic Auth on tunnels."""

from __future__ import annotations

from nps_ctl import tunnel
from nps_ctl.cli.cmd_tunnels import _apply_tunnel_edit
from nps_ctl.cli.parser import create_parser


class FakeNPS:
    """Capture request payloads and report success."""

    def __init__(self):
        self.requests = []

    def request(self, path, method="POST", data=None):
        self.requests.append((path, data or {}))
        return {"status": 1}


def test_add_tunnel_sends_auth():
    nps = FakeNPS()

    assert tunnel.add_tunnel(
        nps,
        client_id=1,
        tunnel_type="tcp",
        port=8080,
        target="127.0.0.1:80",
        auth="admin=secret",
    )

    assert nps.requests[0][1]["auth"] == "admin=secret"


def test_edit_tunnel_sends_auth():
    nps = FakeNPS()

    assert tunnel.edit_tunnel(
        nps,
        tunnel_id=7,
        client_id=1,
        tunnel_type="tcp",
        port=8080,
        target="127.0.0.1:80",
        auth="admin=secret",
    )

    assert nps.requests[0][1]["auth"] == "admin=secret"


def test_tunnel_edit_preserves_existing_auth():
    nps = FakeNPS()
    current = {
        "Id": 7,
        "Port": 8080,
        "Mode": "tcp",
        "Remark": "web",
        "Target": {"TargetStr": "127.0.0.1:80"},
        "Client": {"Id": 1},
        "UserAuth": {"Content": "admin=secret"},
    }

    assert _apply_tunnel_edit(nps, 7, current, None, None, "web-v2")

    assert nps.requests[0][1]["auth"] == "admin=secret"


def test_tunnel_edit_can_replace_and_clear_auth():
    nps = FakeNPS()
    current = {
        "Id": 7,
        "Port": 8080,
        "Mode": "tcp",
        "Remark": "web",
        "Target": {"TargetStr": "127.0.0.1:80"},
        "Client": {"Id": 1},
        "UserAuth": {"Content": "admin=secret"},
    }

    assert _apply_tunnel_edit(nps, 7, current, None, None, None, "new=pass")
    assert _apply_tunnel_edit(nps, 7, current, None, None, None, "")

    assert nps.requests[0][1]["auth"] == "new=pass"
    assert nps.requests[1][1]["auth"] == ""


def test_tunnel_add_and_edit_parsers_accept_auth():
    parser = create_parser()

    add_args = parser.parse_args(
        ["tunnel", "add", "-c", "my-server", "-a", "--auth", "u=p"]
    )
    edit_args = parser.parse_args(
        ["tunnel", "edit", "--id", "5", "-e", "nps-us", "--auth", "u=p"]
    )

    assert add_args.auth == "u=p"
    assert edit_args.auth == "u=p"
