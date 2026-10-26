"""CLI commands: check links / probe / stress for NPS/NPC deployments."""

import argparse
import sys
import time
from typing import Any

from ..check.leftovers import find_leftovers, remove_leftovers
from ..check.links import LinkReport, collect_links
from ..check.model import Finding, exit_code
from ..check.session import ProbeSession, SessionError
from ..check.stress import (
    Step,
    StressReport,
    run_stress,
)
from ..check.units import format_duration, parse_duration, parse_size
from ..cluster import NPSCluster
from .helpers import (
    console,
    create_table,
    print_error,
    print_info,
    print_json,
    status_spinner,
)

_LEVEL_STYLE = {"error": "red", "warn": "yellow", "info": "green"}


def _fail(message: str, json_mode: bool, code: int = 1) -> int:
    if json_mode:
        print_json({"error": message})
    else:
        print_error(message)
    return code


def _load_cluster(args: argparse.Namespace, json_mode: bool) -> NPSCluster | int:
    try:
        return NPSCluster(args.config)
    except FileNotFoundError as e:
        return _fail(str(e), json_mode)


def _verdict(report: LinkReport) -> str:
    worst = max(report.findings, key=lambda f: ("info", "warn", "error").index(f.level))
    style = _LEVEL_STYLE[worst.level]
    return f"[{style}]{worst.code}[/{style}]"


def _links_payload(
    reports: list[LinkReport],
    errors: dict[str, str],
    findings: list[Finding],
    unattributed: dict[str, list[Any]],
    now: float,
) -> dict[str, Any]:
    return {
        "links": [report.to_dict() for report in reports],
        "errors": errors,
        "findings": [finding.to_dict() for finding in findings],
        "unattributed_outages": {
            client: [
                {
                    "server": outage.server,
                    "start": outage.start,
                    "end": outage.end(now),
                }
                for outage in outages
            ]
            for client, outages in unattributed.items()
        },
        "summary": {
            "links": len(reports),
            "unreachable_clients": len(errors),
            "errors": sum(f.level == "error" for f in findings),
            "warnings": sum(f.level == "warn" for f in findings),
        },
    }


def cmd_check_links(args: argparse.Namespace) -> int:
    """Report bridge-link health for NPC clients without generating traffic."""
    json_mode = getattr(args, "json", False)
    try:
        since = parse_duration(args.since)
    except ValueError as e:
        return _fail(str(e), json_mode, code=2)

    cluster = _load_cluster(args, json_mode)
    if isinstance(cluster, int):
        return cluster

    names = cluster.npc_client_names
    if args.client:
        if args.client not in names:
            return _fail(f"Client '{args.client}' not found in clients.toml", json_mode)
        names = [args.client]
    if not names:
        return _fail("No NPC clients configured in clients.toml", json_mode)

    with status_spinner(
        f"Reading link state from {len(names)} client(s)...", json_mode=json_mode
    ):
        reports, errors, unattributed = collect_links(
            cluster,
            names,
            since=since,
            log_path=args.log_path,
            tail_bytes=args.tail_bytes,
        )

    findings = [finding for report in reports for finding in report.findings]
    findings += [
        Finding("error", "collect_failed", name, reason)
        for name, reason in sorted(errors.items())
    ]
    now = time.time()
    for client, outages in sorted(unattributed.items()):
        servers = sorted({outage.server or "(unnamed)" for outage in outages})
        findings.append(
            Finding(
                "warn",
                "outages_unattributed",
                client,
                f"{len(outages)} outage(s) name servers that no configured bridge "
                f"matches: {', '.join(servers)}; the client's edges or bridge "
                "port may have drifted from clients.toml",
            )
        )

    if json_mode:
        print_json(_links_payload(reports, errors, findings, unattributed, now))
        return exit_code(findings, args.fail_on)

    table = create_table(title=f"NPC bridge links (last {format_duration(since)})")
    table.add_column("Client", style="bold")
    table.add_column("Edge")
    table.add_column("Link")
    table.add_column("Outages", justify="right")
    table.add_column("Median", justify="right")
    table.add_column("Max", justify="right")
    table.add_column("Down", justify="right")
    table.add_column("Period", justify="right")
    table.add_column("Verdict")
    for report in reports:
        s = report.summary
        table.add_row(
            report.client,
            report.edge or report.server,
            "[green]up[/green]" if report.established else "[red]down[/red]",
            str(s.outages),
            format_duration(s.median_duration),
            format_duration(s.max_duration),
            f"{s.downtime_share:.1%}",
            format_duration(s.median_period) + (" *" if s.periodic else ""),
            _verdict(report),
        )
    console.print(table, crop=False)

    for finding in findings:
        if finding.level == "info":
            continue
        style = _LEVEL_STYLE[finding.level]
        console.print(
            f"[{style}]{finding.level}[/{style}] {finding.subject}: "
            f"[bold]{finding.code}[/bold] - {finding.message}"
        )
    if not any(f.level != "info" for f in findings):
        console.print("[green]All checked links are stable.[/green]")
    return exit_code(findings, args.fail_on)


def _step_table(report: StressReport) -> None:
    table = create_table(title=f"{report.profile}: requests through the tunnel")
    table.add_column("Step", style="bold")
    table.add_column("Requests", justify="right")
    table.add_column("Failed", justify="right")
    table.add_column("p50", justify="right")
    table.add_column("p95", justify="right")
    table.add_column("Max", justify="right")
    table.add_column("Outcomes")
    for step in report.steps:
        result = step.result
        if result is None:
            table.add_row(
                step.name, "-", "-", "-", "-", "-", f"[red]{step.error}[/red]"
            )
            continue
        failed = step.failed
        outcomes = ", ".join(f"{k} {v}" for k, v in sorted(result["outcomes"].items()))
        table.add_row(
            step.name,
            str(result["total"]),
            f"[red]{failed}[/red]" if failed else "0",
            _ms(result["p50_ms"]),
            _ms(result["p95_ms"]),
            _ms(result["max_ms"]),
            outcomes,
        )
    console.print(table, crop=False)


def _ms(value: float | None) -> str:
    return "-" if value is None else f"{value:.0f}ms"


def _print_findings(findings: list[Finding]) -> None:
    for finding in findings:
        style = _LEVEL_STYLE[finding.level]
        console.print(
            f"[{style}]{finding.level}[/{style}] {finding.subject}: "
            f"[bold]{finding.code}[/bold] - {finding.message}"
        )


def _cleanup_failure(message: str, session: Any, json_mode: bool) -> int:
    """Report a session that failed while cleaning up after itself."""
    problems = list(getattr(session, "cleanup_problems", []))
    if json_mode:
        print_json({"error": message, "cleanup_problems": problems})
    else:
        print_error(message)
        for problem in problems:
            print_error(problem)
    return 1


def _run_session_command(
    args: argparse.Namespace, *, profile: str, steps: list[Step] | None, duration: float
) -> int:
    json_mode = getattr(args, "json", False)
    cluster = _load_cluster(args, json_mode)
    if isinstance(cluster, int):
        return cluster

    if args.edge not in cluster.edge_names:
        return _fail(f"Edge '{args.edge}' not found", json_mode, code=2)
    if args.client not in cluster.npc_client_names:
        return _fail(
            f"Client '{args.client}' not found in clients.toml", json_mode, code=2
        )

    plan = (
        f"Will start a temporary echo service on {args.client}, add a temporary host "
        f"mapping on edge {args.edge} to it, send {profile} load through NPS, and "
        "remove both afterwards."
    )
    if getattr(args, "dry_run", False):
        if json_mode:
            print_json({"dry_run": True, "plan": plan, "profile": profile})
        else:
            console.print(plan)
        return 0
    if json_mode:
        # A prompt would be written to stdout and stop the stream being JSON.
        if not args.yes:
            return _fail(
                "--json runs without a prompt; pass -y to confirm "
                "(or --dry-run to see the plan)",
                json_mode,
                code=2,
            )
    else:
        console.print(plan)
        if not args.yes:
            # The prompt goes to stderr so stdout stays a clean result stream.
            sys.stderr.write("Continue? [y/N] ")
            sys.stderr.flush()
            try:
                response = input()
            except EOFError:
                return _fail(
                    "No TTY for the confirmation prompt; pass -y to continue "
                    "without asking",
                    json_mode,
                    code=2,
                )
            if response.strip().lower() != "y":
                console.print("Aborted.")
                return 0

    def progress(name: str) -> None:
        if not json_mode:
            print_info(f"running {name}")

    try:
        session = ProbeSession(
            cluster, args.edge, args.client, http_proxy_port=args.http_proxy_port
        )
    except SessionError as exc:
        return _fail(str(exc), json_mode)

    try:
        with session:
            report = run_stress(
                session, profile, duration=duration, on_step=progress, steps=steps
            )
    except KeyboardInterrupt:
        return _fail(
            "interrupted; the temporary host mapping and echo service were removed"
            if not session.cleanup_problems
            else "interrupted; cleanup left: " + "; ".join(session.cleanup_problems),
            json_mode,
            code=130,
        )
    except SessionError as exc:
        return _cleanup_failure(str(exc), session, json_mode)

    problems = session.cleanup_problems
    findings = list(report.findings)
    findings += [Finding("error", "cleanup_failed", args.edge, p) for p in problems]

    if json_mode:
        payload = report.to_dict()
        payload["plan"] = plan
        payload["findings"] = [f.to_dict() for f in findings]
        payload["cleanup_problems"] = problems
        print_json(payload)
    else:
        if report.steps:
            _step_table(report)
        if report.correlation and report.correlation.failures:
            c = report.correlation
            console.print(
                f"{c.inside} of {c.failures} failures fall inside logged link outages "
                f"(outage windows cover {c.chance:.0%} of the run)"
            )
        _print_findings(findings)
    return exit_code(findings, args.fail_on)


def cmd_check_probe(args: argparse.Namespace) -> int:
    """Send one self-verifying load through an edge's tunnel and judge the result."""
    json_mode = getattr(args, "json", False)
    try:
        size = parse_size(args.size)
    except ValueError as e:
        return _fail(str(e), json_mode, code=2)
    spec: dict[str, Any] = {
        "size": size,
        "count": args.count,
        "concurrency": args.concurrency,
        "mode": args.mode,
        "chunk_kb": args.chunk_kb,
        "gap_ms": args.gap_ms,
        "timeout": args.timeout,
    }
    step = Step(f"probe {args.size} x{args.concurrency}", spec)
    return _run_session_command(args, profile="probe", steps=[step], duration=0)


def cmd_check_stress(args: argparse.Namespace) -> int:
    """Run a named stress profile through an edge's tunnel."""
    json_mode = getattr(args, "json", False)
    try:
        duration = parse_duration(args.duration)
    except ValueError as e:
        return _fail(str(e), json_mode, code=2)
    return _run_session_command(
        args, profile=args.profile, steps=None, duration=duration
    )


def cmd_check_leftovers(args: argparse.Namespace) -> int:
    """List, or delete, host mappings left behind by an interrupted run."""
    json_mode = getattr(args, "json", False)
    cluster = _load_cluster(args, json_mode)
    if isinstance(cluster, int):
        return cluster

    edge = getattr(args, "edge", None)
    every = getattr(args, "all", False)
    if edge and every:
        return _fail("Use either -e/--edge or -a/--all, not both", json_mode, code=2)
    if edge and edge not in cluster.edge_names:
        return _fail(f"Edge '{edge}' not found", json_mode, code=2)
    if args.delete and not (edge or every):
        return _fail(
            "--delete needs an explicit target: -e/--edge for one edge or -a/--all",
            json_mode,
            code=2,
        )
    targets = [edge] if edge else list(cluster.edge_names)

    leftovers = find_leftovers(cluster, targets)
    removed: list[Any] = []
    failures: list[tuple[Any, str]] = []
    if args.delete and leftovers:
        if json_mode:
            if not args.yes:
                return _fail(
                    "--json runs without a prompt; pass -y to delete",
                    json_mode,
                    code=2,
                )
        elif not args.yes:
            sys.stderr.write(f"Delete {len(leftovers)} leftover mapping(s)? [y/N] ")
            sys.stderr.flush()
            try:
                response = input()
            except EOFError:
                return _fail(
                    "No TTY for the confirmation prompt; pass -y to delete",
                    json_mode,
                    code=2,
                )
            if response.strip().lower() != "y":
                console.print("Aborted.")
                return 0
        failures = remove_leftovers(cluster, leftovers)
        removed = [
            item for item in leftovers if all(item is not f[0] for f in failures)
        ]

    findings = (
        [
            Finding(
                "warn",
                "leftover_mapping",
                f"{item.edge}:{item.domain}",
                item.target or "-",
            )
            for item in leftovers
        ]
        if not args.delete
        else []
    )
    findings += [
        Finding("error", "leftover_delete_failed", f"{item.edge}:{item.domain}", error)
        for item, error in failures
    ]

    if json_mode:
        print_json(
            {
                "leftovers": [item.to_dict() for item in leftovers],
                "removed": [item.to_dict() for item in removed],
                "failures": [
                    {"leftover": item.to_dict(), "error": error}
                    for item, error in failures
                ],
                "summary": {
                    "found": len(leftovers),
                    "removed": len(removed),
                    "failed": len(failures),
                },
            }
        )
    else:
        if not leftovers:
            console.print("[green]No leftover mappings.[/green]")
        else:
            table = create_table(title="Host mappings left by a check run")
            table.add_column("Edge", style="bold")
            table.add_column("ID", justify="right")
            table.add_column("Domain")
            table.add_column("Target")
            for item in leftovers:
                table.add_row(
                    item.edge, str(item.host_id), item.domain, item.target or "-"
                )
            console.print(table, crop=False)
            if args.delete:
                console.print(
                    f"[green]{len(removed)} removed[/green]"
                    + (f", [red]{len(failures)} failed[/red]" if failures else "")
                )
            else:
                console.print(
                    f"[yellow]{len(leftovers)} leftover(s).[/yellow] Remove them with "
                    "`nps-ctl check leftovers --delete -a -y`."
                )
        for finding in findings:
            style = _LEVEL_STYLE[finding.level]
            console.print(
                f"[{style}]{finding.level}[/{style}] {finding.subject}: "
                f"[bold]{finding.code}[/bold] - {finding.message}"
            )

    if failures:
        return 1
    return 0 if not leftovers or args.delete else 1
