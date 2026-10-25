#!/usr/bin/env python3
"""Hash-echo HTTP service for nps-ctl checks.

Reads a request body without keeping it and answers with its length, SHA-256 and
one short hash per 64 KiB block, so a sender can tell not only that a body was
damaged but where. Standard library only: this file is shipped to remote hosts
and run with the system ``python3``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

BLOCK = 65536


class Digest:
    """Incremental length, SHA-256 and per-block hashes of a byte stream."""

    def __init__(self) -> None:
        self.length = 0
        self.total = hashlib.sha256()
        self.blocks: list[str] = []
        self._block = hashlib.sha256()
        self._filled = 0

    def update(self, data: bytes) -> None:
        """Feed *data* into the digest."""
        self.length += len(data)
        self.total.update(data)
        view = memoryview(data)
        while view:
            take = min(BLOCK - self._filled, len(view))
            self._block.update(view[:take])
            self._filled += take
            view = view[take:]
            if self._filled == BLOCK:
                self._close_block()

    def _close_block(self) -> None:
        self.blocks.append(self._block.hexdigest()[:8])
        self._block = hashlib.sha256()
        self._filled = 0

    def result(self, short: bool) -> dict:
        """Return the JSON-serialisable answer."""
        if self._filled:
            self._close_block()
        return {
            "len": self.length,
            "sha256": self.total.hexdigest(),
            "blocks": self.blocks,
            "short": short,
        }


def _read_exact(rfile, length: int, digest: Digest) -> bool:
    """Read *length* bytes into *digest*; return True when the stream ended early."""
    remaining = length
    while remaining:
        data = rfile.read(min(remaining, 1 << 20))
        if not data:
            return True
        digest.update(data)
        remaining -= len(data)
    return False


def _read_chunked(rfile, digest: Digest) -> bool:
    """Decode a chunked body into *digest*; return True when it ended early."""
    while True:
        line = rfile.readline()
        if not line:
            return True
        try:
            size = int(line.split(b";")[0].strip() or b"0", 16)
        except ValueError:
            return True
        if size == 0:
            rfile.readline()
            return False
        if _read_exact(rfile, size, digest):
            return True
        rfile.readline()


class Handler(BaseHTTPRequestHandler):
    """Answer GET with a liveness body and POST with the body's digest."""

    protocol_version = "HTTP/1.1"

    def log_message(self, format, *args):  # noqa: A002 - signature fixed by the base class
        pass

    def _send(self, payload: dict) -> None:
        body = json.dumps(payload).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)
        self.close_connection = True

    def do_GET(self):  # noqa: N802
        self._send({"ok": True})

    def do_POST(self):  # noqa: N802
        digest = Digest()
        if "chunked" in self.headers.get("Transfer-Encoding", "").lower():
            short = _read_chunked(self.rfile, digest)
        else:
            declared = int(self.headers.get("Content-Length") or 0)
            short = _read_exact(self.rfile, declared, digest)
        self._send(digest.result(short))


def main() -> None:
    """Start the service and write its port to ``--port-file``."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bind", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--port-file", default="")
    parser.add_argument(
        "--ttl",
        type=float,
        default=3600.0,
        help="Exit after this many seconds so an orphaned service cleans itself up",
    )
    args = parser.parse_args()

    server = ThreadingHTTPServer((args.bind, args.port), Handler)
    server.daemon_threads = True
    if args.port_file:
        with open(args.port_file, "w") as handle:
            handle.write(str(server.server_address[1]))
    threading.Timer(args.ttl, server.shutdown).start()
    server.serve_forever()


if __name__ == "__main__":
    main()
