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


def _timeout(at: str, last_alive: str) -> str:
    return _line(
        at,
        f"mux: ping timeout, last alive {last_alive} timeout 30s\n",
        "debug",
    )


def _cycle(server: str, timeout_at: str, last_alive: str, start_at: str, back_at: str):
    return [
        _timeout(timeout_at, last_alive),
        _line(start_at, f"Start server: {server} vkey: X"),
        _line(back_at, f"Successful connection with server {server}"),
    ]


def test_two_bridges_down_together_stay_separate_outages():
    # A client bridging two edges whose own network blips: both muxes time out
    # within a second of each other. Each edge keeps its own downtime.
    other = "nps-other.example.test:51235"
    text = "\n".join(
        [
            _timeout("2026-10-25T09:00:00+00:00", "2026-10-25 08:59:58.0 +0000 UTC"),
            _timeout("2026-10-25T09:00:01+00:00", "2026-10-25 08:59:59.0 +0000 UTC"),
            _line("2026-10-25T09:00:05+00:00", f"Start server: {SERVER} vkey: X"),
            _line("2026-10-25T09:00:06+00:00", f"Start server: {other} vkey: X"),
            # The second bridge comes back first, which used to misattribute both.
            _line(
                "2026-10-25T09:00:53+00:00",
                f"Successful connection with server {other}",
            ),
            _line(
                "2026-10-25T09:00:47+00:00",
                f"Successful connection with server {SERVER}",
            ),
        ]
    )

    outages = find_outages(parse_log(text))

    assert [o.server for o in outages] == [SERVER, other]
    assert abs(outages[0].duration(now=0) - 49) < 2
    assert abs(outages[1].duration(now=0) - 54) < 2


def test_a_failure_lines_up_with_the_outage_of_the_same_server():
    other = "nps-other.example.test:51235"
    text = "\n".join(
        [
            _timeout("2026-10-25T09:00:00+00:00", "2026-10-25 08:59:58.0 +0000 UTC"),
            _timeout("2026-10-25T09:00:01+00:00", "2026-10-25 08:59:59.0 +0000 UTC"),
            _line("2026-10-25T09:00:02+00:00", f"Start server: {SERVER} vkey: X"),
            _line("2026-10-25T09:00:02+00:00", f"Start server: {other} vkey: X"),
            _line(
                "2026-10-25T09:00:20+00:00",
                f"Failed to connect to server {other} error: i/o timeout",
                "error",
            ),
            _line(
                "2026-10-25T09:00:30+00:00",
                f"Successful connection with server {SERVER}",
            ),
            _line(
                "2026-10-25T09:00:40+00:00",
                f"Successful connection with server {other}",
            ),
        ]
    )

    outages = find_outages(parse_log(text))

    assert [o.server for o in outages] == [SERVER, other]
    assert outages[0].failed_attempts == 0
    assert outages[1].failed_attempts == 1
    assert outages[1].reasons == ["timeout"]


def test_back_to_back_cycles_for_one_server_stay_two_outages():
    text = "\n".join(
        _cycle(
            SERVER,
            "2026-10-25T09:00:00+00:00",
            "2026-10-25 08:59:58.0 +0000 UTC",
            "2026-10-25T09:00:05+00:00",
            "2026-10-25T09:00:20+00:00",
        )
        + _cycle(
            SERVER,
            "2026-10-25T09:10:00+00:00",
            "2026-10-25 09:09:58.0 +0000 UTC",
            "2026-10-25T09:10:05+00:00",
            "2026-10-25T09:10:20+00:00",
        )
    )

    outages = find_outages(parse_log(text))

    assert len(outages) == 2
    assert all(o.server == SERVER and o.reconnected for o in outages)


def test_a_repeated_timeout_for_the_same_drop_is_not_a_second_outage():
    # A bridge that never reconnects keeps reporting the same last-answered
    # ping; each report used to open a phantom outage that never closed.
    same = "2026-10-25 08:59:58.5 +0000 UTC"
    text = "\n".join(
        [
            _timeout("2026-10-25T09:00:28+00:00", same),
            _line("2026-10-25T09:00:29+00:00", f"Start server: {SERVER} vkey: X"),
            _timeout("2026-10-25T09:01:12+00:00", same),
            _timeout("2026-10-25T09:02:00+00:00", same),
            _line(
                "2026-10-25T09:02:20+00:00",
                f"Successful connection with server {SERVER}",
            ),
        ]
    )

    outages = find_outages(parse_log(text))

    assert len(outages) == 1
    assert outages[0].server == SERVER
    assert outages[0].reconnected is not None


def test_two_bridges_dropping_a_second_apart_keep_their_own_stamps():
    # The two timeouts are logged a second apart but each carries the time its
    # own bridge stopped answering, which is what keeps them apart.
    other = "nps-other.example.test:51235"
    text = "\n".join(
        [
            _timeout("2026-10-25T09:00:28+00:00", "2026-10-25 08:59:58.1 +0000 UTC"),
            _timeout("2026-10-25T09:00:29+00:00", "2026-10-25 08:59:59.9 +0000 UTC"),
            _line("2026-10-25T09:00:35+00:00", f"Start server: {SERVER} vkey: X"),
            _line("2026-10-25T09:00:36+00:00", f"Start server: {other} vkey: X"),
            _line(
                "2026-10-25T09:01:20+00:00",
                f"Successful connection with server {SERVER}",
            ),
            _line(
                "2026-10-25T09:01:21+00:00",
                f"Successful connection with server {other}",
            ),
        ]
    )

    outages = find_outages(parse_log(text))

    assert [o.server for o in outages] == [SERVER, other]


def test_a_tie_on_the_stamp_gives_each_bridge_its_own_outage():
    # NPC stamps ``last alive`` to the second, so two bridges stopping together
    # share a stamp. The second is folded at the timeout and gets its outage
    # back when its own Start server line names it.
    other = "nps-other.example.test:51235"
    same = "2026-10-25 08:59:58 +0000 UTC"
    text = "\n".join(
        [
            _timeout("2026-10-25T09:00:28+00:00", same),
            _timeout("2026-10-25T09:00:28+00:00", same),
            _line("2026-10-25T09:00:30+00:00", f"Start server: {SERVER} vkey: X"),
            _line("2026-10-25T09:00:31+00:00", f"Start server: {other} vkey: X"),
            _line(
                "2026-10-25T09:01:40+00:00",
                f"Successful connection with server {SERVER}",
            ),
            _line(
                "2026-10-25T09:02:20+00:00",
                f"Successful connection with server {other}",
            ),
        ]
    )

    outages = find_outages(parse_log(text))

    assert [o.server for o in outages] == [SERVER, other]
    assert abs(outages[0].duration(now=0) - 102) < 2
    assert abs(outages[1].duration(now=0) - 142) < 2


def test_a_tie_where_only_the_second_bridge_returns_keeps_the_first_open():
    other = "nps-other.example.test:51235"
    same = "2026-10-25 08:59:58 +0000 UTC"
    text = "\n".join(
        [
            _timeout("2026-10-25T09:00:28+00:00", same),
            _timeout("2026-10-25T09:00:28+00:00", same),
            _line("2026-10-25T09:00:30+00:00", f"Start server: {SERVER} vkey: X"),
            _line("2026-10-25T09:00:31+00:00", f"Start server: {other} vkey: X"),
            _line(
                "2026-10-25T09:02:20+00:00",
                f"Successful connection with server {other}",
            ),
        ]
    )

    outages = find_outages(parse_log(text))

    assert [(o.server, o.reconnected is None) for o in outages] == [
        (SERVER, True),
        (other, False),
    ]


def test_a_reconnect_after_a_fold_does_not_invent_an_outage():
    # Only a Start server line may claim a folded timeout: a bridge that was
    # never down must not be handed one from a Successful connection.
    same = "2026-10-25 08:59:58 +0000 UTC"
    other = "nps-other.example.test:51235"
    text = "\n".join(
        [
            _timeout("2026-10-25T09:00:28+00:00", same),
            _timeout("2026-10-25T09:00:29+00:00", same),
            _line("2026-10-25T09:00:30+00:00", f"Start server: {SERVER} vkey: X"),
            _line(
                "2026-10-25T09:02:30+00:00",
                f"Successful connection with server {other}",
            ),
        ]
    )

    outages = find_outages(parse_log(text))

    assert [o.server for o in outages] == [SERVER]
    assert outages[0].reconnected is None


def test_one_fold_backs_only_one_invented_outage():
    same = "2026-10-25 08:59:58 +0000 UTC"
    second = "nps-second.example:8024"
    third = "nps-third.example:8024"
    text = "\n".join(
        [
            _timeout("2026-10-25T09:00:28+00:00", same),
            _timeout("2026-10-25T09:00:29+00:00", same),
            _line("2026-10-25T09:00:30+00:00", f"Start server: {SERVER} vkey: X"),
            _line("2026-10-25T09:00:40+00:00", f"Start server: {second} vkey: X"),
            _line("2026-10-25T09:00:50+00:00", f"Start server: {third} vkey: X"),
        ]
    )

    outages = find_outages(parse_log(text))

    assert [o.server for o in outages] == [SERVER, second]


def test_a_stamp_less_repeat_after_the_outage_is_named_does_not_open_a_phantom():
    text = "\n".join(
        [
            _line(
                "2026-10-25T09:00:00+00:00", "mux: ping timeout timeout 30s", "debug"
            ),
            _line("2026-10-25T09:00:04+00:00", f"Start server: {SERVER} vkey: X"),
            _line(
                "2026-10-25T09:00:30+00:00", "mux: ping timeout timeout 30s", "debug"
            ),
            _line(
                "2026-10-25T09:01:00+00:00", "mux: ping timeout timeout 30s", "debug"
            ),
            _line(
                "2026-10-25T09:01:40+00:00",
                f"Successful connection with server {SERVER}",
            ),
        ]
    )

    (outage,) = find_outages(parse_log(text))

    assert outage.server == SERVER
    assert outage.reconnected is not None


def test_stamp_less_drops_of_two_bridges_are_separated_by_their_start_lines():
    other = "nps-other.example.test:51235"
    text = "\n".join(
        [
            _line(
                "2026-10-25T09:00:00+00:00", "mux: ping timeout timeout 30s", "debug"
            ),
            _line(
                "2026-10-25T09:00:02+00:00", "mux: ping timeout timeout 30s", "debug"
            ),
            _line("2026-10-25T09:00:05+00:00", f"Start server: {SERVER} vkey: X"),
            _line("2026-10-25T09:00:06+00:00", f"Start server: {other} vkey: X"),
            _line(
                "2026-10-25T09:01:00+00:00",
                f"Successful connection with server {SERVER}",
            ),
            _line(
                "2026-10-25T09:01:10+00:00",
                f"Successful connection with server {other}",
            ),
        ]
    )

    outages = find_outages(parse_log(text))

    assert [o.server for o in outages] == [SERVER, other]
    assert all(o.reconnected is not None for o in outages)


def test_a_timeout_without_a_stamp_folds_into_the_open_outage():
    # A different NPC build, or a truncated tail, may omit the stamp.
    text = "\n".join(
        [
            _line(
                "2026-10-25T09:00:00+00:00", "mux: ping timeout timeout 30s", "debug"
            ),
            _line(
                "2026-10-25T09:00:40+00:00", "mux: ping timeout timeout 30s", "debug"
            ),
            _line(
                "2026-10-25T09:01:20+00:00", "mux: ping timeout timeout 30s", "debug"
            ),
            _line("2026-10-25T09:01:30+00:00", f"Start server: {SERVER} vkey: X"),
            _line(
                "2026-10-25T09:02:00+00:00",
                f"Successful connection with server {SERVER}",
            ),
        ]
    )

    (outage,) = find_outages(parse_log(text))

    assert outage.server == SERVER
    assert outage.reconnected is not None


def test_a_tie_is_redeemed_after_the_first_bridge_reconnects():
    # NPC logs Start and Successful per bridge, so a client that reconnects its
    # bridges one at a time closes the first outage before the second Start
    # arrives. The tied bridge still gets its own outage, with the shared stamp.
    same = "2026-10-25 08:59:58 +0000 UTC"
    other = "nps-other.example.test:51235"
    text = "\n".join(
        [
            _line(
                "2026-10-25T08:59:00+00:00",
                f"Successful connection with server {SERVER}",
            ),
            _line(
                "2026-10-25T08:59:01+00:00",
                f"Successful connection with server {other}",
            ),
            _timeout("2026-10-25T09:00:28+00:00", same),
            _timeout("2026-10-25T09:00:28+00:00", same),
            _line("2026-10-25T09:00:30+00:00", f"Start server: {other} vkey: X"),
            _line(
                "2026-10-25T09:01:45+00:00",
                f"Successful connection with server {other}",
            ),
            _line("2026-10-25T09:01:48+00:00", f"Start server: {SERVER} vkey: X"),
            _line(
                "2026-10-25T09:02:00+00:00",
                f"Successful connection with server {SERVER}",
            ),
        ]
    )

    outages = find_outages(parse_log(text))

    assert [o.server for o in outages] == [other, SERVER]
    assert abs(outages[0].duration(now=0) - 107) < 2
    assert abs(outages[1].duration(now=0) - 122) < 2


def test_a_tie_keeps_the_late_bridge_while_the_drop_is_still_open():
    # A third bridge that has not come back holds the drop open, so the tied
    # bridge's own reconnect can be minutes later and still count from the
    # shared stamp.
    same = "2026-10-25 08:59:58 +0000 UTC"
    other = "nps-other.example.test:51235"
    third = "nps-third.example.test:51235"
    text = "\n".join(
        [
            _line(
                "2026-10-25T08:59:00+00:00",
                f"Successful connection with server {SERVER}",
            ),
            _line(
                "2026-10-25T08:59:01+00:00",
                f"Successful connection with server {other}",
            ),
            _line(
                "2026-10-25T08:59:02+00:00",
                f"Successful connection with server {third}",
            ),
            _timeout("2026-10-25T09:00:28+00:00", same),
            _timeout("2026-10-25T09:00:29+00:00", same),
            _timeout("2026-10-25T09:00:29+00:00", "2026-10-25 08:59:59 +0000 UTC"),
            _line("2026-10-25T09:00:30+00:00", f"Start server: {SERVER} vkey: X"),
            _line(
                "2026-10-25T09:00:50+00:00",
                f"Successful connection with server {SERVER}",
            ),
            _line("2026-10-25T09:00:40+00:00", f"Start server: {third} vkey: X"),
            _line("2026-10-25T09:04:00+00:00", f"Start server: {other} vkey: X"),
            _line(
                "2026-10-25T09:04:20+00:00",
                f"Successful connection with server {other}",
            ),
        ]
    )

    outages = find_outages(parse_log(text))

    assert [o.server for o in outages] == [SERVER, third, other]
    assert abs(outages[2].duration(now=0) - 262) < 2
    assert outages[1].reconnected is None


def test_a_start_after_the_drop_is_over_starts_at_that_line():
    # Nothing of the drop is still open and its last outage closed minutes ago,
    # so this Start is the client starting a bridge again rather than a tied
    # bridge coming back. Dating it from the drop would report hours that never
    # happened; the line itself is the earliest evidence there is.
    same = "2026-10-25 08:59:58 +0000 UTC"
    other = "nps-other.example.test:51235"
    text = "\n".join(
        [
            _line(
                "2026-10-25T08:59:00+00:00",
                f"Successful connection with server {SERVER}",
            ),
            _line(
                "2026-10-25T08:59:01+00:00",
                f"Successful connection with server {other}",
            ),
            _timeout("2026-10-25T09:00:28+00:00", same),
            _timeout("2026-10-25T09:00:29+00:00", same),
            _line("2026-10-25T09:00:30+00:00", f"Start server: {SERVER} vkey: X"),
            _line(
                "2026-10-25T09:00:50+00:00",
                f"Successful connection with server {SERVER}",
            ),
            _line("2026-10-25T09:04:00+00:00", f"Start server: {other} vkey: X"),
            _line(
                "2026-10-25T09:04:20+00:00",
                f"Successful connection with server {other}",
            ),
        ]
    )

    outages = find_outages(parse_log(text))

    assert [o.server for o in outages] == [SERVER, other]
    assert abs(outages[1].duration(now=0) - 20) < 2


def test_a_bridge_that_reconnected_after_the_fold_is_not_handed_one():
    # A Start server for a bridge that is up again is its listener restarting,
    # not a second bridge going down with the drop.
    same = "2026-10-25 08:59:58 +0000 UTC"
    other = "nps-other.example.test:51235"
    text = "\n".join(
        [
            _line(
                "2026-10-25T08:59:00+00:00",
                f"Successful connection with server {SERVER}",
            ),
            _timeout("2026-10-25T09:00:28+00:00", same),
            _timeout("2026-10-25T09:00:29+00:00", same),
            _line("2026-10-25T09:00:30+00:00", f"Start server: {SERVER} vkey: X"),
            _line(
                "2026-10-25T09:00:50+00:00",
                f"Successful connection with server {SERVER}",
            ),
            _line(
                "2026-10-25T09:00:55+00:00",
                f"Successful connection with server {other}",
            ),
            _line("2026-10-25T09:01:00+00:00", f"Start server: {other} vkey: X"),
        ]
    )

    (outage,) = find_outages(parse_log(text))

    assert outage.server == SERVER
    assert outage.reconnected is not None


def test_four_bridges_on_one_stamp_each_get_an_outage():
    others = [f"nps-{name}.example.test:51235" for name in ("one", "two", "three")]
    same = "2026-10-25 08:59:58 +0000 UTC"
    start = [
        _line("2026-10-25T08:59:00+00:00", f"Successful connection with server {name}")
        for name in [SERVER, *others]
    ]
    text = "\n".join(
        [
            *start,
            *[_timeout("2026-10-25T09:00:28+00:00", same) for _ in range(4)],
            *[
                _line(
                    f"2026-10-25T09:00:{30 + index}+00:00",
                    f"Start server: {name} vkey: X",
                )
                for index, name in enumerate(others)
            ],
            _line("2026-10-25T09:00:34+00:00", f"Start server: {SERVER} vkey: X"),
            *[
                _line(
                    f"2026-10-25T09:01:{index:02d}+00:00",
                    f"Successful connection with server {name}",
                )
                for index, name in enumerate([SERVER, *others])
            ],
        ]
    )

    outages = find_outages(parse_log(text))

    assert sorted(o.server for o in outages) == sorted([SERVER, *others])
    assert all(o.reconnected is not None for o in outages)


def test_a_stamp_less_drop_takes_both_bridges_with_it():
    # Without a stamp the drop time is estimated from the timeout lines, but a
    # second Start server still means a second bridge went down.
    other = "nps-other.example.test:51235"
    text = "\n".join(
        [
            _line(
                "2026-10-25T08:59:00+00:00",
                f"Successful connection with server {SERVER}",
            ),
            _line(
                "2026-10-25T08:59:01+00:00",
                f"Successful connection with server {other}",
            ),
            _line(
                "2026-10-25T09:00:28+00:00", "mux: ping timeout timeout 30s", "debug"
            ),
            _line(
                "2026-10-25T09:00:30+00:00", "mux: ping timeout timeout 30s", "debug"
            ),
            _line("2026-10-25T09:00:35+00:00", f"Start server: {SERVER} vkey: X"),
            _line("2026-10-25T09:00:36+00:00", f"Start server: {other} vkey: X"),
            _line(
                "2026-10-25T09:01:00+00:00",
                f"Successful connection with server {SERVER}",
            ),
            _line(
                "2026-10-25T09:01:30+00:00",
                f"Successful connection with server {other}",
            ),
        ]
    )

    outages = find_outages(parse_log(text))

    assert [o.server for o in outages] == [SERVER, other]
    assert all(o.reconnected is not None for o in outages)


def test_a_restarted_bridge_is_not_given_the_old_drops_downtime():
    # One bridge drops and repeats its timeout, so it leaves a fold behind; the
    # other bridge was up the whole time and is restarted much later. The fold
    # must not turn that restart into an outage measured from the old drop.
    same = "2026-10-25 08:59:58 +0000 UTC"
    other = "nps-other.example.test:51235"
    text = "\n".join(
        [
            _line(
                "2026-10-25T08:59:00+00:00",
                f"Successful connection with server {SERVER}",
            ),
            _line(
                "2026-10-25T08:59:00+00:00",
                f"Successful connection with server {other}",
            ),
            _timeout("2026-10-25T09:00:28+00:00", same),
            _timeout("2026-10-25T09:00:58+00:00", same),
            _line("2026-10-25T09:01:08+00:00", f"Start server: {SERVER} vkey: X"),
            _line(
                "2026-10-25T09:01:28+00:00",
                f"Successful connection with server {SERVER}",
            ),
            _line("2026-10-25T09:05:00+00:00", f"Start server: {other} vkey: X"),
            _line(
                "2026-10-25T09:05:01+00:00",
                f"Successful connection with server {other}",
            ),
        ]
    )

    outages = find_outages(parse_log(text))

    assert [o.server for o in outages] == [SERVER, other]
    assert abs(outages[0].duration(now=0) - 90) < 2
    assert abs(outages[1].duration(now=0) - 1) < 2


def test_a_reconnect_for_an_unknown_bridge_leaves_the_open_outage_open():
    other = "nps-other.example.test:51235"
    same = "2026-10-25 08:59:58 +0000 UTC"
    text = "\n".join(
        [
            _timeout("2026-10-25T09:00:28+00:00", same),
            _timeout("2026-10-25T09:00:28+00:00", same),
            _line("2026-10-25T09:00:30+00:00", f"Start server: {SERVER} vkey: X"),
            _line(
                "2026-10-25T09:02:20+00:00",
                f"Successful connection with server {other}",
            ),
        ]
    )

    (outage,) = find_outages(parse_log(text))

    assert outage.server == SERVER
    assert outage.reconnected is None


def test_startup_lines_with_no_outage_open_are_ignored():
    text = "\n".join(
        [
            _line("2026-10-25T09:00:00+00:00", f"Start server: {SERVER} vkey: X"),
            _line(
                "2026-10-25T09:00:05+00:00",
                f"Successful connection with server {SERVER}",
            ),
        ]
    )

    assert find_outages(parse_log(text)) == []


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
