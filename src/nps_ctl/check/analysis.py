"""Summarise outages per bridge link and turn them into findings."""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass, field
from statistics import median
from typing import Any

from .model import Finding
from .npc_log import Outage
from .units import format_duration

FLAP_MIN_OUTAGES = 3
PERIOD_MIN_GAPS = 4
PERIOD_TOLERANCE = 0.15
PERIOD_MIN_SHARE = 0.6


@dataclass
class LinkSummary:
    """Outage statistics for one bridge link over an examined window.

    Attributes:
        window: Seconds of log examined.
        outages: Number of outages that started in the window.
        downtime: Seconds the link was down, summed over outages.
        median_duration: Median outage length in seconds.
        max_duration: Longest outage in seconds.
        median_period: Median gap between outage starts, when there are at
            least two outages.
        periodic: True when outages recur at a near-constant interval.
        failed_attempts: Reconnect attempts that failed.
        reasons: Failure reason -> number of outages that reported it.
        still_open: True when the last outage had not ended at the end of the log.
    """

    window: float
    outages: int = 0
    downtime: float = 0.0
    median_duration: float | None = None
    max_duration: float | None = None
    median_period: float | None = None
    periodic: bool = False
    failed_attempts: int = 0
    reasons: dict[str, int] = field(default_factory=dict)
    still_open: bool = False

    @property
    def downtime_share(self) -> float:
        """Fraction of the window the link was down."""
        return self.downtime / self.window if self.window else 0.0

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serialisable mapping."""
        data = asdict(self)
        data["downtime_share"] = round(self.downtime_share, 4)
        return data


def detect_period(starts: list[float]) -> tuple[float | None, bool]:
    """Find a recurring interval between outage start times.

    Args:
        starts: Outage start times in ascending order.

    Returns:
        ``(median_gap, periodic)``. ``periodic`` is true when there are at
        least :data:`PERIOD_MIN_GAPS` gaps and at least
        :data:`PERIOD_MIN_SHARE` of them lie within
        :data:`PERIOD_TOLERANCE` of the median gap.
    """
    gaps = [later - earlier for earlier, later in zip(starts, starts[1:])]
    if not gaps:
        return None, False
    mid = median(gaps)
    if len(gaps) < PERIOD_MIN_GAPS or mid <= 0:
        return mid, False
    close = sum(1 for gap in gaps if abs(gap - mid) <= mid * PERIOD_TOLERANCE)
    return mid, close / len(gaps) >= PERIOD_MIN_SHARE


def summarize(outages: list[Outage], now: float, window: float) -> LinkSummary:
    """Summarise the outages of a single link.

    Args:
        outages: Outages of one link, in time order.
        now: End of the examined window, epoch seconds.
        window: Length of the examined window in seconds.

    Returns:
        The statistics, with every field zero or ``None`` when there were no
        outages.
    """
    summary = LinkSummary(window=window)
    if not outages:
        return summary
    durations = [outage.duration(now) for outage in outages]
    reasons: Counter[str] = Counter()
    for outage in outages:
        reasons.update(outage.reasons)
    summary.outages = len(outages)
    summary.downtime = sum(durations)
    summary.median_duration = median(durations)
    summary.max_duration = max(durations)
    summary.median_period, summary.periodic = detect_period(
        [outage.start for outage in outages]
    )
    summary.failed_attempts = sum(outage.failed_attempts for outage in outages)
    summary.reasons = dict(reasons)
    summary.still_open = outages[-1].reconnected is None
    return summary


def assess(summary: LinkSummary, established: bool, subject: str) -> list[Finding]:
    """Turn a link's state and outage statistics into findings.

    Args:
        summary: Statistics from :func:`summarize`.
        established: Whether a bridge socket to the server exists right now.
        subject: Label used in the findings, e.g. ``cloud.usa2 -> nps-europe``.

    Returns:
        Findings from most to least severe; a single ``link_stable`` info
        finding when nothing is wrong.
    """
    findings: list[Finding] = []
    if not established:
        findings.append(
            Finding("error", "link_down", subject, "no established bridge socket")
        )
    if summary.still_open and established:
        findings.append(
            Finding(
                "warn",
                "outage_open",
                subject,
                "the last outage has no reconnect in the log although a socket exists",
            )
        )
    if summary.outages >= FLAP_MIN_OUTAGES:
        reasons = ", ".join(f"{k} x{v}" for k, v in sorted(summary.reasons.items()))
        findings.append(
            Finding(
                "warn",
                "link_flapping",
                subject,
                f"{summary.outages} outages in {format_duration(summary.window)}, "
                f"median {format_duration(summary.median_duration)}, "
                f"max {format_duration(summary.max_duration)}, "
                f"down {summary.downtime_share:.1%} of the time"
                + (f"; reasons: {reasons}" if reasons else ""),
            )
        )
    if summary.periodic:
        findings.append(
            Finding(
                "warn",
                "link_periodic",
                subject,
                "outages recur about every "
                f"{format_duration(summary.median_period)}; look for a scheduled "
                "job, a rate limit or a path change with that period",
            )
        )
    if not findings:
        findings.append(
            Finding(
                "info",
                "link_stable",
                subject,
                f"{summary.outages} outage(s) in {format_duration(summary.window)}",
            )
        )
    return findings
