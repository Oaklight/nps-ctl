"""Read-only web dashboard for an NPS cluster.

The dashboard is intentionally dependency-free: it uses the standard
library HTTP server and serves one HTML page backed by JSON endpoints.
"""

from __future__ import annotations

import base64
import hmac
import json
import logging
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import TYPE_CHECKING, Any
from urllib.parse import unquote, urlparse

from . import client_mgmt, host, tunnel
from .exceptions import NPSError
from .status import build_status_payload, collect_edge_status

if TYPE_CHECKING:
    from .cluster import NPSCluster

logger = logging.getLogger(__name__)

LOOPBACK_HOSTS = {"127.0.0.1", "::1", "localhost"}
RESOURCES = {"clients", "tunnels", "hosts"}
SENSITIVE_ROW_KEYS = ("VerifyKey", "Password", "WebPassword", "BasicPassword")


def _redact_row(item: Any) -> Any:
    """Return a copy of a resource row with credentials redacted."""
    if not isinstance(item, dict):
        return item
    row = dict(item)
    for key in SENSITIVE_ROW_KEYS:
        if row.get(key):
            row[key] = "**redacted**"
    user_auth = row.get("UserAuth")
    if isinstance(user_auth, dict) and user_auth.get("Content"):
        row["UserAuth"] = {"Content": "**redacted**", "AccountMap": {}}
    client = row.get("Client")
    if isinstance(client, dict):
        row["Client"] = _redact_row(client)
    cnf = row.get("Cnf")
    if isinstance(cnf, dict):
        cnf = dict(cnf)
        for key in ("P", "Password"):
            if cnf.get(key):
                cnf[key] = "**redacted**"
        row["Cnf"] = cnf
    return row


def build_auth_header(username: str, password: str) -> str:
    """Build an HTTP Basic Authorization header value.

    Args:
        username: Dashboard username.
        password: Dashboard password.

    Returns:
        Header value, or an empty string when no username is configured.
    """
    if not username:
        return ""
    token = base64.b64encode(f"{username}:{password}".encode()).decode("ascii")
    return f"Basic {token}"


def _overview(cluster: NPSCluster) -> dict[str, Any]:
    """Collect edge status and resource counts for the dashboard."""
    rows = collect_edge_status(
        cluster,
        include_hosts=True,
        include_tunnels=True,
    )
    payload = build_status_payload(rows)
    totals = payload["totals"]
    return {
        "edges": [
            {
                "name": row.edge,
                "region": row.region,
                "api_url": row.api_url,
                "online": row.online,
                "ok": row.ok,
                "partial": row.partial,
                "error": row.error or None,
                "clients": row.clients_total,
                "clients_online": row.clients_online,
                "tunnels": row.tunnels_total,
                "tunnels_running": row.tunnels_running,
                "hosts": row.hosts_total,
                "ports": row.ports,
                "tunnel_ports": row.tunnel_ports,
            }
            for row in rows
        ],
        "summary": {
            "edges": len(rows),
            "online": payload["summary"]["online"],
            "ok": totals["ok"],
            "partial": totals["partial"],
            "clients": totals["clients"],
            "tunnels": totals["tunnels"],
            "hosts": totals["hosts"],
        },
    }


def _edge_items(cluster: NPSCluster, edge_name: str, resource: str) -> list[Any]:
    """Fetch one resource type from one edge.

    Args:
        cluster: NPSCluster instance.
        edge_name: Configured edge name.
        resource: One of ``clients``, ``tunnels``, ``hosts``.

    Returns:
        Rows with Basic Auth credentials redacted.

    Raises:
        KeyError: If the edge or resource is unknown.
    """
    if resource not in RESOURCES:
        raise KeyError(resource)
    nps = cluster.get_client(edge_name)
    if nps is None:
        raise KeyError(edge_name)

    if resource == "clients":
        items: list[Any] = client_mgmt.list_clients(nps)
    elif resource == "tunnels":
        items = tunnel.list_tunnels(nps)
    else:
        items = host.list_hosts(nps)
    return [_redact_row(item) for item in items]


class _AdminHandler(BaseHTTPRequestHandler):
    """HTTP handler for the dashboard and its JSON API."""

    server_version = "nps-ctl-web"

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        if not self._check_auth():
            return

        path = urlparse(self.path).path.rstrip("/") or "/"
        try:
            if path == "/":
                self._send_html(_DASHBOARD_HTML)
            elif path == "/api/overview":
                self._send_json(_overview(getattr(self.server, "cluster")))
            elif path.startswith("/api/edges/"):
                parts = [unquote(part) for part in path.strip("/").split("/")]
                if len(parts) != 4:
                    raise KeyError(path)
                _, _, edge_name, resource = parts
                try:
                    items = _edge_items(
                        getattr(self.server, "cluster"), edge_name, resource
                    )
                except NPSError as e:
                    self._send_json(
                        {"error": str(e), "edge": edge_name, "resource": resource},
                        status=502,
                    )
                    return
                self._send_json(
                    {"edge": edge_name, "resource": resource, "items": items}
                )
            else:
                self._send_json({"error": "Not found"}, status=404)
        except KeyError:
            self._send_json({"error": "Not found"}, status=404)
        except Exception:
            logger.exception("Dashboard request failed: %s", path)
            self._send_json({"error": "Internal server error"}, status=500)

    def _check_auth(self) -> bool:
        expected = getattr(self.server, "auth_header", "")
        if not expected:
            return True
        supplied = self.headers.get("Authorization", "")
        if hmac.compare_digest(supplied, expected):
            return True
        self.send_response(401)
        self.send_header("WWW-Authenticate", 'Basic realm="nps-ctl"')
        self.send_header("Content-Length", "0")
        self._common_headers()
        self.end_headers()
        return False

    def _send_html(self, body: str) -> None:
        encoded = body.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self._common_headers()
        self.end_headers()
        self.wfile.write(encoded)

    def _send_json(self, payload: dict[str, Any], status: int = 200) -> None:
        encoded = json.dumps(payload, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self._common_headers()
        self.end_headers()
        self.wfile.write(encoded)

    def _common_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'none'; script-src 'unsafe-inline'; "
            "style-src 'unsafe-inline'; connect-src 'self'",
        )

    def log_message(self, format: str, *args: Any) -> None:
        logger.info("%s - %s", self.address_string(), format % args)


class AdminServer(ThreadingHTTPServer):
    """HTTP server carrying the cluster and optional auth header."""

    daemon_threads = True

    def __init__(
        self,
        address: tuple[str, int],
        cluster: NPSCluster,
        auth_header: str = "",
    ) -> None:
        super().__init__(address, _AdminHandler)
        self.cluster = cluster
        self.auth_header = auth_header


def create_server(
    cluster: NPSCluster,
    host: str = "127.0.0.1",
    port: int = 8080,
    username: str = "",
    password: str = "",
    *,
    allow_insecure: bool = False,
) -> AdminServer:
    """Create the dashboard server.

    Args:
        cluster: NPSCluster instance.
        host: Bind address.
        port: Bind port (0 chooses an ephemeral port).
        username: Optional Basic Auth username.
        password: Optional Basic Auth password.
        allow_insecure: Allow a non-loopback bind without authentication.

    Returns:
        A configured, not-yet-serving AdminServer.

    Raises:
        ValueError: If a username has no password, or a non-loopback bind
            has no authentication and ``allow_insecure`` is false.
    """
    if username and not password:
        raise ValueError("Basic Auth username requires a non-empty password")
    if (
        host not in LOOPBACK_HOSTS
        and not (username and password)
        and not allow_insecure
    ):
        raise ValueError(
            "Refusing to expose the dashboard without authentication; "
            "set --username/--password or pass --insecure"
        )
    return AdminServer(
        (host, port), cluster, auth_header=build_auth_header(username, password)
    )


_DASHBOARD_HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>NPS Cluster</title>
<style>
  :root { color-scheme: light dark; --fg: #1f2328; --bg: #f6f8fa;
          --card: #ffffff; --muted: #656d76; --line: #d0d7de;
          --ok: #1a7f37; --bad: #cf222e; --warn: #9a6700; }
  @media (prefers-color-scheme: dark) {
    :root { --fg: #e6edf3; --bg: #0d1117; --card: #161b22;
            --muted: #8d96a0; --line: #30363d; --ok: #3fb950; --bad: #f85149;
            --warn: #d29922; }
  }
  * { box-sizing: border-box; }
  body { margin: 0; padding: 24px; font: 15px/1.5 system-ui, sans-serif;
         color: var(--fg); background: var(--bg); }
  h1 { font-size: 22px; margin: 0 0 16px; }
  h2 { font-size: 17px; margin: 24px 0 8px; }
  .cards { display: flex; flex-wrap: wrap; gap: 12px; margin-bottom: 20px; }
  .card { background: var(--card); border: 1px solid var(--line);
          border-radius: 8px; padding: 12px 16px; min-width: 120px; }
  .card .num { font-size: 24px; font-weight: 600; }
  .card .label { color: var(--muted); font-size: 12px; text-transform: uppercase; }
  table { width: 100%; border-collapse: collapse; background: var(--card);
          border: 1px solid var(--line); border-radius: 8px; overflow: hidden; }
  th, td { text-align: left; padding: 8px 10px; border-bottom: 1px solid var(--line);
           vertical-align: top; }
  tr:last-child td { border-bottom: 0; }
  th { color: var(--muted); font-size: 12px; text-transform: uppercase; }
  .ok { color: var(--ok); } .bad { color: var(--bad); }
  .warn { color: var(--warn); }
  button { font: inherit; padding: 4px 10px; margin-right: 4px;
           border: 1px solid var(--line); border-radius: 6px;
           background: var(--card); color: var(--fg); cursor: pointer; }
  button:hover { border-color: var(--muted); }
  #detail { margin-top: 24px; }
  .empty, .error { color: var(--muted); padding: 8px 0; }
  .error { color: var(--bad); }
  .mono { font-family: ui-monospace, monospace; font-size: 13px; }
</style>
</head>
<body>
<h1>NPS Cluster</h1>
<div class="cards" id="summary"></div>
<table>
  <thead><tr><th>Edge</th><th>Region</th><th>Status</th><th>Clients</th>
  <th>Tunnels</th><th>Hosts</th><th></th></tr></thead>
  <tbody id="edges"><tr><td colspan="7" class="empty">Loading…</td></tr></tbody>
</table>
<div id="detail"></div>
<script>
const summary = document.getElementById('summary');
const edgesBody = document.getElementById('edges');
const detail = document.getElementById('detail');

function el(tag, text, cls) {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  if (cls) node.className = cls;
  return node;
}

function display(value) {
  return value === null || value === undefined ? '—' : String(value);
}

function card(value, label) {
  const box = el('div', undefined, 'card');
  box.append(el('div', display(value), 'num'), el('div', label, 'label'));
  return box;
}

function renderSummary(s) {
  summary.replaceChildren(
    card(s.online + '/' + s.edges, 'edges online'),
    card(s.clients, 'clients'),
    card(s.tunnels, 'tunnels'),
    card(s.hosts, 'hosts')
  );
}

function renderEdges(edges) {
  edgesBody.replaceChildren();
  for (const edge of edges) {
    const row = document.createElement('tr');
    row.append(el('td', edge.name, 'mono'), el('td', edge.region || '—'));
    const status = el('td');
    const state = edge.ok ? ['online', 'ok']
                : edge.partial ? ['partial', 'warn']
                : ['offline', 'bad'];
    status.append(el('span', state[0], state[1]));
    if (edge.error) status.append(el('div', edge.error, 'error mono'));
    row.append(status, el('td', display(edge.clients)),
               el('td', display(edge.tunnels)), el('td', display(edge.hosts)));
    const actions = el('td');
    for (const resource of ['clients', 'tunnels', 'hosts']) {
      const button = el('button', resource);
      button.onclick = () => loadResource(edge.name, resource);
      actions.append(button);
    }
    row.append(actions);
    edgesBody.append(row);
  }
}

async function loadResource(edgeName, resource) {
  detail.replaceChildren(el('h2', edgeName + ' / ' + resource));
  const box = el('div', 'Loading…', 'empty');
  detail.append(box);
  try {
    const response = await fetch('api/edges/' + encodeURIComponent(edgeName) +
                                 '/' + resource);
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error || response.statusText);
    if (!payload.items.length) {
      box.textContent = 'No ' + resource + '.';
      return;
    }
    const columns = Object.keys(payload.items[0]);
    const table = el('table');
    const head = document.createElement('tr');
    for (const column of columns) head.append(el('th', column));
    const thead = document.createElement('thead');
    thead.append(head);
    table.append(thead);
    const tbody = document.createElement('tbody');
    for (const item of payload.items) {
      const row = document.createElement('tr');
      for (const column of columns) {
        let value = item[column];
        if (value && typeof value === 'object') value = JSON.stringify(value);
        const cell = el('td', value === undefined || value === null ? '' : String(value));
        if (column === 'UserAuth' || column === 'Target' || column === 'Client') {
          cell.className = 'mono';
        }
        row.append(cell);
      }
      tbody.append(row);
    }
    table.append(tbody);
    box.replaceWith(table);
  } catch (error) {
    box.className = 'error';
    box.textContent = 'Failed to load: ' + error.message;
  }
}

async function load() {
  try {
    const response = await fetch('api/overview');
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error || response.statusText);
    renderSummary(payload.summary);
    renderEdges(payload.edges);
  } catch (error) {
    const row = document.createElement('tr');
    row.append(el('td', 'Failed to load: ' + error.message, 'error'));
    edgesBody.replaceChildren(row);
  }
}

load();
</script>
</body>
</html>
"""
