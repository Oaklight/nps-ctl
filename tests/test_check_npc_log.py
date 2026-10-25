"""Tests for NPC log parsing and outage detection."""

from __future__ import annotations

from datetime import datetime

from nps_ctl.check import npc_log
from nps_ctl.check.npc_log import (
    CLIENT_CLOSED,
    CONNECT_FAILED,
    CONNECTED,
    MUX_CLOSED,
    PING_TIMEOUT,
    START_SERVER,
    classify_error,
    find_outages,
    parse_line,
    parse_log,
)

SERVER = "nps-europe.example.test:51235"


def _line(time: str, message: str, level: str = "info", caller: str = "x.go:1") -> str:
    import json

    return json.dumps(
        {"level": level, "time": time, "caller": caller, "message": message}
    )


def _epoch(text: str) -> float:
    return datetime.fromisoformat(text).timestamp()


# One reconnect cycle as NPC logs it: a ping timeout, the mux teardown, a
# restart naming the server, one failed attempt and the final reconnect.
CYCLE = "\n".join(
    [
        _line(
            "2026-10-25T04:19:38-04:00",
            "mux: ping timeout, last alive 2026-10-25 04:19:06.12357105 "
            "-0400 EDT timeout 30s\n",
            "debug",
        ),
        _line("2026-10-25T04:19:38-04:00", "close mux\n", "debug"),
        _line(
            "2026-10-25T04:19:38-04:00",
            "Client closed! It will be reconnected in five seconds",
        ),
        _line(
            "2026-10-25T04:19:43-04:00",
            f"Start server: {SERVER} vkey: REDACTED type: tls local_ip: ",
        ),
        _line(
            "2026-10-25T04:19:58-04:00",
            f"Failed to connect to server {SERVER} error: dial tcp "
            "192.0.2.7:51235: connect: no route to host",
            "error",
        ),
        _line(
            "2026-10-25T04:20:08-04:00",
            f"Successful connection with server {SERVER}",
        ),
    ]
)


def test_parse_line_recognises_each_event_kind():
    kinds = [event.kind for event in parse_log(CYCLE)]

    assert kinds == [
        PING_TIMEOUT,
        MUX_CLOSED,
        CLIENT_CLOSED,
        START_SERVER,
        CONNECT_FAILED,
        CONNECTED,
    ]


def test_ping_timeout_carries_the_last_alive_time_with_fractions():
    event = parse_log(CYCLE)[0]

    assert event.last_alive is not None
    assert abs(event.last_alive - _epoch("2026-10-25T04:19:06.123571-04:00")) < 1e-3


def test_start_and_failure_name_their_server():
    events = {event.kind: event for event in parse_log(CYCLE)}

    assert events[START_SERVER].server == SERVER
    assert events[CONNECT_FAILED].server == SERVER
    assert "no route to host" in events[CONNECT_FAILED].detail


def test_unrelated_and_malformed_lines_are_ignored():
    text = "\n".join(
        [
            "",
            "not json at all",
            "{broken",
            _line("2026-10-25T04:00:00-04:00", "new tcp connection with the goal"),
            '{"level":"info","caller":"x.go:1","message":"close mux"}',
            _line("not-a-time", "close mux"),
        ]
    )

    assert parse_log(text) == []


def test_parse_line_returns_none_for_a_non_event():
    assert parse_line(_line("2026-10-25T04:00:00-04:00", "heartbeat")) is None


def test_events_are_returned_in_time_order():
    text = "\n".join(reversed(CYCLE.splitlines()))

    times = [event.time for event in parse_log(text)]

    assert times == sorted(times)


def test_cycle_becomes_one_outage_from_last_alive_to_reconnect():
    (outage,) = find_outages(parse_log(CYCLE))

    assert outage.server == SERVER
    assert outage.reconnected == _epoch("2026-10-25T04:20:08-04:00")
    assert abs(outage.last_alive - _epoch("2026-10-25T04:19:06.123571-04:00")) < 1e-3
    assert outage.failed_attempts == 1
    assert outage.reasons == ["no route to host"]
    assert 61 < outage.duration(now=0) < 63


def test_outage_without_reconnect_stays_open_until_now():
    open_cycle = "\n".join(CYCLE.splitlines()[:5])
    (outage,) = find_outages(parse_log(open_cycle))
    now = _epoch("2026-10-25T04:30:00-04:00")

    assert outage.reconnected is None
    assert outage.end(now) == now
    assert outage.duration(now) > 600


def test_second_ping_timeout_inside_an_outage_extends_it():
    lines = CYCLE.splitlines()
    second = _line(
        "2026-10-25T04:19:50-04:00",
        "mux: ping timeout, last alive 2026-10-25 04:19:20.0 -0400 EDT timeout 30s\n",
        "debug",
    )
    text = "\n".join(lines[:4] + [second] + lines[4:])

    outages = find_outages(parse_log(text))

    assert len(outages) == 1
    assert outages[0].reconnected == _epoch("2026-10-25T04:20:08-04:00")


def test_a_connection_with_no_outage_open_is_not_an_outage():
    text = _line(
        "2026-10-25T04:00:00-04:00", f"Successful connection with server {SERVER}"
    )

    assert find_outages(parse_log(text)) == []


def test_two_cycles_make_two_outages_each_with_its_own_server():
    other = CYCLE.replace(SERVER, "nps-asia.example.test:51235").replace(
        "2026-10-25T04:", "2026-10-25T05:"
    )

    outages = find_outages(parse_log(CYCLE + "\n" + other))

    assert [o.server for o in outages] == [SERVER, "nps-asia.example.test:51235"]


def test_classify_error_names_the_common_failures():
    assert classify_error("dial tcp 1.2.3.4:5: connect: no route to host") == (
        "no route to host"
    )
    assert classify_error("dial tcp: i/o timeout") == "timeout"
    assert classify_error("connect: connection refused") == "connection refused"
    assert classify_error("can not resolve nps-europe.example") == "dns failure"
    assert classify_error("read: connection reset by peer") == "connection reset"
    assert classify_error("connect: network is unreachable") == "network unreachable"
    assert classify_error("something odd") == "something odd"


def test_classify_error_never_echoes_a_verify_key():
    quoted = "validation key j9b93wfmiodhimy9 incorrect"

    assert classify_error(quoted) == "verify key rejected"
    assert "j9b93wfmiodhimy9" not in classify_error(
        "rejected: token j9b93wfmiodhimy9 bad"
    )
    assert classify_error("rejected: token j9b93wfmiodhimy9 bad") == (
        "rejected: token <redacted> bad"
    )
    assert classify_error("") == "unknown"


def test_module_exposes_the_documented_kinds():
    for name in (
        "PING_TIMEOUT",
        "MUX_CLOSED",
        "CLIENT_CLOSED",
        "START_SERVER",
        "CONNECT_FAILED",
        "CONNECTED",
    ):
        assert isinstance(getattr(npc_log, name), str)
