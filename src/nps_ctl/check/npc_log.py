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
    message carries even when the two timeouts are logged a second apart. A
    timeout with no stamp at all cannot be compared that way; the caller folds
    it in provisionally and a later ``Start server`` line decides whether it was
    a repeat or a second bridge.

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


# How long after a drop's last outage has closed a ``Start server`` line still
# counts as that drop's recovery rather than a fresh start.
TIE_GRACE = 60.0

# How many folded timeouts stay available for a tied bridge to claim. Only one
# per pending bridge can ever be redeemed, and the list is cleared when a new
# drop begins; the cap just bounds a long retry loop's log.
TIE_MEMORY = 32


def _open_for_start(
    event: NpcEvent,
    pending: set[str] | None,
    folds: list[tuple[float, float]],
    episode_closed_at: float | None,
) -> Outage | None:
    """Open the outage a ``Start server`` line accounts for, or ``None``.

    NPC stamps the last-answered ping to the second, so two bridges that stop
    answering in the same second produce identical stamps and the second is
    folded into the first. Its ``Start server`` line then names a bridge no open
    outage carries — the moment this outage can be created. While the drop it
    belongs to still counts as running — an outage of it is open, or the last
    one closed moments ago — the fold supplies the shared stamp.

    A drop that is over has no such stamp to offer: a ``Start server`` long
    after the fact is the client's own restart of a bridge, and dating it from
    the old drop would report hours of downtime that never happened. That
    outage starts at the ``Start server`` line instead, the earliest moment the
    log proves the bridge was not serving.

    Only a bridge that was connected when the drop began can have gone down
    with it; a client's first start, or a bridge added since, invents nothing.

    Args:
        event: A ``Start server`` event that matched no open outage.
        pending: Bridges that were connected when the current drop began, less
            the ones the log has shown connected again since — or ``None`` when
            the log gives no way to tell.
        folds: ``(last_alive, seen_at)`` for each timeout folded into an
            unnamed outage of the current drop, oldest first.
        episode_closed_at: Epoch seconds the drop's last outage closed, or
            ``None`` while one is still open.

    Returns:
        The outage to open, or ``None`` when the event proves nothing.
    """
    if pending is not None and event.server not in pending:
        return None
    if pending is None and not folds:
        return None
    if pending is not None:
        pending.discard(event.server)
    running = episode_closed_at is None or event.time - episode_closed_at <= TIE_GRACE
    if folds and running:
        last_alive, seen_at = folds.pop(0)
        return Outage(server=event.server, last_alive=last_alive, detected=seen_at)
    return Outage(server=event.server, last_alive=event.time, detected=event.time)


def find_outages(events: list[NpcEvent]) -> list[Outage]:
    """Group link events into outage windows.

    Every ping timeout opens its own outage, starting at the last answered
    ping. The bridge it belongs to is named by the ``Start server`` line that
    follows it, because the timeout line carries no server. Events are paired
    oldest-first: when a client bridges several edges and its own network
    blips, several muxes time out within seconds of each other, and folding
    them together would credit one edge with another's downtime.

    Two timeouts can share a stamp, because NPC records the last answer to the
    second: both bridges stopped answering in the same second. The second is
    folded into the first as a repeat, and the fold is remembered while that
    outage still has no name — an outage that has been named has already had
    its ``Start server`` line, so nothing is waiting to claim a fold for it. The
    tied bridge then gets its own outage when its ``Start server`` line arrives,
    with the shared stamp, however long either bridge takes to reconnect. A
    timeout line with no stamp at all cannot be compared, so the drop time is
    estimated from the timeout line itself.

    An outage ends at the ``Successful connection`` naming the same server, or
    the oldest unnamed outage when the event carries no name. A ``Start
    server`` or ``Successful connection`` with no outage open is the client's
    initial connection and is ignored, unless the bridge was connected when the
    current drop began and the log has not shown it back since: that line is the
    earliest moment the log proves it stopped serving.

    Args:
        events: Events in time order, as returned by :func:`parse_log`.

    Returns:
        Outages in time order. The last one has ``reconnected is None`` when
        the log ends before the link came back.
    """
    outages: list[Outage] = []
    open_outages: list[Outage] = []
    folds: list[tuple[float, float]] = []
    connected_at: dict[str, float] = {}
    pending: set[str] | None = None
    episode_closed_at: float | None = None
    for event in events:
        if event.kind == CONNECTED:
            connected_at[event.server] = event.time
            # A bridge that connected again is up, so it did not stay down
            # with the drop; it is no longer a candidate for a tied outage.
            if pending is not None:
                pending.discard(event.server)

        if event.kind == PING_TIMEOUT:
            if event.last_alive is None:
                # No stamp to compare, so the timeout is provisional: fold it
                # into the newest outage and let the next Start server line
                # decide. A line naming a bridge that already has an outage
                # confirms the repeat; a line naming a new bridge claims the
                # fold and opens that bridge's outage.
                newest = open_outages[-1] if open_outages else None
                if newest is not None:
                    newest.detected = event.time
                    if not newest.server:
                        folds.append((event.time, event.time))
                        del folds[:-TIE_MEMORY]
                    continue
                last_alive = event.time
            else:
                last_alive = event.last_alive
            repeat = _repeat_of(open_outages, last_alive)
            if repeat is not None:
                repeat.last_alive = min(repeat.last_alive, last_alive)
                repeat.detected = event.time
                if not repeat.server:
                    folds.append((last_alive, event.time))
                    del folds[:-TIE_MEMORY]
                continue
            if not open_outages:
                # A new drop: the bridges connected right now are the ones that
                # can have gone down with it, and folds left by an earlier drop
                # are stale.
                pending = set(connected_at) or None
                episode_closed_at = None
                folds.clear()
            outage = Outage(server="", last_alive=last_alive, detected=event.time)
            outages.append(outage)
            open_outages.append(outage)
            continue
        target = _oldest_open(open_outages, event.server)
        if target is None:
            if event.kind == START_SERVER:
                opened = _open_for_start(event, pending, folds, episode_closed_at)
                if opened is not None:
                    outages.append(opened)
                    open_outages.append(opened)
            continue
        if event.kind == START_SERVER:
            if not target.server:
                target.server = event.server
                if pending is not None:
                    pending.discard(event.server)
        elif event.kind == CONNECT_FAILED:
            target.failed_attempts += 1
            if not target.server:
                target.server = event.server
                if pending is not None:
                    pending.discard(event.server)
            reason = classify_error(event.detail)
            if reason not in target.reasons:
                target.reasons.append(reason)
        elif event.kind == CONNECTED:
            target.reconnected = event.time
            if not target.server:
                target.server = event.server
            open_outages.remove(target)
            if not open_outages and episode_closed_at is None:
                # The drop is over. A later outage opened by a ``Start server``
                # line must not move this forward: that would keep re-arming
                # the grace window and let an old fold be redeemed long after
                # its drop.
                episode_closed_at = event.time
    return outages
