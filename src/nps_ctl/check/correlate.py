"""Relate failed requests to the link outages seen in the NPC log."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .npc_log import Outage

DEFAULT_PAD = 15.0


@dataclass
class Correlation:
    """How many failures fall inside link outages, and how likely that is by chance.

    Attributes:
        failures: Number of failed requests considered.
        inside: Failures that fall inside an outage window.
        share: ``inside / failures`` (0 when there are no failures).
        chance: Fraction of the run covered by outage windows, i.e. the share
            expected if failures were unrelated to outages.
        by_outage: One entry per outage that overlaps the run.
    """

    failures: int
    inside: int
    share: float
    chance: float
    by_outage: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serialisable mapping."""
        return {
            "failures": self.failures,
            "inside": self.inside,
            "share": round(self.share, 4),
            "chance": round(self.chance, 4),
            "by_outage": self.by_outage,
        }


def _merged_length(windows: list[tuple[float, float]], lo: float, hi: float) -> float:
    clipped = sorted((max(a, lo), min(b, hi)) for a, b in windows if b > lo and a < hi)
    total = 0.0
    current_end = lo
    for start, end in clipped:
        start = max(start, current_end)
        if end > start:
            total += end - start
            current_end = end
    return total


def correlate(
    failure_times: list[float],
    outages: list[Outage],
    run_start: float,
    run_end: float,
    *,
    pad: float = DEFAULT_PAD,
) -> Correlation:
    """Count the failures that fall inside outage windows.

    Args:
        failure_times: Epoch seconds at which requests failed.
        outages: Outages from the NPC log of the client serving the tunnel.
        run_start: Start of the load run, epoch seconds.
        run_end: End of the load run, epoch seconds.
        pad: Seconds added on both sides of every outage to allow clock skew
            between the load generator and the NPC host.

    Returns:
        The correlation. ``chance`` is zero when the run was too short to
        measure.
    """
    windows = [(o.start - pad, o.end(run_end) + pad) for o in outages]
    inside = sum(any(a <= t <= b for a, b in windows) for t in failure_times)
    span = run_end - run_start
    chance = _merged_length(windows, run_start, run_end) / span if span > 0 else 0.0
    by_outage = []
    for outage, (a, b) in zip(outages, windows):
        if b < run_start or a > run_end:
            continue
        by_outage.append(
            {
                "server": outage.server,
                "start": outage.start,
                "end": outage.end(run_end),
                "failures": sum(a <= t <= b for t in failure_times),
            }
        )
    count = len(failure_times)
    return Correlation(
        failures=count,
        inside=inside,
        share=inside / count if count else 0.0,
        chance=chance,
        by_outage=by_outage,
    )
