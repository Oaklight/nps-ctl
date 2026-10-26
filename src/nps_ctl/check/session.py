"""An ephemeral probe session: echo service, host mapping and load runs.

A session starts a hash-echo service on an NPC client host, maps a throwaway
domain on one NPS edge to it, and runs the load generator from two places:
on the client host straight at the echo (the baseline, no tunnel) and on the
edge host through NPS's HTTP proxy (the path under test). Everything it
creates is removed again, including after a failure part-way through setup.
"""

from __future__ import annotations

import json
import re
import secrets
import shlex
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from .. import client_mgmt, host
from ..deploy import DeployResult, ssh_execute
from ..types import HostInfo
from . import echo_server, loadgen
from .links import SshRunner, collect_links
from .npc_log import Outage

REMARK = "nps-ctl check (ephemeral)"
DOMAIN_SUFFIX = ".nps-ctl-check.invalid"
DEFAULT_HTTP_PROXY_PORT = 30080
ECHO_TTL_SECONDS = 3600
LAYER_CLIENT_LOCAL = "client_local"
LAYER_VIA_NPS = "via_nps"

_DIR = re.compile(r"^/tmp/nps-ctl-check\.[A-Za-z0-9]+$")
_PID = re.compile(r"^\d+$")


class SessionError(RuntimeError):
    """Raised when a session cannot be set up or a layer cannot be run."""


class MappingApi(Protocol):
    """Creates and removes the throwaway host mapping on an NPS edge."""

    def add(self, edge: str, client_remark: str, domain: str, target: str) -> int:
        """Create the mapping and return its host id."""

    def remove(self, edge: str, host_id: int, domain: str) -> None:
        """Delete the mapping with *host_id*."""

    def remove_unclaimed(self, edge: str, domain: str) -> int:
        """Delete any mapping for *domain* this session created, without an id.

        Used when the create call raised after the edge had already accepted
        it, so no id was ever returned.

        Returns:
            How many rows were removed.
        """


class NpsMapping:
    """:class:`MappingApi` backed by the NPS HTTP API of a real cluster."""

    def __init__(self, cluster: Any):
        self.cluster = cluster

    def _nps(self, edge: str) -> Any:
        nps = self.cluster.get_client(edge)
        if nps is None:
            raise SessionError(f"edge '{edge}' has no API client")
        return nps

    def add(self, edge: str, client_remark: str, domain: str, target: str) -> int:
        nps = self._nps(edge)
        clients = client_mgmt.list_clients(nps, search=client_remark)
        matching = [c for c in clients if c.get("Remark") == client_remark]
        if not matching:
            raise SessionError(f"client '{client_remark}' not found on {edge}")
        if not host.add_host(
            nps,
            client_id=matching[0]["Id"],
            host=domain,
            target=target,
            remark=REMARK,
        ):
            raise SessionError(f"{edge} refused to add the host mapping")
        for entry in host.list_hosts(nps, search=domain):
            if entry.get("Host") == domain:
                return int(entry["Id"])
        raise SessionError(f"host mapping {domain} not found on {edge} after adding it")

    def _ours(self, nps: Any, domain: str) -> list[HostInfo]:
        """Return the host rows for *domain* that carry this session's remark."""
        return [
            entry
            for entry in host.list_hosts(nps, search=domain)
            if entry.get("Host") == domain and entry.get("Remark") == REMARK
        ]

    def _delete(self, nps: Any, edge: str, host_id: int, domain: str) -> None:
        """Delete one row and confirm it is gone.

        Raises:
            SessionError: If the row is not this session's mapping, or if it
                is still listed after the delete.
        """
        entry = next(
            (row for row in self._ours(nps, domain) if row.get("Id") == host_id),
            None,
        )
        if entry is None:
            return
        if not host.del_host(nps, host_id):
            raise SessionError(f"{edge} refused to delete host mapping {host_id}")
        if any(row.get("Id") == host_id for row in self._ours(nps, domain)):
            raise SessionError(f"{edge} still lists host {host_id} after deleting it")

    def remove(self, edge: str, host_id: int, domain: str) -> None:
        """Delete the session's mapping and confirm it is gone.

        Entry lookup goes through the host list rather than ``get_host``,
        which answers for neither API flavour reliably.

        Raises:
            SessionError: If the entry is not this session's mapping, or if it
                is still listed after the delete.
        """
        nps = self._nps(edge)
        known = next(
            (row for row in self._ours(nps, domain) if row.get("Id") == host_id),
            None,
        )
        if known is None:
            if any(
                row.get("Host") == domain for row in host.list_hosts(nps, search=domain)
            ):
                raise SessionError(
                    f"refusing to delete host {host_id} on {edge}: it is not the "
                    "mapping this session created"
                )
            return
        self._delete(nps, edge, host_id, domain)

    def remove_unclaimed(self, edge: str, domain: str) -> int:
        """Delete every row for *domain* that this session created.

        The create call can be accepted by the edge and then fail to show up in
        the follow-up listing, so no id is returned. The domain carries a
        random token and the remark is this session's own, so a row matching
        both is this session's mapping.

        Raises:
            SessionError: If a row survives the delete.
        """
        nps = self._nps(edge)
        removed = 0
        for entry in self._ours(nps, domain):
            host_id = int(entry["Id"])
            self._delete(nps, edge, host_id, domain)
            removed += 1
        return removed


@dataclass
class LayerRun:
    """Result of running the load generator in one place.

    Attributes:
        layer: ``client_local`` or ``via_nps``.
        where: SSH host the generator ran on.
        result: Parsed generator output, ``None`` when it could not run.
        error: Why it could not run, empty on success.
    """

    layer: str
    where: str
    result: dict[str, Any] | None
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serialisable mapping."""
        return {
            "layer": self.layer,
            "where": self.where,
            "result": self.result,
            "error": self.error,
        }


def _source(module: Any) -> str:
    text = Path(module.__file__).read_text()
    if "NPS_CTL_END" in text:
        raise SessionError(f"{module.__name__} contains the heredoc delimiter")
    return text


def echo_start_script(ttl: int = ECHO_TTL_SECONDS) -> str:
    """Return the shell script that starts the echo service in the background."""
    return f"""set -e
command -v python3 >/dev/null || {{ echo "ERROR no python3"; exit 3; }}
D=$(mktemp -d /tmp/nps-ctl-check.XXXXXX)
cat > "$D/echo.py" <<'NPS_CTL_END'
{_source(echo_server)}
NPS_CTL_END
setsid nohup python3 "$D/echo.py" --bind 127.0.0.1 --port 0 --port-file "$D/port" --ttl {int(ttl)} >"$D/log" 2>&1 </dev/null &
echo $! > "$D/pid"
for i in $(seq 1 50); do [ -s "$D/port" ] && break; sleep 0.1; done
echo "DIR $D"
echo "PORT $(cat "$D/port" 2>/dev/null)"
echo "PID $(cat "$D/pid")"
"""


def echo_stop_script(directory: str, pid: str) -> str:
    """Return the shell script that stops the echo service and removes its files.

    Raises:
        ValueError: If *directory* or *pid* is not one this module would create.
    """
    if not _DIR.match(directory) or not _PID.match(pid):
        raise ValueError(f"unexpected echo handle {directory!r} / {pid!r}")
    return f"kill {pid} 2>/dev/null; rm -rf {shlex.quote(directory)}; echo stopped\n"


def load_script(spec: dict[str, Any]) -> str:
    """Return the shell script that runs the load generator with *spec*."""
    return (
        f"python3 - {shlex.quote(json.dumps(spec))} <<'NPS_CTL_END'\n"
        f"{_source(loadgen)}\nNPS_CTL_END\n"
    )


def parse_handle(stdout: str) -> tuple[str, int, str]:
    """Parse ``DIR``/``PORT``/``PID`` lines of :func:`echo_start_script`.

    Raises:
        SessionError: If the echo service did not report a port.
    """
    values = dict(
        line.split(" ", 1) for line in stdout.splitlines() if line.count(" ") >= 1
    )
    directory = values.get("DIR", "").strip()
    port = values.get("PORT", "").strip()
    pid = values.get("PID", "").strip()
    if not (port.isdigit() and int(port) > 0 and _PID.match(pid) and directory):
        raise SessionError(f"the echo service did not start: {stdout.strip()[-200:]}")
    return directory, int(port), pid


class ProbeSession:
    """Ephemeral echo + host mapping between one NPS edge and one NPC client.

    Use as a context manager; leaving it always attempts cleanup and records
    any leftovers in :attr:`cleanup_problems`.

    Args:
        cluster: Cluster exposing ``get_edge``, ``get_npc_client`` and the
            link-collection accessors.
        edge: Edge name.
        client: NPC client name from ``clients.toml``.
        ssh: SSH runner, replaceable in tests.
        mapping: Host-mapping backend, replaceable in tests.
        http_proxy_port: NPS HTTP proxy port on the edge; discovered from the
            edge's ``nps.conf`` when omitted.
        sleep: Sleep function, replaceable in tests.
    """

    def __init__(
        self,
        cluster: Any,
        edge: str,
        client: str,
        *,
        ssh: SshRunner = ssh_execute,
        mapping: MappingApi | None = None,
        http_proxy_port: int | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self.cluster = cluster
        self.edge = edge
        self.client = client
        self.ssh = ssh
        self.mapping: MappingApi = mapping or NpsMapping(cluster)
        self.http_proxy_port = http_proxy_port
        self.sleep = sleep
        self.token = secrets.token_hex(4)
        self.domain = f"nps-ctl-check-{self.token}{DOMAIN_SUFFIX}"
        self.cleanup_problems: list[str] = []
        self._runs = 0
        self._echo_dir = ""
        self._echo_pid = ""
        self._echo_port = 0
        self._host_id: int | None = None
        self._mapping_attempted = False

        edge_config = cluster.get_edge(edge)
        npc = cluster.get_npc_client(client)
        if edge_config is None:
            raise SessionError(f"edge '{edge}' not found")
        if npc is None:
            raise SessionError(f"client '{client}' not found in clients.toml")
        if not edge_config.ssh_host:
            raise SessionError(f"edge '{edge}' has no ssh_host configured")
        if edge not in npc.edges:
            raise SessionError(f"client '{client}' is not connected to edge '{edge}'")
        self.edge_ssh = edge_config.ssh_host
        self.client_ssh = npc.ssh_host
        self.client_ssh_user = npc.ssh_user
        self.client_remark = npc.remark

    def _run(
        self, host_name: str, script: str, timeout: int, user: str = ""
    ) -> DeployResult:
        return self.ssh(host_name, script, timeout=timeout, ssh_user=user)

    def __enter__(self) -> ProbeSession:
        try:
            self.setup()
        except BaseException:
            self.cleanup()
            raise
        return self

    def __exit__(self, *exc: object) -> None:
        self.cleanup()

    def setup(self) -> None:
        """Start the echo service, discover the proxy port and map the domain."""
        result = self._run(
            self.client_ssh, echo_start_script(), 60, self.client_ssh_user
        )
        if not result.success:
            raise SessionError(
                f"cannot start echo on {self.client_ssh}: {result.message}"
            )
        self._echo_dir, self._echo_port, self._echo_pid = parse_handle(result.stdout)

        if self.http_proxy_port is None:
            self.http_proxy_port = self._discover_http_proxy_port()

        # The create can be accepted and still fail to return an id; cleanup
        # then has to look for the row by domain.
        self._mapping_attempted = True
        self._host_id = self.mapping.add(
            self.edge,
            self.client_remark,
            self.domain,
            f"127.0.0.1:{self._echo_port}",
        )
        self._wait_ready()

    def _discover_http_proxy_port(self) -> int:
        script = (
            "grep -hE '^http_proxy_port' /etc/nps/conf/nps.conf 2>/dev/null "
            "| head -1 | cut -d= -f2 | tr -d ' \\r'\n"
        )
        result = self._run(self.edge_ssh, script, 30)
        if not result.success:
            raise SessionError(f"cannot reach edge {self.edge_ssh}: {result.message}")
        out = result.stdout.strip()
        return int(out) if out.isdigit() else DEFAULT_HTTP_PROXY_PORT

    def _wait_ready(self, attempts: int = 10) -> None:
        last = ""
        for _ in range(attempts):
            run = self.run_load(
                LAYER_VIA_NPS,
                {"size": 1024, "count": 1, "concurrency": 1, "timeout": 5},
            )
            if run.result and run.result.get("outcomes") == {"ok": 1}:
                return
            last = run.error or json.dumps(run.result and run.result.get("outcomes"))
            self.sleep(1.0)
        raise SessionError(
            f"the new host mapping did not become reachable through NPS: {last}"
        )

    def cleanup(self) -> list[str]:
        """Remove the host mapping and the echo service.

        Returns:
            Problems that left something behind, with the manual fix. Also
            stored in :attr:`cleanup_problems`.
        """
        problems: list[str] = []
        manual = (
            f"remove it with 'nps-ctl host del -e {self.edge} "
            f"--domain {self.domain} -y'"
        )
        if self._host_id is not None:
            try:
                self.mapping.remove(self.edge, self._host_id, self.domain)
                self._host_id = None
            except Exception as exc:  # noqa: BLE001 - report, never mask the original error
                problems.append(
                    f"host mapping {self.domain} (id {self._host_id}) is still on "
                    f"{self.edge}: {exc}; {manual}"
                )
        elif self._mapping_attempted:
            try:
                removed = self.mapping.remove_unclaimed(self.edge, self.domain)
                if removed == 0:
                    raise SessionError("the edge lists no mapping for it either")
            except Exception as exc:  # noqa: BLE001
                problems.append(
                    f"a host mapping for {self.domain} may still be on "
                    f"{self.edge} from a create whose id was never returned: "
                    f"{exc}; {manual}"
                )
        if self._echo_dir:
            try:
                script = echo_stop_script(self._echo_dir, self._echo_pid)
                result = self._run(self.client_ssh, script, 30, self.client_ssh_user)
                if result.success:
                    self._echo_dir = ""
                else:
                    raise SessionError(result.message)
            except Exception as exc:  # noqa: BLE001
                problems.append(
                    f"echo service ({self._echo_dir}, pid {self._echo_pid}) may still "
                    f"run on {self.client_ssh}: {exc}; it exits by itself after "
                    f"{ECHO_TTL_SECONDS}s"
                )
        self.cleanup_problems = problems
        return problems

    def run_load(
        self, layer: str, overrides: dict[str, Any], timeout: int | None = None
    ) -> LayerRun:
        """Run the load generator for *layer*.

        Args:
            layer: ``client_local`` (client host to echo, no tunnel) or
                ``via_nps`` (edge host through NPS, NPC and the tunnel).
            overrides: Load-spec fields, see :mod:`nps_ctl.check.loadgen`.
            timeout: SSH timeout in seconds; derived from the spec when omitted.

        Returns:
            The layer run; ``error`` is set instead of raising when the
            generator could not run or printed nothing parseable.
        """
        if layer == LAYER_CLIENT_LOCAL:
            where, user = self.client_ssh, self.client_ssh_user
            target = {"host": "127.0.0.1", "port": self._echo_port, "host_header": ""}
        elif layer == LAYER_VIA_NPS:
            where, user = self.edge_ssh, ""
            target = {
                "host": "127.0.0.1",
                "port": self.http_proxy_port,
                "host_header": self.domain,
            }
        else:
            raise ValueError(f"unknown layer {layer!r}")

        self._runs += 1
        spec = {
            **overrides,
            **target,
            "seed": f"{self.token}-{layer}-{self._runs}",
        }
        if timeout is None:
            timeout = self._ssh_timeout(spec)
        result = self._run(where, load_script(spec), timeout, user)
        if not result.success:
            return LayerRun(layer, where, None, result.message)
        lines = [line for line in result.stdout.splitlines() if line.strip()]
        try:
            return LayerRun(layer, where, json.loads(lines[-1]))
        except (IndexError, ValueError):
            tail = (result.stderr or result.stdout).strip()[-200:]
            return LayerRun(layer, where, None, f"unparseable generator output: {tail}")

    @staticmethod
    def _ssh_timeout(spec: dict[str, Any]) -> int:
        per_request = float(spec.get("timeout", loadgen.DEFAULTS["timeout"]))
        if spec.get("duration"):
            return int(float(spec["duration"]) + per_request + 60)
        count = int(spec.get("count", loadgen.DEFAULTS["count"]))
        workers = max(1, int(spec.get("concurrency", loadgen.DEFAULTS["concurrency"])))
        return int(min(3600, (count / workers + 2) * per_request + 60))

    def outages(self, since: float) -> list[Outage]:
        """Return this edge's bridge outages from the client's NPC log.

        Args:
            since: Window length in seconds ending now on the client.

        Returns:
            Outages of the bridge to this session's edge; empty when the log
            could not be read.
        """
        reports, _, _ = collect_links(
            self.cluster, [self.client], since=since, ssh=self.ssh, max_workers=1
        )
        return [o for r in reports if r.edge == self.edge for o in r.outages]
