"""Tests for dashboard users, password hashing, and role enforcement."""

from __future__ import annotations

import json
import secrets
import threading
import urllib.error
import urllib.request
from types import SimpleNamespace

import pytest

from nps_ctl import client_mgmt
from nps_ctl.cli.cmd_utils import cmd_hash_password
from nps_ctl.web import build_auth_header, create_server
from nps_ctl.web_auth import (
    hash_password,
    load_users_file,
    users_from_credentials,
    verify_password,
)
from tests.test_web import FakeCluster

VIEWER_PASSWORD = secrets.token_urlsafe(16)
OPERATOR_PASSWORD = secrets.token_urlsafe(16)
PROBE = secrets.token_urlsafe(12)


def _write_users(tmp_path):
    path = tmp_path / "users.toml"
    path.write_text(
        "[[users]]\n"
        'name = "viewer"\n'
        f'password_hash = "{hash_password(VIEWER_PASSWORD)}"\n'
        'role = "viewer"\n'
        "\n"
        "[[users]]\n"
        'name = "operator"\n'
        f'password_hash = "{hash_password(OPERATOR_PASSWORD)}"\n'
        'role = "operator"\n',
        encoding="utf-8",
    )
    path.chmod(0o600)
    return path


def test_hash_roundtrip_and_wrong_password():
    encoded = hash_password(PROBE)
    assert encoded.startswith("pbkdf2_sha256$")
    assert verify_password(PROBE, encoded)
    assert not verify_password(PROBE + "-wrong", encoded)


def test_verify_rejects_malformed_hashes():
    assert not verify_password(PROBE, "")
    assert not verify_password(PROBE, "sha256$1$abc")
    assert not verify_password(PROBE, "pbkdf2_sha256$1$abc$def")
    assert not verify_password(PROBE, "pbkdf2_sha256$999999999$YWJj$YWJj")


def test_hash_password_rejects_empty_and_bad_iterations():
    with pytest.raises(ValueError, match="empty"):
        hash_password("")
    with pytest.raises(ValueError, match="iterations"):
        hash_password(PROBE, iterations=1)


def test_load_users_file(tmp_path):
    users = load_users_file(_write_users(tmp_path))

    assert list(users) == ["viewer", "operator"]
    assert users["viewer"].role == "viewer"
    assert not users["viewer"].can_write
    assert users["operator"].can_write
    assert verify_password(VIEWER_PASSWORD, users["viewer"].password_hash)


def test_load_users_file_rejects_invalid_entries(tmp_path):
    bad_hash = tmp_path / "bad.toml"
    bad_hash.write_text(
        '[[users]]\nname = "a"\npassword_hash = "nope"\n', encoding="utf-8"
    )
    with pytest.raises(ValueError, match="invalid password_hash"):
        load_users_file(bad_hash)

    bad_role = tmp_path / "role.toml"
    bad_role.write_text(
        "[[users]]\n"
        'name = "a"\n'
        f'password_hash = "{hash_password(PROBE)}"\n'
        'role = "root"\n',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="invalid role"):
        load_users_file(bad_role)

    duplicate = tmp_path / "dup.toml"
    duplicate.write_text(
        "[[users]]\n"
        'name = "a"\n'
        f'password_hash = "{hash_password(PROBE)}"\n'
        "[[users]]\n"
        'name = "a"\n'
        f'password_hash = "{hash_password(PROBE + "-2")}"\n',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="duplicate user"):
        load_users_file(duplicate)


def test_users_from_credentials_is_operator():
    users = users_from_credentials("admin", PROBE)

    assert users["admin"].role == "operator"
    assert verify_password(PROBE, users["admin"].password_hash)


def _serve(cluster, users):
    server = create_server(cluster, "127.0.0.1", 0, users=users, allow_writes=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def _request(server, path, *, username=None, password=None, payload=None):
    headers = {}
    if username is not None and password is not None:
        headers["Authorization"] = build_auth_header(username, password)
    data = None
    if payload is not None:
        headers["Content-Type"] = "application/json"
        headers["X-CSRF-Token"] = server.csrf_token
        data = json.dumps(payload).encode()
    request = urllib.request.Request(
        f"http://{server.server_address[0]}:{server.server_address[1]}{path}",
        data=data,
        headers=headers,
    )
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status, response.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()


def test_viewer_is_read_only_and_operator_can_write(tmp_path, monkeypatch):
    users = load_users_file(_write_users(tmp_path))
    monkeypatch.setattr(client_mgmt, "add_client", lambda *a, **k: True)
    server, thread = _serve(FakeCluster(), users)
    try:
        viewer_page_status, viewer_page = _request(
            server, "/", username="viewer", password=VIEWER_PASSWORD
        )
        operator_page_status, operator_page = _request(
            server, "/", username="operator", password=OPERATOR_PASSWORD
        )
        viewer_post_status, viewer_post = _request(
            server,
            "/api/actions/clients",
            username="viewer",
            password=VIEWER_PASSWORD,
            payload={"remark": "beta", "edges": ["edge-a"]},
        )
        operator_post_status, _ = _request(
            server,
            "/api/actions/clients",
            username="operator",
            password=OPERATOR_PASSWORD,
            payload={"remark": "beta", "edges": ["edge-a"]},
        )
        wrong_password_status, _ = _request(
            server, "/", username="viewer", password=PROBE + "-wrong"
        )
        anonymous_status, _ = _request(server, "/")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert viewer_page_status == 200
    assert '"writes": false' in viewer_page.replace("&quot;", '"')
    assert server.csrf_token not in viewer_page
    assert operator_page_status == 200
    assert '"writes": true' in operator_page.replace("&quot;", '"')
    assert server.csrf_token in operator_page
    assert viewer_post_status == 403
    assert "viewer" in viewer_post
    assert operator_post_status == 200
    assert wrong_password_status == 401
    assert anonymous_status == 401


def test_users_file_and_single_user_are_mutually_exclusive(tmp_path):
    users = load_users_file(_write_users(tmp_path))
    with pytest.raises(ValueError, match="not both"):
        create_server(
            FakeCluster(),
            "127.0.0.1",
            0,
            username="admin",
            password=PROBE,
            users=users,
        )


def test_hash_password_command_uses_env_and_prints_hash(monkeypatch, capsys):
    monkeypatch.setenv("NPS_WEB_PASSWORD", PROBE)

    code = cmd_hash_password(SimpleNamespace(iterations=10_000))
    output = capsys.readouterr().out.strip()

    assert code == 0
    assert output.startswith("pbkdf2_sha256$10000$")
    assert verify_password(PROBE, output)
