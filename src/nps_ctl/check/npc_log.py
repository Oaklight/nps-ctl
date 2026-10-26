"""Parse NPC client logs into link events and outage windows.

NPC writes one JSON object per line (``level``, ``time``, ``caller``,
``message``). Only the message text is matched, not the ``caller`` source
line, because the line numbers change between NPC builds.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime

PING_TIMEOUT = "ping_timeout"
MUX_CLOSED = "mux_closed"
CLIENT_CLOSED = "client_closed"
START_SERVER = "start_server"
CONNECT_FAILED = "connect_failed"
CONNECTED = "connected"

_LAST_ALIVE = re.compile(
    r"last alive (\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})(?:\.(\d+))? ([+-]\d{4})"
)
_START = re.compile(r"Start server: (\S+)")
_FAILED = re.compile(r"Failed to connect to server (\S+) error: (.*)", re.DOTALL)
_CONNECTED = re.compile(r"Successful connection with server (\S+)")
# Log text can quote verify keys; anything that looks like one is never echoed.
_SECRET_LIKE = re.compile(r"[A-Za-z0-9]{12,}")


@dataclass(frozen=True)
class NpcEvent:
    """A link-lifecycle event found in an NPC log.

    Attributes:
        time: Event time as epoch seconds.
        kind: One of the module-level kind constants.
        server: ``host:port`` the event names, empty when the log line has none.
        detail: Free text such as the connection error.
        last_alive: For ping timeouts, epoch seconds of the last good ping.
    """

    time: float
    kind: str
    server: str = ""
    detail: str = ""
    last_alive: float | None = None


@dataclass
class Outage:
    """A period in which one bridge connection was not usable.

    Attributes:
        server: ``host:port`` of the bridge, empty when it could not be named.
        last_alive: Epoch seconds of the last ping that was answered.
        detected: Epoch seconds when NPC declared the ping timeout.
        reconnected: Epoch seconds of the next successful connection, or
            ``None`` while the outage is still open at the end of the log.
        failed_attempts: Reconnect attempts that failed in between.
        reasons: Distinct classified failure reasons, in first-seen order.
    """

    server: str
    last_alive: float
    detected: float
    reconnected: float | None = None
    failed_attempts: int = 0
    reasons: list[str] = field(default_factory=list)

    @property
    def start(self) -> float:
        """Epoch seconds at which traffic on this bridge stopped flowing."""
        return self.last_alive

    def end(self, now: float) -> float:
        """Return the outage end, or *now* if it is still open."""
        return self.reconnected if self.reconnected is not None else now

    def duration(self, now: float) -> float:
        """Return the outage length in seconds."""
        return self.end(now) - self.start


def classify_error(text: str) -> str:
    """Reduce a connection error message to a short stable reason."""
    lowered = text.lower()
    if "no route to host" in lowered:
        return "no route to host"
    if "i/o timeout" in lowered or "timed out" in lowered:
        return "timeout"
    if "connection refused" in lowered:
        return "connection refused"
    if "can not resolve" in lowered or "no such host" in lowered:
        return "dns failure"
    if "reset by peer" in lowered:
        return "connection reset"
    if "network is unreachable" in lowered:
        return "network unreachable"
    if "validation key" in lowered:
        return "verify key rejected"
    return _SECRET_LIKE.sub("<redacted>", text.strip())[:60] or "unknown"


def _parse_last_alive(message: str) -> float | None:
    match = _LAST_ALIVE.search(message)
    if not match:
        return None
    stamp, fraction, offset = match.groups()
    micro = (fraction or "0").ljust(6, "0")[:6]
    try:
        parsed = datetime.strptime(
            f"{stamp}.{micro} {offset}", "%Y-%m-%d %H:%M:%S.%f %z"
        )
    except ValueError:
        return None
    return parsed.timestamp()


def parse_line(line: str) -> NpcEvent | None:
    """Parse one log line, returning ``None`` for lines that are not events."""
    line = line.strip()
    if not line.startswith("{"):
        return None
    try:
        record = json.loads(line)
        when = datetime.fromisoformat(record["time"]).timestamp()
    except (ValueError, KeyError, TypeError):
        return None
    message = str(record.get("message", "")).strip()

    if message.startswith("mux: ping timeout"):
        return NpcEvent(when, PING_TIMEOUT, last_alive=_parse_last_alive(message))
    if message == "close mux":
        return NpcEvent(when, MUX_CLOSED)
    if message.startswith("Client closed!"):
        return NpcEvent(when, CLIENT_CLOSED)
    if match := _START.match(message):
        return NpcEvent(when, START_SERVER, server=match.group(1))
    if match := _FAILED.match(message):
        return NpcEvent(
            when, CONNECT_FAILED, server=match.group(1), detail=match.group(2).strip()
        )
    if match := _CONNECTED.match(message):
        return NpcEvent(when, CONNECTED, server=match.group(1))
    return None


def parse_log(text: str) -> list[NpcEvent]:
    """Parse a whole log, returning its events in time order."""
    events = [event for line in text.splitlines() if (event := parse_line(line))]
    events.sort(key=lambda event: event.time)
    return events


def _oldest_open(open_outages: list[Outage], server: str) -> Outage | None:
    """Return the open outage the next event for *server* belongs to.

    An event that names a server belongs to the oldest outage already carrying
    that name, so reconnects pair correctly when several bridges are down at
    once. Failing that, the oldest outage that has no name yet takes it, which
    is what the ``Start server`` line after a ping timeout relies on. A named
    event never falls back to an outage named for a different bridge.

    Args:
        open_outages: Outages that have not reconnected yet, oldest first.
        server: Server named by the event, empty when it names none.

    Returns:
        The matching outage, or ``None`` when no outage is open.
    """
    if server:
        for outage in open_outages:
            if outage.server == server:
                return outage
        # Never credit a named event to another bridge's outage: that would
        # close, or extend, the wrong bridge's downtime. An event nothing can
        # be attributed to is dropped and shows up as unattributed instead.
        return next((outage for outage in open_outages if not outage.server), None)
    return open_outages[0] if open_outages else None


def _repeat_of(open_outages: list[Outage], last_alive: float) -> Outage | None:
    """Return the open outage a timeout belongs to, or ``None`` for a new drop.

    A bridge that has not reconnected emits another ping timeout for the same
    drop, and NPC reports the same ``last alive`` stamp for it. Matching on that
    stamp is what separates a repeat from a second bridge dropping at the same
    moment: the second bridge stopped answering at its own time, which the
    message carries even when the two timeouts are logged a second apart.

    Args:
        open_outages: Outages that have not reconnected yet, oldest first.
        last_alive: The last answered ping reported by this timeout.

    Returns:
        The outage to extend, or ``None`` when this is a new drop.
    """
    for outage in reversed(open_outages):
        if outage.last_alive == last_alive:
            return outage
    return None


def find_outages(events: list[NpcEvent]) -> list[Outage]:
    """Group link events into outage windows.

    Every ping timeout opens its own outage, starting at the last answered
    ping. The bridge it belongs to is named by the ``Start server`` line that
    follows it, because the timeout line carries no server. Events are paired
    oldest-first: when a client bridges several edges and its own network
    blips, several muxes time out within seconds of each other, and folding
    them together would credit one edge with another's downtime.

    An outage ends at the ``Successful connection`` naming the same server, or
    the oldest unnamed outage when the event carries no name. A ``Start
    server`` or ``Successful connection`` with no outage open is the client's
    initial connection and is ignored.

    Args:
        events: Events in time order, as returned by :func:`parse_log`.

    Returns:
        Outages in time order. The last one has ``reconnected is None`` when
        the log ends before the link came back.
    """
    outages: list[Outage] = []
    open_outages: list[Outage] = []
    for event in events:
        if event.kind == PING_TIMEOUT:
            last_alive = event.last_alive or event.time
            repeat = _repeat_of(open_outages, last_alive)
            if repeat is not None:
                repeat.last_alive = min(repeat.last_alive, last_alive)
                repeat.detected = event.time
                continue
            outage = Outage(server="", last_alive=last_alive, detected=event.time)
            outages.append(outage)
            open_outages.append(outage)
            continue
        if not open_outages:
            continue
        target = _oldest_open(open_outages, event.server)
        if target is None:
            continue
        if event.kind == START_SERVER:
            if not target.server:
                target.server = event.server
        elif event.kind == CONNECT_FAILED:
            target.failed_attempts += 1
            if not target.server:
                target.server = event.server
            reason = classify_error(event.detail)
            if reason not in target.reasons:
                target.reasons.append(reason)
        elif event.kind == CONNECTED:
            target.reconnected = event.time
            if not target.server:
                target.server = event.server
            open_outages.remove(target)
    return outages
