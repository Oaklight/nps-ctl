"""Find and remove host mappings an interrupted check run left behind.

A run that is killed outright (SIGKILL, a closed terminal, a timed-out CI job)
cannot clean up. Its mapping is recognisable by the remark every session writes
and by the ``.nps-ctl-check.invalid`` domain, and it matters beyond a wasted
row: ``host_identity`` is ``(Host, Location)``, so a mapping present on one edge
and nowhere else reads as drift in ``edge status`` for as long as it exists.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from .. import host
from ..types import HostInfo
from .session import DOMAIN_SUFFIX, REMARK, NpsMapping

SEARCH = "nps-ctl-check"


@dataclass(frozen=True)
class Leftover:
    """One host mapping created by a check run that never removed it.

    Attributes:
        edge: Edge the mapping is on.
        host_id: NPS host id on that edge.
        domain: The throwaway domain.
        target: Target address, empty when NPS did not report one.
    """

    edge: str
    host_id: int
    domain: str
    target: str

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serialisable mapping."""
        return asdict(self)


def _target_of(entry: HostInfo) -> str:
    target = entry.get("Target") or {}
    return str(target.get("TargetStr", "")) if isinstance(target, dict) else ""


def find_leftovers(cluster: Any, edge_names: list[str]) -> list[Leftover]:
    """List host mappings left by a check run.

    Args:
        cluster: Cluster exposing ``get_client(edge)``.
        edge_names: Edges to inspect.

    Returns:
        One entry per matching mapping, in edge order. Only rows carrying both
        this module's remark and the throwaway domain suffix are returned, so a
        similarly named host someone else created is never touched.
    """
    found: list[Leftover] = []
    for edge in edge_names:
        nps = cluster.get_client(edge)
        if nps is None:
            continue
        for entry in host.list_hosts(nps, search=SEARCH):
            domain = str(entry.get("Host", ""))
            if entry.get("Remark") != REMARK or not domain.endswith(DOMAIN_SUFFIX):
                continue
            found.append(
                Leftover(
                    edge=edge,
                    host_id=int(entry["Id"]),
                    domain=domain,
                    target=_target_of(entry),
                )
            )
    return found


def remove_leftovers(
    cluster: Any, leftovers: list[Leftover]
) -> list[tuple[Leftover, str]]:
    """Delete the given mappings through the verified path.

    Args:
        cluster: Cluster exposing ``get_client(edge)``.
        leftovers: Entries from :func:`find_leftovers`.

    Returns:
        ``(leftover, error)`` for each mapping that could not be removed; empty
        when every delete was confirmed.
    """
    mapping = NpsMapping(cluster)
    failures: list[tuple[Leftover, str]] = []
    for leftover in leftovers:
        try:
            mapping.remove(leftover.edge, leftover.host_id, leftover.domain)
        except Exception as exc:  # noqa: BLE001 - collect, so one failure does not stop the rest
            failures.append((leftover, str(exc)))
    return failures
