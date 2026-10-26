"""Tests for link analysis and collection."""

from __future__ import annotations

import json
from datetime import datetime
from types import SimpleNamespace

import pytest

from nps_ctl.check.analysis import (
    detect_period,
    assess,
    summarize,
)
from nps_ctl.check.links import (
    build_script,
    collect_client,
    collect_links,
    parse_output,
    report_for,
    sudo_prefix,
)
from nps_ctl.check.model import Finding, exit_code, worst_level
from nps_ctl.check.npc_log import Outage
from nps_ctl.check.units import format_duration, parse_duration
from nps_ctl.deploy import DeployResult

HOST = "nps-europe.example.test"
SERVER = f"{HOST}:51235"
NOW = datetime.fromisoformat("2026-10-25T10:00:00+00:00").timestamp()


def _outage(start: float, length: float = 70.0, server: str = SERVER) -> Outage:
    return Outage(
        server=server,
        last_alive=start,
        detected=start + 30,
        reconnected=start + length,
        failed_attempts=2,
        reasons=["no route to host"],
    )


def test_detect_period_finds_a_regular_interval():
    starts = [i * 974.0 + (i % 3) * 5 for i in range(8)]

    period, periodic = detect_period(starts)

    assert periodic
    assert period is not None and 950 < period < 1000


def test_detect_period_rejects_irregular_gaps():
    starts = [0, 40, 400, 450, 2000, 2010, 5000, 5100]

    _, periodic = detect_period([float(s) for s in starts])

    assert not periodic


def test_detect_period_needs_enough_gaps():
    period, periodic = detect_period([0.0, 100.0, 200.0])

    assert period == 100.0
    assert not periodic


def test_detect_period_with_fewer_than_two_outages_is_empty():
    assert detect_period([]) == (None, False)
    assert detect_period([5.0]) == (None, False)


def test_summarize_with_no_outages_is_all_zero():
    summary = summarize([], NOW, 3600)

    assert summary.outages == 0
    assert summary.downtime == 0
    assert summary.median_duration is None
    assert summary.downtime_share == 0


def test_summarize_totals_and_reasons():
    outages = [_outage(NOW - 3000, 60), _outage(NOW - 2000, 100)]

    summary = summarize(outages, NOW, 3600)

    assert summary.outages == 2
    assert summary.downtime == 160
    assert summary.median_duration == 80
    assert summary.max_duration == 100
    assert summary.failed_attempts == 4
    assert summary.reasons == {"no route to host": 2}
    assert not summary.still_open


def test_summarize_marks_an_unfinished_last_outage_open():
    open_outage = _outage(NOW - 100)
    open_outage.reconnected = None

    summary = summarize([open_outage], NOW, 3600)

    assert summary.still_open
    assert summary.downtime == 100


def test_assess_reports_flapping_and_period():
    outages = [_outage(NOW - 7000 + i * 974) for i in range(6)]

    findings = assess(summarize(outages, NOW, 7200), True, "c -> europe")

    codes = [finding.code for finding in findings]
    assert "link_flapping" in codes
    assert "link_periodic" in codes
    flapping = next(f for f in findings if f.code == "link_flapping")
    assert "6 outages" in flapping.message
    assert "no route to host x6" in flapping.message


def test_assess_down_link_is_an_error():
    findings = assess(summarize([], NOW, 3600), False, "c -> europe")

    assert findings[0].level == "error"
    assert findings[0].code == "link_down"


def test_assess_clean_link_is_a_single_info_finding():
    findings = assess(summarize([], NOW, 3600), True, "c -> europe")

    assert [f.code for f in findings] == ["link_stable"]
    assert findings[0].level == "info"


def test_assess_open_outage_with_a_socket_is_flagged():
    open_outage = _outage(NOW - 100)
    open_outage.reconnected = None

    findings = assess(summarize([open_outage], NOW, 3600), True, "c -> europe")

    assert any(f.code == "outage_open" for f in findings)


def test_worst_level_and_exit_code():
    findings = [
        Finding("info", "a", "s", "m"),
        Finding("warn", "b", "s", "m"),
    ]

    assert worst_level(findings) == "warn"
    assert worst_level([]) == "info"
    assert exit_code(findings, "warn") == 1
    assert exit_code(findings, "error") == 0
    assert exit_code([], "warn") == 0


def test_parse_and_format_duration():
    assert parse_duration("90") == 90
    assert parse_duration("15m") == 900
    assert parse_duration("6h") == 21600
    assert parse_duration("2d") == 172800
    assert parse_duration("1.5h") == 5400
    for bad in ("", "abc", "0", "-5m", "5x"):
        with pytest.raises(ValueError):
            parse_duration(bad)
    assert format_duration(None) == "-"
    assert format_duration(72) == "1m12s"
    assert format_duration(974) == "16m14s"
    assert format_duration(7500) == "2h05m"
    assert format_duration(5) == "5s"


def test_build_script_quotes_inputs_and_rejects_unsafe_servers():
    script = build_script([SERVER], "/var/log/npc.log", 1000, "sudo ")

    assert "for s in " + SERVER in script
    assert "sudo tail -c 1000 /var/log/npc.log" in script
    with pytest.raises(ValueError):
        build_script(["host;rm -rf /:1"], "/var/log/npc.log", 1000)
    with pytest.raises(ValueError):
        build_script(["nohostport"], "/var/log/npc.log", 1000)


def test_sudo_prefix():
    assert sudo_prefix("") == ""
    assert sudo_prefix("root") == ""
    assert sudo_prefix("deploy") == "sudo "


def _remote_output(established: bool = True, pid: str = "4242", log: str = "") -> str:
    peers = "ESTAB 192.0.2.7:51235\n" if established else "ESTAB 192.0.2.99:51235\n"
    return (
        f"NOW {int(NOW)}\nPID {pid}\n"
        f"SERVER {HOST} 51235 192.0.2.7 2001:db8::7\n"
        "ESTAB 127.0.0.1:54981\n"
        f"{peers}"
        f"LOG_BEGIN\n{log}\nLOG_END\n"
    )


def test_parse_output_matches_established_sockets_by_ip_and_port():
    pid, now, servers, log = parse_output(_remote_output(log="line1\nline2"))

    assert pid == "4242"
    assert now == int(NOW)
    assert servers[0].host == HOST
    assert servers[0].ips == ["192.0.2.7", "2001:db8::7"]
    assert servers[0].established
    assert log == "line1\nline2"


def test_parse_output_without_a_matching_socket_is_not_established():
    _, _, servers, _ = parse_output(_remote_output(established=False))

    assert not servers[0].established


def test_parse_output_understands_bracketed_ipv6_peers():
    out = _remote_output(established=False).replace(
        "ESTAB 192.0.2.99:51235", "ESTAB [2001:db8::7]:51235"
    )

    _, _, servers, _ = parse_output(out)

    assert servers[0].established


def test_parse_output_reports_a_missing_npc_process():
    pid, _, _, _ = parse_output(_remote_output(pid=""))

    assert pid == ""


def _cycle_log(start_iso: str, reconnect_iso: str) -> str:
    def line(time: str, message: str) -> str:
        return json.dumps(
            {"level": "info", "time": time, "caller": "x", "message": message}
        )

    return "\n".join(
        [
            line(
                start_iso,
                "mux: ping timeout, last alive "
                + start_iso.replace("T", " ").replace("+00:00", " +0000 UTC")
                + " timeout 30s",
            ),
            line(start_iso, f"Start server: {SERVER} vkey: X"),
            line(reconnect_iso, f"Successful connection with server {SERVER}"),
        ]
    )


class FakeSsh:
    def __init__(self, output: str | None = None, ok: bool = True, message: str = ""):
        self.output = output
        self.ok = ok
        self.message = message
        self.calls: list[tuple[str, dict]] = []

    def __call__(self, ssh_host, script, timeout=120, ssh_user=""):
        self.calls.append((ssh_host, {"timeout": timeout, "ssh_user": ssh_user}))
        return DeployResult(self.ok, self.message, stdout=self.output or "")


def test_collect_client_returns_events_and_server_state():
    log = _cycle_log("2026-10-25T09:00:00+00:00", "2026-10-25T09:01:10+00:00")
    ssh = FakeSsh(_remote_output(log=log))

    snapshot = collect_client("usa2", "cloud.usa2", [SERVER], ssh=ssh)

    assert not snapshot.error
    assert snapshot.npc_pid == "4242"
    assert [e.kind for e in snapshot.events] == [
        "ping_timeout",
        "start_server",
        "connected",
    ]
    assert ssh.calls[0][0] == "cloud.usa2"


def test_collect_client_surfaces_ssh_failure_without_raising():
    snapshot = collect_client(
        "usa2", "cloud.usa2", [SERVER], ssh=FakeSsh(ok=False, message="SSH error")
    )

    assert snapshot.error == "SSH error"
    assert snapshot.servers == []


def test_collect_client_flags_a_stopped_npc():
    snapshot = collect_client(
        "usa2", "cloud.usa2", [SERVER], ssh=FakeSsh(_remote_output(pid=""))
    )

    assert snapshot.error == "npc is not running"
    assert snapshot.servers


def test_report_for_only_counts_outages_inside_the_window():
    old = _cycle_log("2026-10-24T01:00:00+00:00", "2026-10-24T01:01:00+00:00")
    new = _cycle_log("2026-10-25T09:00:00+00:00", "2026-10-25T09:01:10+00:00")
    snapshot = collect_client(
        "usa2",
        "cloud.usa2",
        [SERVER],
        ssh=FakeSsh(_remote_output(log=old + "\n" + new)),
    )

    reports, unattributed = report_for(snapshot, 6 * 3600, {HOST: "nps-europe"})
    (report,) = reports
    assert unattributed == []

    assert report.summary.outages == 1
    assert report.edge == "nps-europe"
    assert report.established


class FakeCluster:
    def __init__(self):
        self.edges = {
            "nps-europe": SimpleNamespace(api_url=f"https://{HOST}"),
        }
        self.clients = {
            "usa2": SimpleNamespace(
                name="usa2", ssh_host="cloud.usa2", ssh_user="", edges=["nps-europe"]
            ),
            "broken": SimpleNamespace(
                name="broken", ssh_host="cloud.bad", ssh_user="", edges=["nps-europe"]
            ),
        }

    def get_npc_client(self, name):
        return self.clients[name]

    def get_edge(self, name):
        return self.edges.get(name)

    def get_server_addrs_for_npc(self, config):
        return SERVER


def test_collect_links_separates_reports_from_unreachable_clients():
    good = _remote_output()

    def ssh(ssh_host, script, timeout=120, ssh_user=""):
        if ssh_host == "cloud.bad":
            return DeployResult(False, "SSH command timed out")
        return DeployResult(True, "ok", stdout=good)

    reports, errors, unattributed = collect_links(
        FakeCluster(), ["usa2", "broken"], ssh=ssh
    )

    assert [r.client for r in reports] == ["usa2"]
    assert errors == {"broken": "SSH command timed out"}
    assert unattributed == {}
    assert reports[0].to_dict()["edge"] == "nps-europe"
