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
