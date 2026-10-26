"""Shared result types for the check harness."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

LEVELS = ("info", "warn", "error")


@dataclass(frozen=True)
class Finding:
    """One observation about a link, a probe or a stress run.

    Attributes:
        level: ``info``, ``warn`` or ``error``.
        code: Stable machine-readable identifier, e.g. ``link_flapping``.
        subject: What the finding is about, e.g. ``cloud.usa2 -> nps-europe``.
        message: Human-readable explanation with the measured numbers.
    """

    level: str
    code: str
    subject: str
    message: str

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serialisable mapping."""
        return asdict(self)


def worst_level(findings: list[Finding]) -> str:
    """Return the most severe level among *findings* (``info`` if none)."""
    worst = 0
    for finding in findings:
        worst = max(worst, LEVELS.index(finding.level))
    return LEVELS[worst]


def exit_code(findings: list[Finding], fail_on: str) -> int:
    """Map findings to a process exit code.

    Args:
        findings: All findings of a run.
        fail_on: Lowest level that counts as a failure (``warn`` or ``error``).

    Returns:
        ``1`` when a finding at or above *fail_on* exists, otherwise ``0``.
    """
    threshold = LEVELS.index(fail_on)
    return int(any(LEVELS.index(f.level) >= threshold for f in findings))
