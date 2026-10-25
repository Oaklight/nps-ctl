"""Named load profiles and the runner that applies them to a session."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from .correlate import Correlation, correlate
from .model import Finding
from .session import LAYER_CLIENT_LOCAL, LAYER_VIA_NPS, ProbeSession
from .verdict import assess_run

KIB = 1024
MIB = 1024 * KIB
DEFAULT_SOAK_SECONDS = 600.0


@dataclass(frozen=True)
class Step:
    """One load run of a profile.

    Attributes:
        name: Label shown in reports.
        spec: Load-spec fields, see :mod:`nps_ctl.check.loadgen`.
    """

    name: str
    spec: dict[str, Any]


def _smoke(duration: float) -> list[Step]:
    return [Step("smoke 256K x4", {"size": 256 * KIB, "count": 30, "concurrency": 4})]


def _ladder(duration: float) -> list[Step]:
    steps = []
    for concurrency in (1, 2, 4, 8, 16):
        for size, label in ((64 * KIB, "64K"), (MIB, "1M")):
            steps.append(
                Step(
                    f"ladder {label} x{concurrency}",
                    {
                        "size": size,
                        "count": max(16, 6 * concurrency),
                        "concurrency": concurrency,
                    },
                )
            )
    return steps


def _slow(duration: float) -> list[Step]:
    return [
        Step(
            "slow 512K, 16K chunks / 20ms x4",
            {
                "mode": "slow",
                "size": 512 * KIB,
                "chunk_kb": 16,
                "gap_ms": 20,
                "count": 24,
                "concurrency": 4,
            },
        ),
        Step(
            "slow 256K, 4K chunks / 10ms x8",
            {
                "mode": "slow",
                "size": 256 * KIB,
                "chunk_kb": 4,
                "gap_ms": 10,
                "count": 16,
                "concurrency": 8,
            },
        ),
    ]


def _churn(duration: float) -> list[Step]:
    return [Step("churn 2K x16", {"size": 2 * KIB, "count": 400, "concurrency": 16})]


def _soak(duration: float) -> list[Step]:
    return [
        Step(
            f"soak 256K x4 for {int(duration)}s",
            {"size": 256 * KIB, "duration": duration, "concurrency": 4},
        )
    ]


PROFILES: dict[str, Callable[[float], list[Step]]] = {
    "smoke": _smoke,
    "ladder": _ladder,
    "slow": _slow,
    "churn": _churn,
    "soak": _soak,
}


@dataclass
class StepReport:
    """Outcome of one :class:`Step` through the tunnel."""

    name: str
    error: str
    result: dict[str, Any] | None

    @property
    def failed(self) -> int:
        """Requests that did not verify."""
        if not self.result:
            return 0
        return sum(n for k, n in self.result["outcomes"].items() if k != "ok")

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serialisable mapping."""
        return {"name": self.name, "error": self.error, "result": self.result}


@dataclass
class StressReport:
    """Everything a stress run produced.

    Attributes:
        profile: Profile name.
        baseline: Client-local results, before the steps.
        steps: One report per step, in order.
        correlation: All tunnel failures versus logged outages.
        findings: Verdict findings.
    """

    profile: str
    baseline: list[dict[str, Any]] = field(default_factory=list)
    steps: list[StepReport] = field(default_factory=list)
    correlation: Correlation | None = None
    findings: list[Finding] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serialisable mapping."""
        return {
            "profile": self.profile,
            "baseline": self.baseline,
            "steps": [step.to_dict() for step in self.steps],
            "correlation": self.correlation.to_dict() if self.correlation else None,
            "findings": [finding.to_dict() for finding in self.findings],
        }


BASELINE_SPEC = {"size": 256 * KIB, "count": 20, "concurrency": 4}


def run_stress(
    session: ProbeSession,
    profile: str,
    *,
    duration: float = DEFAULT_SOAK_SECONDS,
    on_step: Callable[[str], None] | None = None,
    steps: list[Step] | None = None,
) -> StressReport:
    """Run a profile's steps through an open session and judge the outcome.

    The client-local baseline runs first. If it fails, the tunnel steps are
    skipped: the harness itself is broken and tunnel numbers would mislead.

    Args:
        session: An open :class:`ProbeSession`.
        profile: Key of :data:`PROFILES`, or a free label when *steps* is given.
        duration: Soak length in seconds; ignored by other profiles.
        on_step: Called with each step's name before it runs.
        steps: Explicit steps replacing the profile's, used by ``check probe``.

    Returns:
        The report, with findings from :func:`assess_run`.

    Raises:
        KeyError: If *profile* is unknown.
    """
    steps = steps if steps is not None else PROFILES[profile](duration)
    subject = f"{session.edge} -> {session.client}"
    report = StressReport(profile=profile)

    if on_step:
        on_step("baseline (client-local, no tunnel)")
    baseline = session.run_load(LAYER_CLIENT_LOCAL, BASELINE_SPEC)
    if baseline.result:
        report.baseline.append(baseline.result)
    if baseline.error or not baseline.result:
        report.findings.append(
            Finding("error", "baseline_failed", subject, baseline.error or "no result")
        )
        return report
    if not _clean([baseline.result]):
        report.findings = assess_run(subject, report.baseline, [])
        return report

    through: list[dict[str, Any]] = []
    failure_times: list[float] = []
    for step in steps:
        if on_step:
            on_step(step.name)
        run = session.run_load(LAYER_VIA_NPS, step.spec)
        report.steps.append(StepReport(step.name, run.error, run.result))
        if run.result:
            through.append(run.result)
            failure_times.extend(run.result.get("failure_times", []))
        elif run.error:
            report.findings.append(
                Finding("error", "step_failed", subject, f"{step.name}: {run.error}")
            )

    if failure_times and through:
        # Failure times come from the edge host's clock, so the run window must too.
        run_start = min(r["started"] for r in through)
        run_end = max(r["finished"] for r in through)
        try:
            outages = session.outages(since=max(600.0, time.time() - run_start + 600))
            report.correlation = correlate(failure_times, outages, run_start, run_end)
        except Exception:  # noqa: BLE001 - correlation is a bonus; never lose the run
            report.correlation = None
    report.findings += assess_run(subject, report.baseline, through, report.correlation)
    return report


def _clean(results: list[dict[str, Any]]) -> bool:
    return all(set(r["outcomes"]) <= {"ok"} for r in results)
