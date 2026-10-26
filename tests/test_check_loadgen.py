"""Tests for the echo service and the self-verifying load generator."""

from __future__ import annotations

import ast
import http.client
import json
import socket
import sys
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

from nps_ctl.check import echo_server, loadgen
from nps_ctl.check.echo_server import Digest, Handler
from nps_ctl.check.loadgen import classify, expected_digest, make_body, run


@pytest.fixture
def echo():
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server.server_address[1]
    server.shutdown()
    server.server_close()


class FaultProxy:
    """TCP proxy that damages request bytes on their way to the echo service."""

    def __init__(self, upstream_port: int, fault: str, after: int = 70000):
        self.upstream_port = upstream_port
        self.fault = fault
        self.after = after
        self.listener = socket.socket()
        self.listener.bind(("127.0.0.1", 0))
        self.listener.listen(64)
        self.port = self.listener.getsockname()[1]
        threading.Thread(target=self._accept, daemon=True).start()

    def close(self):
        self.listener.close()

    def _accept(self):
        while True:
            try:
                client, _ = self.listener.accept()
            except OSError:
                return
            threading.Thread(target=self._serve, args=(client,), daemon=True).start()

    def _serve(self, client):
        upstream = socket.create_connection(("127.0.0.1", self.upstream_port))
        threading.Thread(
            target=self._pump_back, args=(upstream, client), daemon=True
        ).start()
        sent = 0
        try:
            while data := client.recv(65536):
                if self.fault == "flip" and sent <= self.after < sent + len(data):
                    at = self.after - sent
                    data = data[:at] + bytes([data[at] ^ 0xFF]) + data[at + 1 :]
                if self.fault == "truncate" and sent + len(data) > self.after:
                    upstream.sendall(data[: max(0, self.after - sent)])
                    upstream.shutdown(socket.SHUT_WR)
                    return
                upstream.sendall(data)
                sent += len(data)
            upstream.shutdown(socket.SHUT_WR)
        except OSError:
            pass

    @staticmethod
    def _pump_back(upstream, client):
        try:
            while data := upstream.recv(65536):
                client.sendall(data)
        except OSError:
            pass
        finally:
            client.close()


def _spec(port, **overrides):
    return {"port": port, "size": 200_000, "count": 12, "concurrency": 4, **overrides}


def test_make_body_is_deterministic_and_unique_per_request():
    assert make_body("s", 3, 1000) == make_body("s", 3, 1000)
    assert make_body("s", 3, 1000) != make_body("s", 4, 1000)
    assert make_body("a", 3, 1000) != make_body("b", 3, 1000)
    assert len(make_body("s", 0, 123457)) == 123457


def test_digest_matches_the_locally_expected_answer():
    body = make_body("s", 1, 200_001)
    digest = Digest()
    for offset in range(0, len(body), 7777):
        digest.update(body[offset : offset + 7777])

    got = digest.result(short=False)

    assert got["sha256"] == expected_digest(body)["sha256"]
    assert got["blocks"] == expected_digest(body)["blocks"]
    assert len(got["blocks"]) == 4


def test_classify_names_each_failure_shape():
    want = expected_digest(b"x" * 200_000)

    assert classify(want, {**want}) == ("ok", "")
    assert classify(want, {"len": 100, "sha256": "x", "blocks": []})[0] == "truncated"
    assert classify(want, {**want, "len": 5, "short": True})[0] == "truncated"
    assert (
        classify(want, {"len": 200_001, "sha256": "x", "blocks": []})[0] == "extended"
    )
    corrupt = {**want, "sha256": "x", "blocks": ["bad"] + want["blocks"][1:]}
    outcome, detail = classify(want, corrupt)
    assert outcome == "corrupt" and "block 0" in detail


def test_healthy_path_reports_every_request_ok(echo):
    result = run(_spec(echo))

    assert result["total"] == 12
    assert result["outcomes"] == {"ok": 12}
    assert result["failures"] == []
    assert result["failure_times"] == []
    assert result["p50_ms"] is not None


def test_slow_mode_still_delivers_intact_bodies(echo):
    result = run(_spec(echo, mode="slow", size=64_000, chunk_kb=16, gap_ms=1, count=6))

    assert result["outcomes"] == {"ok": 6}


def test_duration_mode_stops_on_time(echo):
    result = run(_spec(echo, duration=0.4, count=0, size=2000, concurrency=2))

    assert result["total"] >= 2
    assert set(result["outcomes"]) == {"ok"}


def test_a_flipped_byte_is_reported_as_corrupt_with_its_block(echo):
    proxy = FaultProxy(echo, "flip", after=70_000)
    try:
        result = run(_spec(proxy.port, count=6))
    finally:
        proxy.close()

    assert result["outcomes"] == {"corrupt": 6}
    assert "block 1" in result["failures"][0]["detail"]


def test_a_cut_stream_is_reported_as_truncated(echo):
    proxy = FaultProxy(echo, "truncate", after=50_000)
    try:
        result = run(_spec(proxy.port, count=6))
    finally:
        proxy.close()

    assert result["outcomes"] == {"truncated": 6}
    assert len(result["failure_times"]) == 6


def test_a_closed_port_is_a_connection_error():
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()

    result = run(_spec(port, count=3, size=1000, timeout=2))

    assert result["outcomes"] == {"conn_error": 3}


def test_a_silent_server_is_a_timeout():
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(8)
    try:
        result = run(_spec(listener.getsockname()[1], count=2, size=1000, timeout=0.3))
    finally:
        listener.close()

    assert result["outcomes"] == {"timeout": 2}


def test_non_200_answers_are_http_errors():
    class Refuse(Handler):
        def do_POST(self):  # noqa: N802
            self.send_response(404)
            self.send_header("Content-Length", "9")
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(b"not found")

    server = ThreadingHTTPServer(("127.0.0.1", 0), Refuse)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        result = run(_spec(server.server_address[1], count=2, size=1000))
    finally:
        server.shutdown()
        server.server_close()

    assert result["outcomes"] == {"http_error": 2}
    assert "404" in result["failures"][0]["detail"]


def test_echo_server_decodes_chunked_bodies(echo):
    body = make_body("s", 9, 150_000)
    conn = http.client.HTTPConnection("127.0.0.1", echo, timeout=5)
    conn.request(
        "POST",
        "/",
        body=iter([body[:1000], body[1000:100_000], body[100_000:]]),
        encode_chunked=True,
    )

    answer = json.loads(conn.getresponse().read())

    assert answer["sha256"] == expected_digest(body)["sha256"]
    assert not answer["short"]


def test_echo_server_answers_get_for_readiness(echo):
    conn = http.client.HTTPConnection("127.0.0.1", echo, timeout=5)
    conn.request("GET", "/")

    assert json.loads(conn.getresponse().read()) == {"ok": True}


@pytest.mark.parametrize("module", [echo_server, loadgen])
def test_shipped_files_use_only_the_standard_library(module):
    tree = ast.parse(Path(module.__file__).read_text())
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            assert node.level == 0, "relative imports cannot be shipped"
            imported.add(node.module.split(".")[0])

    assert imported <= set(sys.stdlib_module_names)
