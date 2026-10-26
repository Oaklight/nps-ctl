#!/usr/bin/env python3
"""Self-verifying HTTP load generator for nps-ctl checks.

Sends request bodies that differ from request to request and compares the
echo service's answer with what it computed locally, so truncation, bit
damage and bytes spliced in from another concurrent request are all detected.
Standard library only: this file is shipped to remote hosts and run with the
system ``python3``. The only argument is a JSON load spec; the result is one
JSON line on stdout.
"""

from __future__ import annotations

import hashlib
import http.client
import json
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any

BLOCK = 65536
MAX_FAILURES_KEPT = 50
MAX_FAILURE_TIMES = 5000

DEFAULTS: dict[str, Any] = {
    "host": "127.0.0.1",
    "port": 0,
    "host_header": "",
    "path": "/",
    "size": 262144,
    "count": 20,
    "duration": 0.0,
    "concurrency": 4,
    "mode": "normal",
    "chunk_kb": 16.0,
    "gap_ms": 20.0,
    "timeout": 30.0,
    "seed": "nps-ctl",
}


def make_body(seed: str, index: int, size: int) -> bytes:
    """Return the deterministic, request-unique body for *index*."""
    return hashlib.shake_256(f"{seed}:{index}".encode()).digest(size)


def expected_digest(body: bytes) -> dict:
    """Compute the answer a correct echo service must give for *body*."""
    return {
        "len": len(body),
        "sha256": hashlib.sha256(body).hexdigest(),
        "blocks": [
            hashlib.sha256(body[i : i + BLOCK]).hexdigest()[:8]
            for i in range(0, len(body), BLOCK)
        ],
    }


def classify(expected: dict, got: dict) -> tuple[str, str]:
    """Compare the echo answer with the expected digest.

    Returns:
        ``(outcome, detail)``; outcome is ``ok``, ``truncated``, ``extended``
        or ``corrupt``.
    """
    if got.get("len") == expected["len"] and got.get("sha256") == expected["sha256"]:
        return "ok", ""
    got_len = got.get("len", -1)
    if got_len < expected["len"] or got.get("short"):
        return "truncated", f"got {got_len} of {expected['len']} bytes"
    if got_len > expected["len"]:
        return "extended", f"got {got_len} of {expected['len']} bytes"
    bad = next(
        (
            i
            for i, (a, b) in enumerate(zip(expected["blocks"], got.get("blocks", [])))
            if a != b
        ),
        -1,
    )
    return "corrupt", f"same length, first differing 64KiB block {bad}"


def one_request(spec: dict, index: int) -> dict:
    """Send request *index* and classify the outcome."""
    started = time.time()
    body = make_body(spec["seed"], index, spec["size"])
    want = expected_digest(body)
    outcome, detail = "ok", ""
    conn = http.client.HTTPConnection(
        spec["host"], spec["port"], timeout=spec["timeout"]
    )
    try:
        headers = {"Content-Type": "application/octet-stream"}
        if spec["host_header"]:
            headers["Host"] = spec["host_header"]
        if spec["mode"] == "slow":
            conn.putrequest(
                "POST",
                spec["path"],
                skip_host=bool(spec["host_header"]),
                skip_accept_encoding=True,
            )
            for key, value in headers.items():
                conn.putheader(key, value)
            conn.putheader("Content-Length", str(len(body)))
            conn.endheaders()
            step = max(1, int(spec["chunk_kb"] * 1024))
            for offset in range(0, len(body), step):
                conn.send(body[offset : offset + step])
                time.sleep(spec["gap_ms"] / 1000.0)
        else:
            conn.request("POST", spec["path"], body=body, headers=headers)
        response = conn.getresponse()
        raw = response.read()
        if response.status != 200:
            outcome = "http_error"
            detail = f"{response.status} {raw[:120].decode('utf-8', 'replace')}"
        else:
            try:
                outcome, detail = classify(want, json.loads(raw))
            except ValueError:
                outcome, detail = "http_error", f"non-JSON answer {raw[:80]!r}"
    except TimeoutError:
        outcome, detail = "timeout", f"no answer within {spec['timeout']}s"
    except Exception as exc:  # noqa: BLE001 - every transport failure is a data point
        outcome, detail = "conn_error", f"{type(exc).__name__}: {exc}"[:160]
    finally:
        conn.close()
    return {
        "i": index,
        "t": started,
        "ms": round((time.time() - started) * 1000, 1),
        "outcome": outcome,
        "detail": detail,
    }


def run(spec: dict) -> dict:
    """Run the load described by *spec* and return the aggregate result."""
    spec = {**DEFAULTS, **spec}
    lock = threading.Lock()
    state = {"next": 0}
    deadline = time.time() + spec["duration"] if spec["duration"] else None
    records: list[dict] = []

    def take() -> int | None:
        with lock:
            if deadline is not None:
                if time.time() >= deadline:
                    return None
            elif state["next"] >= spec["count"]:
                return None
            state["next"] += 1
            return state["next"] - 1

    def worker() -> None:
        while (index := take()) is not None:
            record = one_request(spec, index)
            with lock:
                records.append(record)

    started = time.time()
    with ThreadPoolExecutor(max_workers=spec["concurrency"]) as pool:
        for _ in range(spec["concurrency"]):
            pool.submit(worker)
    finished = time.time()

    outcomes: dict[str, int] = {}
    for record in records:
        outcomes[record["outcome"]] = outcomes.get(record["outcome"], 0) + 1
    durations = sorted(record["ms"] for record in records)
    failures = [r for r in records if r["outcome"] != "ok"]
    failures.sort(key=lambda r: r["t"])
    return {
        "spec": {k: v for k, v in spec.items() if k != "seed"},
        "started": started,
        "finished": finished,
        "total": len(records),
        "outcomes": outcomes,
        "p50_ms": durations[len(durations) // 2] if durations else None,
        "p95_ms": durations[int(len(durations) * 0.95)] if durations else None,
        "max_ms": durations[-1] if durations else None,
        "failures": failures[:MAX_FAILURES_KEPT],
        "failure_times": [r["t"] for r in failures][:MAX_FAILURE_TIMES],
    }


if __name__ == "__main__":
    print(json.dumps(run(json.loads(sys.argv[1]))))
