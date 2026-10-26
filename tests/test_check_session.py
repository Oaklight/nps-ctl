"""Tests for correlation, verdicts, probe sessions and stress profiles."""

from __future__ import annotations

import json
import shlex
import threading
import time
from datetime import datetime, UTC
from http.server import ThreadingHTTPServer
from types import SimpleNamespace

import pytest

from nps_ctl import client_mgmt, host
from nps_ctl.check import loadgen
from nps_ctl.check.correlate import correlate
from nps_ctl.check.echo_server import Handler
from nps_ctl.check.npc_log import Outage
from nps_ctl.check.session import (
    DOMAIN_SUFFIX,
    LAYER_CLIENT_LOCAL,
    LAYER_VIA_NPS,
    REMARK,
    NpsMapping,
    ProbeSession,
    SessionError,
    echo_start_script,
    echo_stop_script,
    load_script,
    parse_handle,
)
from nps_ctl.check.stress import PROFILES, run_stress
from nps_ctl.check.verdict import assess_run
from nps_ctl.deploy import DeployResult
from tests.test_check_loadgen import FaultProxy

EDGE = "nps-x"
CLIENT = "client-a"
SERVER = "nps-x.example.test:51235"


def _outage(start: float, end: float | None) -> Outage:
    return Outage(SERVER, start, start + 30, end)


def _result(total=10, **outcomes):
    outcomes = outcomes or {"ok": total}
    return {
        "total": sum(outcomes.values()),
        "outcomes": outcomes,
        "failures": [
            {"outcome": k, "detail": "x", "t": 0.0, "i": 0, "ms": 1.0}
            for k in outcomes
            if k != "ok"
        ],
        "failure_times": [],
        "started": 0.0,
        "finished": 1.0,
    }


# --- correlate ---


def test_correlate_counts_failures_inside_padded_windows():
    outages = [_outage(100, 160)]

    result = correlate([95, 120, 170, 400], outages, 0, 1000, pad=15)

    assert result.failures == 4
    assert result.inside == 3
    assert result.share == 0.75
    assert result.by_outage[0]["failures"] == 3


def test_correlate_chance_is_the_covered_share_of_the_run():
    result = correlate([], [_outage(100, 200)], 0, 1000, pad=0)

    assert result.chance == pytest.approx(0.1)
    assert result.share == 0


def test_correlate_merges_overlapping_windows_for_chance():
    result = correlate([], [_outage(100, 200), _outage(150, 250)], 0, 1000, pad=0)

    assert result.chance == pytest.approx(0.15)


def test_correlate_treats_an_open_outage_as_lasting_to_the_run_end():
    result = correlate([900], [_outage(800, None)], 0, 1000, pad=0)

    assert result.inside == 1


def test_correlate_ignores_outages_outside_the_run():
    result = correlate([], [_outage(5000, 5100)], 0, 1000)

    assert result.by_outage == []
    assert result.chance == 0


# --- verdict ---


def test_verdict_clean_path():
    findings = assess_run("s", [_result()], [_result(40)])

    assert [f.code for f in findings] == ["path_clean"]


def test_verdict_failed_baseline_makes_the_run_inconclusive():
    findings = assess_run("s", [_result(corrupt=1, ok=9)], [_result(corrupt=5)])

    assert [f.code for f in findings] == ["baseline_failed"]


def test_verdict_damaged_bodies_are_path_corruption():
    findings = assess_run("s", [_result()], [_result(ok=30, corrupt=2)])

    assert findings[0].code == "path_corruption"
    assert "2 of 32" in findings[0].message


def test_verdict_transport_errors_are_path_errors():
    findings = assess_run("s", [_result()], [_result(ok=30, conn_error=2)])

    assert findings[0].code == "path_errors"


def test_verdict_with_no_requests_is_an_error():
    findings = assess_run("s", [_result()], [{"total": 0, "outcomes": {}}])

    assert findings[0].code == "no_requests"


def test_verdict_reports_failures_inside_outage_windows():
    corr = correlate([110, 120, 130, 140], [_outage(100, 160)], 0, 1000, pad=0)

    findings = assess_run("s", [_result()], [_result(ok=30, truncated=4)], corr)

    assert "failures_in_outage_window" in [f.code for f in findings]


def test_verdict_reports_failures_unexplained_by_outages():
    corr = correlate([10, 20, 30], [_outage(500, 560)], 0, 1000, pad=0)

    findings = assess_run("s", [_result()], [_result(ok=30, truncated=3)], corr)

    assert "failures_outside_outages" in [f.code for f in findings]


def test_verdict_reports_partial_overlap():
    corr = correlate([510, 520, 10, 20], [_outage(500, 560)], 0, 1000, pad=0)

    findings = assess_run("s", [_result()], [_result(ok=30, truncated=4)], corr)

    assert "failures_partly_in_outages" in [f.code for f in findings]


# --- scripts ---


def test_echo_start_script_embeds_the_service_and_a_ttl():
    script = echo_start_script(ttl=120)

    assert "class Handler" in script
    assert "--ttl 120" in script
    assert script.count("NPS_CTL_END") == 2


def test_echo_stop_script_only_accepts_handles_it_created():
    assert "kill 42" in echo_stop_script("/tmp/nps-ctl-check.abc123", "42")
    for directory, pid in (
        ("/etc", "42"),
        ("/tmp/nps-ctl-check.abc; rm -rf /", "42"),
        ("/tmp/nps-ctl-check.abc", "42; reboot"),
        ("/tmp/other.abc", "42"),
    ):
        with pytest.raises(ValueError):
            echo_stop_script(directory, pid)


def test_load_script_carries_the_spec_and_the_generator():
    script = load_script({"port": 99, "seed": "x"})

    assert script.startswith("python3 - ")
    assert '"port": 99' in script
    assert "def run(spec" in script


def test_parse_handle_reads_dir_port_and_pid():
    assert parse_handle("DIR /tmp/nps-ctl-check.a1\nPORT 4000\nPID 77\n") == (
        "/tmp/nps-ctl-check.a1",
        4000,
        "77",
    )


@pytest.mark.parametrize(
    "stdout",
    ["", "DIR /tmp/x\nPORT \nPID 1", "ERROR no python3", "DIR /tmp/x\nPORT 0\nPID 1"],
)
def test_parse_handle_rejects_an_echo_that_did_not_start(stdout):
    with pytest.raises(SessionError):
        parse_handle(stdout)


# --- fakes ---


class FakeCluster:
    def __init__(self, edges=(EDGE,), ssh_host="edge.host"):
        self.edge_config = SimpleNamespace(
            ssh_host=ssh_host, api_url="https://nps-x.example.test"
        )
        self.npc = SimpleNamespace(
            ssh_host="client.host", ssh_user="", edges=list(edges), remark=CLIENT
        )

    def get_edge(self, name):
        return self.edge_config if name == EDGE else None

    def get_npc_client(self, name):
        return self.npc if name == CLIENT else None

    def get_server_addrs_for_npc(self, config):
        return SERVER


class FakeMapping:
    def __init__(
        self,
        fail_add=False,
        fail_remove=False,
        orphan_on_add=False,
        lists_nothing=False,
    ):
        self.fail_add = fail_add
        self.fail_remove = fail_remove
        self.lists_nothing = lists_nothing
        self.write_attempted = False
        # The edge accepts the create, then the id lookup misses it.
        self.orphan_on_add = orphan_on_add
        self.added: list[tuple] = []
        self.removed: list[tuple] = []
        self.rows: list[tuple[str, int]] = []

    def add(self, edge, client_remark, domain, target):
        if self.fail_add:
            raise SessionError("nps refused")
        self.write_attempted = True
        self.added.append((edge, client_remark, domain, target))
        if not self.lists_nothing:
            self.rows.append((domain, 7))
        if self.orphan_on_add:
            raise SessionError(
                f"host mapping {domain} not found on {edge} after adding it"
            )
        return 7

    def remove(self, edge, host_id, domain):
        if self.fail_remove:
            raise SessionError("nps unreachable")
        self.removed.append((edge, host_id, domain))
        self.rows = [r for r in self.rows if r[1] != host_id]

    def remove_unclaimed(self, edge, domain):
        if self.fail_remove:
            raise SessionError("nps unreachable")
        mine = [r for r in self.rows if r[0] == domain]
        self.rows = [r for r in self.rows if r[0] != domain]
        self.removed.extend((edge, host_id, domain) for _, host_id in mine)
        return len(mine)


class World:
    """A local stand-in for the client host, the edge host and the tunnel."""

    def __init__(self, fault: str | None = None, echo_dead: bool = False):
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.echo_port = self.server.server_address[1]
        self.proxy = FaultProxy(self.echo_port, fault) if fault else None
        self.echo_dead = echo_dead
        self.tunnel_port = (
            1 if echo_dead else (self.proxy.port if self.proxy else self.echo_port)
        )
        self.calls: list[tuple[str, str]] = []
        self.outage_log = ""

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        if self.proxy:
            self.proxy.close()

    def ssh(self, ssh_host, script, timeout=120, ssh_user=""):
        kind = self._kind(script)
        self.calls.append((ssh_host, kind))
        if kind == "echo_start":
            port = 1 if self.echo_dead else self.echo_port
            return DeployResult(
                True, "ok", stdout=f"DIR /tmp/nps-ctl-check.t1\nPORT {port}\nPID 55\n"
            )
        if kind == "echo_stop":
            return DeployResult(True, "ok", stdout="stopped\n")
        if kind == "port":
            return DeployResult(True, "ok", stdout="30080\n")
        if kind == "load":
            return self._load(ssh_host, script)
        if kind == "links":
            return DeployResult(True, "ok", stdout=self._links_output())
        raise AssertionError(f"unexpected script on {ssh_host}: {script[:80]}")

    @staticmethod
    def _kind(script):
        if "echo.py" in script and "NPS_CTL_END" in script:
            return "echo_start"
        if script.startswith("kill "):
            return "echo_stop"
        if "http_proxy_port" in script:
            return "port"
        if script.startswith("python3 - "):
            return "load"
        if "LOG_BEGIN" in script:
            return "links"
        return "other"

    def _load(self, ssh_host, script):
        spec = json.loads(shlex.split(script.splitlines()[0])[2])
        if ssh_host == "edge.host":
            spec["port"] = self.tunnel_port
        result = loadgen.run(spec)
        return DeployResult(True, "ok", stdout=json.dumps(result) + "\n")

    def _links_output(self):
        now = int(time.time())
        return (
            f"NOW {now}\nPID 99\nSERVER nps-x.example.test 51235 192.0.2.7\n"
            f"ESTAB 192.0.2.7:51235\nLOG_BEGIN\n{self.outage_log}\nLOG_END\n"
        )

    def open_outage_now(self):
        """Log an outage that began a moment ago and has not ended."""
        start = time.time() - 5
        stamp = datetime.fromtimestamp(start, UTC)
        iso = stamp.isoformat()
        alive = stamp.strftime("%Y-%m-%d %H:%M:%S.%f") + " +0000 UTC"
        self.outage_log = "\n".join(
            [
                json.dumps(
                    {
                        "time": iso,
                        "message": f"mux: ping timeout, last alive {alive} timeout 30s",
                    }
                ),
                json.dumps({"time": iso, "message": f"Start server: {SERVER} vkey: X"}),
            ]
        )


@pytest.fixture
def world():
    made = []

    def make(**kwargs):
        w = World(**kwargs)
        made.append(w)
        return w

    yield make
    for w in made:
        w.close()


def _session(w, mapping=None, cluster=None):
    return ProbeSession(
        cluster or FakeCluster(),
        EDGE,
        CLIENT,
        ssh=w.ssh,
        mapping=mapping or FakeMapping(),
        sleep=lambda _s: None,
    )


# --- session lifecycle ---


def test_session_maps_a_throwaway_domain_to_the_echo_and_cleans_up(world):
    w = world()
    mapping = FakeMapping()

    with _session(w, mapping) as session:
        assert mapping.added == [
            (EDGE, CLIENT, session.domain, f"127.0.0.1:{w.echo_port}")
        ]
        assert session.domain.endswith(DOMAIN_SUFFIX)
        assert mapping.removed == []

    assert mapping.removed == [(EDGE, 7, session.domain)]
    assert ("client.host", "echo_stop") in w.calls
    assert session.cleanup_problems == []


def test_session_runs_the_baseline_on_the_client_and_the_tunnel_on_the_edge(world):
    w = world()

    with _session(w) as session:
        base = session.run_load(LAYER_CLIENT_LOCAL, {"size": 4096, "count": 4})
        tunnel = session.run_load(LAYER_VIA_NPS, {"size": 4096, "count": 4})

    assert base.where == "client.host" and base.result["outcomes"] == {"ok": 4}
    assert tunnel.where == "edge.host" and tunnel.result["outcomes"] == {"ok": 4}
    assert tunnel.to_dict()["layer"] == LAYER_VIA_NPS


def test_each_load_run_uses_its_own_seed(world):
    w = world()
    seeds = []
    real = w.ssh

    def spy(ssh_host, script, timeout=120, ssh_user=""):
        if script.startswith("python3 - "):
            seeds.append(json.loads(shlex.split(script.splitlines()[0])[2])["seed"])
        return real(ssh_host, script, timeout, ssh_user)

    session = ProbeSession(
        FakeCluster(),
        EDGE,
        CLIENT,
        ssh=spy,
        mapping=FakeMapping(),
        sleep=lambda _s: None,
    )
    with session:
        session.run_load(LAYER_VIA_NPS, {"size": 100, "count": 1})

    assert len(seeds) == len(set(seeds)) >= 2


def test_setup_failure_after_the_echo_started_still_stops_the_echo(world):
    w = world()
    mapping = FakeMapping(fail_add=True)

    with pytest.raises(SessionError, match="nps refused"):
        with _session(w, mapping):
            pytest.fail("the session must not open")

    assert ("client.host", "echo_stop") in w.calls
    assert mapping.removed == []


def test_unreachable_mapping_removes_everything_it_created(world):
    w = world(echo_dead=True)
    mapping = FakeMapping()

    with pytest.raises(SessionError, match="did not become reachable"):
        with _session(w, mapping):
            pytest.fail("the session must not open")

    assert len(mapping.removed) == 1
    assert ("client.host", "echo_stop") in w.calls


def test_create_that_returns_no_id_is_reclaimed_by_domain(world):
    w = world()
    mapping = FakeMapping(orphan_on_add=True)

    with pytest.raises(SessionError, match="not found .* after adding it"):
        with _session(w, mapping):
            pytest.fail("the session must not open")

    assert mapping.rows == []
    assert mapping.removed == [(EDGE, 7, mapping_domain(mapping))]
    assert ("client.host", "echo_stop") in w.calls


def mapping_domain(mapping):
    return mapping.added[0][2]


def test_a_create_refused_before_the_write_reports_nothing_to_clean(world):
    w = world()
    mapping = FakeMapping(fail_add=True)
    session = _session(w, mapping)

    with pytest.raises(SessionError, match="nps refused"):
        with session:
            pytest.fail("the session must not open")

    assert session.cleanup_problems == []
    assert ("client.host", "echo_stop") in w.calls


def test_a_sweep_that_finds_nothing_is_not_a_problem(world):
    w = world()
    # The edge accepted the create but lists no row for it, so nothing is left.
    mapping = FakeMapping(orphan_on_add=True, lists_nothing=True)
    session = _session(w, mapping)

    with pytest.raises(SessionError):
        with session:
            pytest.fail("the session must not open")

    assert mapping.removed == []
    assert session.cleanup_problems == []


def test_reclaim_that_fails_is_reported_with_the_manual_command(world):
    w = world()
    mapping = FakeMapping(orphan_on_add=True, fail_remove=True)
    session = _session(w, mapping)

    with pytest.raises(SessionError):
        with session:
            pytest.fail("the session must not open")

    (problem,) = session.cleanup_problems
    assert "may still be on" in problem
    assert f"nps-ctl host del -e {EDGE}" in problem


def test_a_clean_run_does_not_claim_an_unclaimed_mapping(world):
    w = world()
    mapping = FakeMapping()
    session = _session(w, mapping)

    with session:
        pass

    assert mapping.removed == [(EDGE, 7, session.domain)]
    assert session.cleanup_problems == []


def test_cleanup_reports_a_mapping_it_could_not_remove(world):
    w = world()
    session = _session(w, FakeMapping(fail_remove=True))

    with session:
        pass

    (problem,) = session.cleanup_problems
    assert session.domain in problem
    assert f"nps-ctl host del -e {EDGE}" in problem


def test_cleanup_reports_an_echo_that_could_not_be_stopped(world):
    w = world()
    real = w.ssh

    def flaky(ssh_host, script, timeout=120, ssh_user=""):
        if script.startswith("kill "):
            return DeployResult(False, "SSH command timed out")
        return real(ssh_host, script, timeout, ssh_user)

    session = ProbeSession(
        FakeCluster(),
        EDGE,
        CLIENT,
        ssh=flaky,
        mapping=FakeMapping(),
        sleep=lambda _s: None,
    )
    with session:
        pass

    assert any("may still run" in p for p in session.cleanup_problems)


@pytest.mark.parametrize(
    "cluster, message",
    [
        (FakeCluster(edges=("other",)), "not connected to edge"),
        (FakeCluster(ssh_host=""), "no ssh_host"),
    ],
)
def test_session_rejects_an_unusable_topology(cluster, message):
    with pytest.raises(SessionError, match=message):
        ProbeSession(cluster, EDGE, CLIENT, mapping=FakeMapping())


def test_session_rejects_unknown_names():
    with pytest.raises(SessionError, match="edge 'nope' not found"):
        ProbeSession(FakeCluster(), "nope", CLIENT, mapping=FakeMapping())
    with pytest.raises(SessionError, match="client 'nope' not found"):
        ProbeSession(FakeCluster(), EDGE, "nope", mapping=FakeMapping())


def test_a_generator_that_prints_nothing_is_an_error_not_a_crash(world):
    w = world()
    real = w.ssh

    def silent(ssh_host, script, timeout=120, ssh_user=""):
        if script.startswith("python3 - ") and '"count": 7' in script:
            return DeployResult(True, "ok", stdout="", stderr="Traceback ...")
        return real(ssh_host, script, timeout, ssh_user)

    session = ProbeSession(
        FakeCluster(),
        EDGE,
        CLIENT,
        ssh=silent,
        mapping=FakeMapping(),
        sleep=lambda _s: None,
    )
    with session:
        run = session.run_load(LAYER_VIA_NPS, {"size": 100, "count": 7})

    assert run.result is None and "unparseable" in run.error


def test_unknown_layer_is_a_programming_error(world):
    with _session(world()) as session:
        with pytest.raises(ValueError):
            session.run_load("bogus", {})


# --- stress ---


def test_profiles_define_positive_work():
    assert set(PROFILES) == {"smoke", "ladder", "slow", "churn", "soak"}
    for name, build in PROFILES.items():
        steps = build(30.0)
        assert steps, name
        for step in steps:
            assert step.spec.get("count", 0) > 0 or step.spec.get("duration", 0) > 0
    assert len(PROFILES["ladder"](0)) == 10
    assert PROFILES["soak"](42.0)[0].spec["duration"] == 42.0
    assert all(s.spec["mode"] == "slow" for s in PROFILES["slow"](0))


def test_stress_on_a_healthy_path_is_clean(world):
    w = world()
    seen = []

    with _session(w) as session:
        report = run_stress(session, "smoke", on_step=seen.append)

    assert [f.code for f in report.findings] == ["path_clean"]
    assert len(report.steps) == 1 and report.steps[0].failed == 0
    assert seen[0].startswith("baseline")
    assert report.to_dict()["profile"] == "smoke"


def test_stress_flags_a_damaging_tunnel_while_the_baseline_stays_clean(world):
    w = world(fault="flip")

    with _session(w) as session:
        report = run_stress(session, "smoke")

    assert report.findings[0].code == "path_corruption"
    assert report.steps[0].failed == 30
    assert report.baseline[0]["outcomes"] == {"ok": 20}


def test_stress_correlates_failures_with_a_logged_outage(world):
    w = world(fault="truncate")
    w.open_outage_now()

    with _session(w) as session:
        report = run_stress(session, "smoke")

    codes = [f.code for f in report.findings]
    assert "path_corruption" in codes
    assert "failures_in_outage_window" in codes
    assert report.correlation is not None and report.correlation.share == 1.0


def test_stress_skips_the_tunnel_when_the_baseline_is_broken(world):
    w = world()
    real = w.ssh

    def break_baseline(ssh_host, script, timeout=120, ssh_user=""):
        if ssh_host == "client.host" and '"count": 20' in script:
            spec = json.loads(shlex.split(script.splitlines()[0])[2])
            spec["port"] = 1
            result = loadgen.run({**spec, "timeout": 1})
            return DeployResult(True, "ok", stdout=json.dumps(result))
        return real(ssh_host, script, timeout, ssh_user)

    session = ProbeSession(
        FakeCluster(),
        EDGE,
        CLIENT,
        ssh=break_baseline,
        mapping=FakeMapping(),
        sleep=lambda _s: None,
    )
    with session:
        report = run_stress(session, "smoke")

    assert [f.code for f in report.findings] == ["baseline_failed"]
    assert report.steps == []


def test_stress_rejects_an_unknown_profile(world):
    with _session(world()) as session:
        with pytest.raises(KeyError):
            run_stress(session, "nope")


# --- NpsMapping against the NPS API helpers ---


def _nps_world(monkeypatch, *, host_remark=REMARK, host_name=None):
    state = {"hosts": {}, "added": [], "deleted": []}
    nps = object()
    cluster = SimpleNamespace(get_client=lambda edge: nps if edge == EDGE else None)

    monkeypatch.setattr(
        client_mgmt,
        "list_clients",
        lambda n, search="": [
            {"Id": 3, "Remark": CLIENT},
            {"Id": 4, "Remark": "other"},
        ],
    )

    def add_host(n, client_id, host, target, remark="", **kw):
        state["added"].append((client_id, host, target, remark))
        state["hosts"][11] = {
            "Id": 11,
            "Host": host_name or host,
            "Remark": host_remark,
        }
        return True

    monkeypatch.setattr(host, "add_host", add_host)
    monkeypatch.setattr(
        host, "list_hosts", lambda n, search="": list(state["hosts"].values())
    )
    monkeypatch.setattr(host, "get_host", lambda n, hid: state["hosts"].get(hid))

    def del_host(n, hid):
        state["deleted"].append(hid)
        state["hosts"].pop(hid, None)
        return True

    monkeypatch.setattr(host, "del_host", del_host)
    return NpsMapping(cluster), state


def test_nps_mapping_adds_for_the_right_client_and_returns_the_host_id(monkeypatch):
    mapping, state = _nps_world(monkeypatch)

    host_id = mapping.add(EDGE, CLIENT, "d.invalid", "127.0.0.1:99")

    assert host_id == 11
    assert state["added"] == [(3, "d.invalid", "127.0.0.1:99", REMARK)]


def test_nps_mapping_removes_only_what_it_created(monkeypatch):
    mapping, state = _nps_world(monkeypatch)
    mapping.add(EDGE, CLIENT, "d.invalid", "127.0.0.1:99")

    mapping.remove(EDGE, 11, "d.invalid")

    assert state["deleted"] == [11]


def test_nps_mapping_refuses_to_delete_a_foreign_host(monkeypatch):
    mapping, state = _nps_world(monkeypatch, host_remark="somebody's real site")
    mapping.add(EDGE, CLIENT, "d.invalid", "127.0.0.1:99")

    with pytest.raises(SessionError, match="not the mapping this session created"):
        mapping.remove(EDGE, 11, "d.invalid")

    assert state["deleted"] == []


def test_nps_mapping_remove_is_a_noop_when_the_host_is_already_gone(monkeypatch):
    mapping, state = _nps_world(monkeypatch)

    mapping.remove(EDGE, 999, "d.invalid")

    assert state["deleted"] == []


def test_nps_mapping_finds_the_entry_without_get_host(monkeypatch):
    # get_host answered None on a real legacy edge while the list still had the
    # row, which silently skipped the delete; removal must not depend on it.
    mapping, state = _nps_world(monkeypatch)
    monkeypatch.setattr(host, "get_host", lambda n, hid: None)
    mapping.add(EDGE, CLIENT, "d.invalid", "127.0.0.1:99")

    mapping.remove(EDGE, 11, "d.invalid")

    assert state["deleted"] == [11]


def test_nps_mapping_raises_when_the_row_survives_the_delete(monkeypatch):
    mapping, state = _nps_world(monkeypatch)
    mapping.add(EDGE, CLIENT, "d.invalid", "127.0.0.1:99")
    # A delete that reports success without removing anything must not pass.
    monkeypatch.setattr(host, "del_host", lambda n, hid: True)

    with pytest.raises(SessionError, match="still lists host 11"):
        mapping.remove(EDGE, 11, "d.invalid")

    assert 11 in state["hosts"]


def test_nps_mapping_reclaims_a_row_whose_create_returned_no_id(monkeypatch):
    mapping, state = _nps_world(monkeypatch)
    state["hosts"][21] = {"Id": 21, "Host": "d.invalid", "Remark": REMARK}
    state["hosts"][22] = {"Id": 22, "Host": "other.invalid", "Remark": REMARK}

    removed = mapping.remove_unclaimed(EDGE, "d.invalid")

    assert removed == 1
    assert state["deleted"] == [21]
    assert 22 in state["hosts"]


def test_nps_mapping_reclaim_leaves_a_foreign_row_alone(monkeypatch):
    mapping, state = _nps_world(monkeypatch, host_remark="somebody's real site")
    state["hosts"][21] = {
        "Id": 21,
        "Host": "d.invalid",
        "Remark": "somebody's real site",
    }

    removed = mapping.remove_unclaimed(EDGE, "d.invalid")

    assert removed == 0
    assert state["deleted"] == []


def test_nps_mapping_reclaim_raises_when_the_row_survives(monkeypatch):
    mapping, state = _nps_world(monkeypatch)
    state["hosts"][21] = {"Id": 21, "Host": "d.invalid", "Remark": REMARK}
    monkeypatch.setattr(host, "del_host", lambda n, hid: True)

    with pytest.raises(SessionError, match="still lists host 21"):
        mapping.remove_unclaimed(EDGE, "d.invalid")


def test_port_discovery_needs_only_grep():
    seen = []

    def ssh(ssh_host, script, timeout=120, ssh_user=""):
        seen.append(script)
        return DeployResult(True, "ok", stdout="30080\n")

    session = ProbeSession(
        FakeCluster(),
        EDGE,
        CLIENT,
        ssh=ssh,
        mapping=FakeMapping(),
        sleep=lambda _s: None,
    )
    session.http_proxy_port = None

    assert session._discover_http_proxy_port() == 30080
    assert "python3" not in seen[0]
    assert "http_proxy_port" in seen[0]


def test_port_discovery_falls_back_when_nps_conf_has_no_port():
    def ssh(ssh_host, script, timeout=120, ssh_user=""):
        return DeployResult(True, "ok", stdout="")

    session = ProbeSession(
        FakeCluster(),
        EDGE,
        CLIENT,
        ssh=ssh,
        mapping=FakeMapping(),
        sleep=lambda _s: None,
    )
    session.http_proxy_port = None

    assert session._discover_http_proxy_port() == 30080


def test_nps_mapping_reports_an_unknown_client(monkeypatch):
    mapping, _ = _nps_world(monkeypatch)

    with pytest.raises(SessionError, match="client 'ghost' not found"):
        mapping.add(EDGE, "ghost", "d.invalid", "127.0.0.1:99")


def test_nps_mapping_reports_an_unknown_edge(monkeypatch):
    mapping, _ = _nps_world(monkeypatch)

    with pytest.raises(SessionError, match="no API client"):
        mapping.add("nope", CLIENT, "d.invalid", "127.0.0.1:99")
