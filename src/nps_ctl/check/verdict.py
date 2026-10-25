"""Turn load-run results into findings."""

from __future__ import annotations

from typing import Any

from .correlate import Correlation
from .model import Finding

DAMAGED = ("corrupt", "truncated", "extended")
MIN_FAILURES_FOR_VERDICT = 3
OUTAGE_SHARE_THRESHOLD = 0.8


def _totals(results: list[dict[str, Any]]) -> tuple[int, dict[str, int], list[str]]:
    total = 0
    outcomes: dict[str, int] = {}
    examples: list[str] = []
    for result in results:
        total += result.get("total", 0)
        for name, count in result.get("outcomes", {}).items():
            outcomes[name] = outcomes.get(name, 0) + count
        for failure in result.get("failures", [])[:2]:
            examples.append(f"{failure['outcome']}: {failure['detail']}")
    return total, outcomes, examples


def _describe(outcomes: dict[str, int]) -> str:
    return ", ".join(f"{count} {name}" for name, count in sorted(outcomes.items()))


def assess_run(
    subject: str,
    baseline: list[dict[str, Any]],
    through_tunnel: list[dict[str, Any]],
    correlation: Correlation | None = None,
) -> list[Finding]:
    """Judge a probe or stress run.

    Args:
        subject: Label used in findings, e.g. ``nps-europe -> cloud.usa2``.
        baseline: Load results for the client-local layer (no tunnel).
        through_tunnel: Load results for the layer that crosses edge, NPS and NPC.
        correlation: Failures versus logged outages, if it could be computed.

    Returns:
        Findings. A failing baseline makes the run inconclusive and is the
        only finding reported besides the baseline itself.
    """
    base_total, base_outcomes, base_examples = _totals(baseline)
    base_bad = {k: v for k, v in base_outcomes.items() if k != "ok"}
    if base_bad:
        return [
            Finding(
                "error",
                "baseline_failed",
                subject,
                f"the client-local echo failed ({_describe(base_bad)}; "
                f"{'; '.join(base_examples[:2])}), so results through the tunnel "
                "are inconclusive",
            )
        ]

    total, outcomes, examples = _totals(through_tunnel)
    bad = {k: v for k, v in outcomes.items() if k != "ok"}
    if total == 0:
        return [Finding("error", "no_requests", subject, "no request completed")]
    if not bad:
        return [
            Finding(
                "info",
                "path_clean",
                subject,
                f"{total} requests through the tunnel, every body verified",
            )
        ]

    failed = sum(bad.values())
    damaged = sum(bad.get(name, 0) for name in DAMAGED)
    code = "path_corruption" if damaged else "path_errors"
    findings = [
        Finding(
            "error",
            code,
            subject,
            f"{failed} of {total} requests failed through the tunnel "
            f"({_describe(bad)}) while the client-local echo was clean"
            + (f"; e.g. {examples[0]}" if examples else ""),
        )
    ]
    if correlation is not None and correlation.failures >= MIN_FAILURES_FOR_VERDICT:
        pct = f"{correlation.share:.0%}"
        chance = f"{correlation.chance:.0%}"
        if correlation.share >= OUTAGE_SHARE_THRESHOLD:
            findings.append(
                Finding(
                    "warn",
                    "failures_in_outage_window",
                    subject,
                    f"{correlation.inside} of {correlation.failures} failures ({pct}) "
                    f"fall inside logged link outages that cover only {chance} of "
                    "the run",
                )
            )
        elif correlation.inside == 0:
            findings.append(
                Finding(
                    "info",
                    "failures_outside_outages",
                    subject,
                    "no logged link outage overlaps the failures",
                )
            )
        else:
            findings.append(
                Finding(
                    "info",
                    "failures_partly_in_outages",
                    subject,
                    f"{correlation.inside} of {correlation.failures} failures ({pct}) "
                    f"fall inside logged outages (chance level {chance})",
                )
            )
    return findings
