"""Tests for the ``check`` command group: parsing, usage errors and exit codes."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

import nps_ctl.cli.cmd_check as cmd_check
from nps_ctl.check.correlate import Correlation
from nps_ctl.check.links import LinkReport
from nps_ctl.check.analysis import assess, summarize
from nps_ctl.check.model import Finding
from nps_ctl.check.stress import PROFILES, StepReport, StressReport
from nps_ctl.cli.parser import STRESS_PROFILES, create_parser
from nps_ctl.check.units import parse_size


class FakeCluster:
    edge_names = ["nps-x"]
    npc_client_names = ["client-a", "client-b"]


def _parse(*argv):
    return create_parser().parse_args(["--config", "c.toml", *argv])


def _link_report(established=True, outages=()):
    summary = summarize(list(outages), 1000.0, 3600.0)
    return LinkReport(
        client="client-a",
        server="nps-x.test:51235",
        edge="nps-x",
        established=established,
        summary=summary,
        outages=list(outages),
        findings=assess(summary, established, "client-a -> nps-x"),
    )


def _patch_cluster(monkeypatch, cluster=None):
    monkeypatch.setattr(
        cmd_check, "NPSCluster", lambda config: cluster or FakeCluster()
    )


# --- parsing ---


def test_stress_profile_choices_match_the_implemented_profiles():
    assert set(STRESS_PROFILES) == set(PROFILES)


def test_links_defaults():
    args = _parse("check", "links")

    assert args.command == "check" and args.subcommand == "links"
    assert args.since == "6h"
    assert args.fail_on == "warn"
    assert args.client is None


def test_probe_requires_edge_and_client():
    for argv in (
        ("check", "probe"),
        ("check", "probe", "-e", "nps-x"),
        ("check", "probe", "-c", "client-a"),
    ):
        with pytest.raises(SystemExit) as exc:
            _parse(*argv)
        assert exc.value.code == 2


def test_probe_arguments():
    args = _parse(
        "check",
        "probe",
        "-e",
        "nps-x",
        "-c",
        "client-a",
        "--size",
        "1M",
        "--count",
        "5",
        "--concurrency",
        "2",
        "--mode",
        "slow",
        "-y",
        "--json",
    )

    assert (args.edge, args.client, args.size, args.mode) == (
        "nps-x",
        "client-a",
        "1M",
        "slow",
    )
    assert args.yes and args.json and args.fail_on == "error"


def test_stress_rejects_an_unknown_profile():
    with pytest.raises(SystemExit) as exc:
        _parse("check", "stress", "-e", "nps-x", "-c", "client-a", "--profile", "nope")

    assert exc.value.code == 2


def test_parse_size():
    assert parse_size("2048") == 2048
    assert parse_size("64K") == 65536
    assert parse_size("1m") == 1048576
    for bad in ("", "0", "-1", "1G", "abc", "1.5M"):
        with pytest.raises(ValueError):
            parse_size(bad)


# --- check links ---


def test_links_json_reports_links_and_exits_zero_when_stable(monkeypatch, capsys):
    _patch_cluster(monkeypatch)
    monkeypatch.setattr(
        cmd_check, "collect_links", lambda *a, **k: ([_link_report()], {}, {})
    )

    code = cmd_check.cmd_check_links(_parse("check", "links", "--json"))

    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["summary"]["links"] == 1
    assert payload["links"][0]["findings"][0]["code"] == "link_stable"


def test_links_exits_one_for_a_down_link(monkeypatch, capsys):
    _patch_cluster(monkeypatch)
    monkeypatch.setattr(
        cmd_check,
        "collect_links",
        lambda *a, **k: ([_link_report(established=False)], {}, {}),
    )

    assert cmd_check.cmd_check_links(_parse("check", "links", "--json")) == 1
    assert json.loads(capsys.readouterr().out)["summary"]["errors"] == 1


def test_links_exits_one_for_an_unreachable_client(monkeypatch, capsys):
    _patch_cluster(monkeypatch)
    monkeypatch.setattr(
        cmd_check, "collect_links", lambda *a, **k: ([], {"client-a": "SSH error"}, {})
    )

    code = cmd_check.cmd_check_links(_parse("check", "links", "--json"))

    assert code == 1
    assert json.loads(capsys.readouterr().out)["errors"] == {"client-a": "SSH error"}


def test_links_fail_on_error_ignores_warnings(monkeypatch):
    _patch_cluster(monkeypatch)
    flapping = [
        SimpleNamespace(
            server="nps-x.test:51235",
            start=i * 300.0,
            reconnected=i * 300.0 + 60,
            failed_attempts=1,
            reasons=["timeout"],
            end=lambda now, i=i: i * 300.0 + 60,
            duration=lambda now: 60.0,
        )
        for i in range(4)
    ]
    report = _link_report(outages=flapping)
    assert any(f.level == "warn" for f in report.findings)
    monkeypatch.setattr(cmd_check, "collect_links", lambda *a, **k: ([report], {}, {}))

    warn = cmd_check.cmd_check_links(_parse("check", "links", "--json"))
    error = cmd_check.cmd_check_links(
        _parse("check", "links", "--json", "--fail-on", "error")
    )

    assert (warn, error) == (1, 0)


def test_links_unknown_client_is_a_failure(monkeypatch, capsys):
    _patch_cluster(monkeypatch)

    code = cmd_check.cmd_check_links(_parse("check", "links", "-c", "ghost", "--json"))

    assert code == 1
    assert "ghost" in json.loads(capsys.readouterr().out)["error"]


def test_links_bad_duration_is_a_usage_error(monkeypatch, capsys):
    _patch_cluster(monkeypatch)

    code = cmd_check.cmd_check_links(
        _parse("check", "links", "--since", "soon", "--json")
    )

    assert code == 2


def test_links_missing_config_exits_one(monkeypatch, capsys):
    def boom(config):
        raise FileNotFoundError("no edges.toml")

    monkeypatch.setattr(cmd_check, "NPSCluster", boom)

    assert cmd_check.cmd_check_links(_parse("check", "links", "--json")) == 1
    assert "no edges.toml" in json.loads(capsys.readouterr().out)["error"]


def test_links_table_output_lists_each_link(monkeypatch, capsys):
    _patch_cluster(monkeypatch)
    monkeypatch.setattr(
        cmd_check, "collect_links", lambda *a, **k: ([_link_report()], {}, {})
    )

    code = cmd_check.cmd_check_links(_parse("check", "links", "--no-color"))

    out = capsys.readouterr().out
    assert code == 0
    assert "client-a" in out and "nps-x" in out and "link_stable" in out
    assert "All checked links are stable" in out


# --- check probe / stress ---


class FakeSession:
    opened: list = []

    def __init__(self, cluster, edge, client, http_proxy_port=None):
        self.edge, self.client = edge, client
        self.cleanup_problems = []
        FakeSession.opened.append((edge, client, http_proxy_port))

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _report(findings, failed=0):
    outcomes = {"ok": 10 - failed}
    if failed:
        outcomes["corrupt"] = failed
    report = StressReport(profile="probe")
    report.steps = [
        StepReport(
            "probe 256K x4",
            "",
            {
                "total": 10,
                "outcomes": outcomes,
                "p50_ms": 12.0,
                "p95_ms": 30.0,
                "max_ms": 41.0,
            },
        )
    ]
    report.findings = findings
    return report


@pytest.fixture
def session_env(monkeypatch):
    FakeSession.opened = []
    _patch_cluster(monkeypatch)
    monkeypatch.setattr(cmd_check, "ProbeSession", FakeSession)
    calls = {}

    def fake_run(session, profile, **kwargs):
        calls["profile"] = profile
        calls.update(kwargs)
        return calls["report"]

    monkeypatch.setattr(cmd_check, "run_stress", fake_run)
    return calls


def test_probe_clean_run_exits_zero_and_emits_json(session_env, capsys):
    session_env["report"] = _report([Finding("info", "path_clean", "s", "ok")])

    code = cmd_check.cmd_check_probe(
        _parse("check", "probe", "-e", "nps-x", "-c", "client-a", "-y", "--json")
    )

    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["findings"][0]["code"] == "path_clean"
    assert payload["cleanup_problems"] == []
    assert session_env["profile"] == "probe"
    assert session_env["steps"][0].spec["size"] == 256 * 1024
    assert FakeSession.opened == [("nps-x", "client-a", None)]


def test_probe_damage_exits_one(session_env, capsys):
    session_env["report"] = _report(
        [Finding("error", "path_corruption", "s", "2 of 10 failed")], failed=2
    )

    code = cmd_check.cmd_check_probe(
        _parse("check", "probe", "-e", "nps-x", "-c", "client-a", "-y", "--no-color")
    )

    out = capsys.readouterr().out
    assert code == 1
    assert "path_corruption" in out and "corrupt 2" in out


def test_probe_cleanup_problem_fails_the_run(session_env, monkeypatch, capsys):
    session_env["report"] = _report([Finding("info", "path_clean", "s", "ok")])

    class Leaky(FakeSession):
        def __init__(self, *a, **k):
            super().__init__(*a, **k)
            self.cleanup_problems = ["host mapping x is still on nps-x"]

    monkeypatch.setattr(cmd_check, "ProbeSession", Leaky)

    code = cmd_check.cmd_check_probe(
        _parse("check", "probe", "-e", "nps-x", "-c", "client-a", "-y", "--json")
    )

    payload = json.loads(capsys.readouterr().out)
    assert code == 1
    assert payload["cleanup_problems"] == ["host mapping x is still on nps-x"]
    assert any(f["code"] == "cleanup_failed" for f in payload["findings"])


def test_probe_reports_a_setup_failure(session_env, monkeypatch, capsys):
    from nps_ctl.check.session import SessionError

    class Refusing(FakeSession):
        def __enter__(self):
            raise SessionError("cannot start echo")

    monkeypatch.setattr(cmd_check, "ProbeSession", Refusing)

    code = cmd_check.cmd_check_probe(
        _parse("check", "probe", "-e", "nps-x", "-c", "client-a", "-y", "--json")
    )

    assert code == 1
    assert "cannot start echo" in json.loads(capsys.readouterr().out)["error"]


def test_probe_dry_run_touches_nothing(session_env, capsys):
    code = cmd_check.cmd_check_probe(
        _parse("check", "probe", "-e", "nps-x", "-c", "client-a", "--dry-run", "--json")
    )

    assert code == 0
    assert json.loads(capsys.readouterr().out)["dry_run"] is True
    assert FakeSession.opened == []


def test_probe_without_yes_and_without_a_tty_is_a_usage_error(
    session_env, monkeypatch, capsys
):
    def no_tty(prompt):
        raise EOFError

    monkeypatch.setattr("builtins.input", no_tty)

    code = cmd_check.cmd_check_probe(
        _parse("check", "probe", "-e", "nps-x", "-c", "client-a", "--json")
    )

    assert code == 2
    assert FakeSession.opened == []


def test_probe_declined_confirmation_aborts_cleanly(session_env, monkeypatch, capsys):
    monkeypatch.setattr("builtins.input", lambda: "n")

    code = cmd_check.cmd_check_probe(
        _parse("check", "probe", "-e", "nps-x", "-c", "client-a", "--no-color")
    )

    assert code == 0
    assert "Aborted" in capsys.readouterr().out
    assert FakeSession.opened == []


@pytest.mark.parametrize(
    "argv, fragment",
    [
        (("-e", "ghost", "-c", "client-a"), "Edge 'ghost' not found"),
        (("-e", "nps-x", "-c", "ghost"), "Client 'ghost' not found"),
    ],
)
def test_probe_unknown_names_are_usage_errors(session_env, capsys, argv, fragment):
    code = cmd_check.cmd_check_probe(_parse("check", "probe", *argv, "-y", "--json"))

    assert code == 2
    assert fragment in json.loads(capsys.readouterr().out)["error"]


def test_probe_bad_size_is_a_usage_error(session_env, capsys):
    code = cmd_check.cmd_check_probe(
        _parse(
            "check",
            "probe",
            "-e",
            "nps-x",
            "-c",
            "client-a",
            "--size",
            "huge",
            "-y",
            "--json",
        )
    )

    assert code == 2


def test_json_without_yes_refuses_instead_of_prompting(session_env, capsys):
    code = cmd_check.cmd_check_probe(
        _parse("check", "probe", "-e", "nps-x", "-c", "client-a", "--json")
    )

    out = capsys.readouterr().out
    assert code == 2
    assert json.loads(out)["error"].startswith("--json runs without a prompt")
    assert FakeSession.opened == []


def test_json_mode_emits_one_document_only(session_env, capsys):
    session_env["report"] = _report([Finding("info", "path_clean", "s", "ok")])

    code = cmd_check.cmd_check_probe(
        _parse("check", "probe", "-e", "nps-x", "-c", "client-a", "-y", "--json")
    )

    out = capsys.readouterr().out
    payload = json.loads(out)  # a second document would fail here
    assert code == 0
    assert payload["plan"].startswith("Will start a temporary echo service")


def test_setup_failure_reports_what_cleanup_left_behind(
    session_env, monkeypatch, capsys
):
    from nps_ctl.check.session import SessionError

    class LeakySetup(FakeSession):
        def __enter__(self):
            self.cleanup_problems = ["host mapping x is still on nps-x"]
            raise SessionError("cannot start echo")

    monkeypatch.setattr(cmd_check, "ProbeSession", LeakySetup)

    code = cmd_check.cmd_check_probe(
        _parse("check", "probe", "-e", "nps-x", "-c", "client-a", "-y", "--json")
    )

    payload = json.loads(capsys.readouterr().out)
    assert code == 1
    assert payload["error"] == "cannot start echo"
    assert payload["cleanup_problems"] == ["host mapping x is still on nps-x"]


def test_interrupt_exits_130_and_says_cleanup_succeeded(
    session_env, monkeypatch, capsys
):
    def interrupted(*a, **k):
        raise KeyboardInterrupt

    monkeypatch.setattr(cmd_check, "run_stress", interrupted)

    code = cmd_check.cmd_check_stress(
        _parse("check", "stress", "-e", "nps-x", "-c", "client-a", "-y", "--json")
    )

    payload = json.loads(capsys.readouterr().out)
    assert code == 130
    assert "were removed" in payload["error"]


def test_interrupt_reports_cleanup_problems(session_env, monkeypatch, capsys):
    class Leaky(FakeSession):
        def __init__(self, *a, **k):
            super().__init__(*a, **k)
            self.cleanup_problems = ["host mapping left"]

    def interrupted(*a, **k):
        raise KeyboardInterrupt

    monkeypatch.setattr(cmd_check, "ProbeSession", Leaky)
    monkeypatch.setattr(cmd_check, "run_stress", interrupted)

    code = cmd_check.cmd_check_probe(
        _parse("check", "probe", "-e", "nps-x", "-c", "client-a", "-y", "--json")
    )

    payload = json.loads(capsys.readouterr().out)
    assert code == 130
    assert "cleanup left: host mapping left" in payload["error"]


def test_links_reports_outages_whose_server_is_not_configured(monkeypatch, capsys):
    _patch_cluster(monkeypatch)
    from nps_ctl.check.npc_log import Outage

    orphan = Outage("nps-gone.example:51235", 100.0, 130.0, reconnected=190.0)
    monkeypatch.setattr(
        cmd_check,
        "collect_links",
        lambda *a, **k: ([_link_report()], {}, {"client-a": [orphan]}),
    )

    code = cmd_check.cmd_check_links(_parse("check", "links", "--json"))

    payload = json.loads(capsys.readouterr().out)
    assert code == 1
    assert payload["unattributed_outages"]["client-a"][0]["server"] == (
        "nps-gone.example:51235"
    )
    assert (
        any(f["code"] == "outages_unattributed" for f in payload["findings"])
        or payload["summary"]["warnings"] == 1
    )


def test_stress_passes_the_profile_and_duration_through(session_env, capsys):
    session_env["report"] = _report([Finding("info", "path_clean", "s", "ok")])

    code = cmd_check.cmd_check_stress(
        _parse(
            "check",
            "stress",
            "-e",
            "nps-x",
            "-c",
            "client-a",
            "--profile",
            "soak",
            "--duration",
            "90s",
            "--http-proxy-port",
            "31000",
            "-y",
            "--json",
        )
    )

    assert code == 0
    assert session_env["profile"] == "soak"
    assert session_env["duration"] == 90.0
    assert session_env["steps"] is None
    assert FakeSession.opened == [("nps-x", "client-a", 31000)]


def test_stress_bad_duration_is_a_usage_error(session_env, capsys):
    code = cmd_check.cmd_check_stress(
        _parse(
            "check",
            "stress",
            "-e",
            "nps-x",
            "-c",
            "client-a",
            "--duration",
            "later",
            "-y",
            "--json",
        )
    )

    assert code == 2


def test_stress_table_shows_correlation(session_env, capsys):
    report = _report([Finding("error", "path_errors", "s", "failed")], failed=3)
    report.correlation = Correlation(failures=3, inside=3, share=1.0, chance=0.1)
    session_env["report"] = report

    code = cmd_check.cmd_check_stress(
        _parse("check", "stress", "-e", "nps-x", "-c", "client-a", "-y", "--no-color")
    )

    assert code == 1
    assert "3 of 3 failures fall inside logged link outages" in capsys.readouterr().out
