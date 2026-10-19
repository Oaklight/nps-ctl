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
from .status import build_status_payload, collect_cluster_status

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
    status = collect_cluster_status(
        cluster,
        include_hosts=True,
        include_tunnels=True,
    )
    rows = status.rows
    payload = build_status_payload(rows)
    totals = payload["totals"]
    unique = status.unique
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
                "missing": status.missing.get(row.edge),
            }
            for row in rows
        ],
        "summary": {
            "edges": len(rows),
            "online": payload["summary"]["online"],
            "ok": totals["ok"],
            "partial": totals["partial"],
            "clients": unique.get("clients"),
            "tunnels": unique.get("tunnels"),
            "hosts": unique.get("hosts"),
            "in_sync": sum(
                1
                for missing in status.missing.values()
                if missing and not any(missing.values())
            ),
            "replicated": {
                "clients": totals["clients"],
                "tunnels": totals["tunnels"],
                "hosts": totals["hosts"],
            },
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
          --hover: #f6f8fa; --accent: #0969da; --sel: #ddf4ff;
          --ok: #1a7f37; --ok-bg: #dafbe1; --bad: #cf222e; --bad-bg: #ffebe9;
          --warn: #9a6700; --warn-bg: #fff8c5; --muted-bg: #eaeef2; }
  @media (prefers-color-scheme: dark) {
    :root { --fg: #e6edf3; --bg: #0d1117; --card: #161b22;
            --muted: #8d96a0; --line: #30363d; --hover: #1c2128;
            --accent: #4493f8; --sel: #121d2f;
            --ok: #3fb950; --ok-bg: rgba(46, 160, 67, 0.15);
            --bad: #f85149; --bad-bg: rgba(248, 81, 73, 0.15);
            --warn: #d29922; --warn-bg: rgba(187, 128, 9, 0.15);
            --muted-bg: #21262d; }
  }
  * { box-sizing: border-box; }
  body { margin: 0; padding: 24px; font: 14px/1.5 system-ui, sans-serif;
         color: var(--fg); background: var(--bg); }
  main { max-width: 1280px; margin: 0 auto; }
  header { display: flex; align-items: center; gap: 12px; flex-wrap: wrap;
           margin-bottom: 16px; }
  h1 { font-size: 20px; margin: 0; flex: 1; }
  h2 { font-size: 16px; margin: 0; }
  .cards { display: grid; grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
           gap: 12px; margin-bottom: 20px; }
  .card { background: var(--card); border: 1px solid var(--line);
          border-radius: 8px; padding: 12px 16px; }
  .card .num { font-size: 24px; font-weight: 600; font-variant-numeric: tabular-nums; }
  .card .label { color: var(--muted); font-size: 12px; text-transform: uppercase; }
  .card .note { color: var(--muted); font-size: 12px; }
  .card.warn .num { color: var(--warn); }
  .scroll { overflow-x: auto; background: var(--card); border: 1px solid var(--line);
            border-radius: 8px; }
  table { width: 100%; border-collapse: collapse; }
  th, td { text-align: left; padding: 8px 12px; border-bottom: 1px solid var(--line);
           vertical-align: top; white-space: nowrap; }
  tbody tr:last-child td { border-bottom: 0; }
  th { color: var(--muted); font-size: 12px; font-weight: 600;
       text-transform: uppercase; background: var(--card); }
  th.num, td.num { text-align: right; font-variant-numeric: tabular-nums; }
  .sub { color: var(--muted); font-size: 12px; }
  .muted { color: var(--muted); }
  .mono { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 13px; }
  .name { font-weight: 600; }
  .badge { display: inline-block; padding: 0 8px; border-radius: 999px;
           font-size: 12px; font-weight: 600; line-height: 20px; }
  .badge.ok { color: var(--ok); background: var(--ok-bg); }
  .badge.bad { color: var(--bad); background: var(--bad-bg); }
  .badge.warn { color: var(--warn); background: var(--warn-bg); }
  .badge.muted { color: var(--muted); background: var(--muted-bg); }
  button { font: inherit; font-size: 13px; padding: 4px 10px;
           border: 1px solid var(--line); border-radius: 6px;
           background: var(--card); color: var(--fg); cursor: pointer; }
  button:hover { border-color: var(--muted); }
  button[aria-pressed="true"] { background: var(--accent); border-color: var(--accent);
                                color: #ffffff; }
  button:disabled { opacity: 0.6; cursor: progress; }
  button:focus-visible, input:focus-visible, tr.item:focus-visible {
    outline: 2px solid var(--accent); outline-offset: -2px; }
  .chips { display: flex; gap: 4px; }
  tr.selected td { background: var(--sel); }
  #detail { margin-top: 24px; }
  .detail-head { display: flex; align-items: center; gap: 12px; flex-wrap: wrap;
                 margin-bottom: 8px; }
  .detail-head input { flex: 1; min-width: 180px; max-width: 320px; margin-left: auto;
                       padding: 5px 10px; font: inherit; color: var(--fg);
                       background: var(--card); border: 1px solid var(--line);
                       border-radius: 6px; }
  tr.item { cursor: pointer; }
  tr.item:hover td { background: var(--hover); }
  tr.item td:first-child::before { content: '▸'; display: inline-block; width: 1.2em;
                                   color: var(--muted); }
  tr.item.open td:first-child::before { content: '▾'; }
  tr.raw td { background: var(--bg); white-space: normal; }
  tr.raw pre { margin: 0; max-height: 360px; overflow: auto; font-size: 12px; }
  .empty { color: var(--muted); padding: 12px; }
  .error { color: var(--bad); }
  td .error { white-space: normal; max-width: 360px; }
  body.busy #summary, body.busy #edges { opacity: 0.6; transition: opacity 0.2s; }
  @media (max-width: 640px) { body { padding: 16px; } }
</style>
</head>
<body>
<main>
<header>
  <h1>NPS Cluster</h1>
  <span id="updated" class="muted" aria-live="polite"></span>
  <button id="refresh" type="button">Refresh</button>
</header>
<div class="cards" id="summary"></div>
<div class="scroll">
<table>
  <thead><tr><th>Edge</th><th>Region</th><th>Status</th><th class="num">Clients</th>
  <th class="num">Tunnels</th><th class="num">Hosts</th><th>Sync</th><th>Browse</th></tr></thead>
  <tbody id="edges"><tr><td colspan="8" class="empty">Loading edges…</td></tr></tbody>
</table>
</div>
<section id="detail"></section>
</main>
<script>
const summary = document.getElementById('summary');
const edgesBody = document.getElementById('edges');
const detail = document.getElementById('detail');
const refreshButton = document.getElementById('refresh');
const updated = document.getElementById('updated');
const RESOURCES = ['clients', 'tunnels', 'hosts'];
const state = { edges: null, edge: null, resource: null, items: [], filter: '' };

function el(tag, text, cls) {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  if (cls) node.className = cls;
  return node;
}

function display(value) {
  return value === null || value === undefined ? '—' : String(value);
}

function bytes(value) {
  const n = Number(value);
  if (value === null || value === undefined || value === '' || !isFinite(n)) return '—';
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  let size = n;
  let unit = 0;
  while (size >= 1024 && unit < units.length - 1) { size /= 1024; unit++; }
  return (unit ? size.toFixed(1) : String(size)) + ' ' + units[unit];
}

function badge(text, tone) { return el('span', text, 'badge ' + tone); }
function target(value) {
  return value && typeof value === 'object' ? value.TargetStr || '' : value || '';
}
function owner(item) { return (item.Client || {}).Remark || ''; }
function flow(item) {
  const f = item.Flow || {};
  return bytes(f.InletFlow) + ' / ' + bytes(f.ExportFlow);
}

const COLUMNS = {
  clients: [
    { label: 'ID', value: i => i.Id, cls: 'num' },
    { label: 'Remark', value: i => i.Remark, cls: 'name' },
    { label: 'Status', value: i => !i.Status ? badge('disabled', 'muted')
        : i.IsConnect ? badge('online', 'ok') : badge('offline', 'bad') },
    { label: 'Address', value: i => i.Addr, cls: 'mono' },
    { label: 'Version', value: i => i.Version },
    { label: 'In / out', value: i => bytes(i.InletFlow) + ' / ' + bytes(i.ExportFlow),
      cls: 'num' },
    { label: 'Last online', value: i => i.LastOnlineTime, cls: 'muted' },
  ],
  tunnels: [
    { label: 'ID', value: i => i.Id, cls: 'num' },
    { label: 'Remark', value: i => i.Remark, cls: 'name' },
    { label: 'Mode', value: i => i.Mode },
    { label: 'Port', value: i => i.Port, cls: 'num mono' },
    { label: 'Target', value: i => target(i.Target), cls: 'mono' },
    { label: 'Client', value: owner },
    { label: 'Status', value: i => !i.Status ? badge('disabled', 'muted')
        : i.RunStatus ? badge('running', 'ok') : badge('stopped', 'bad') },
    { label: 'In / out', value: flow, cls: 'num' },
  ],
  hosts: [
    { label: 'ID', value: i => i.Id, cls: 'num' },
    { label: 'Host', value: i => i.Host, cls: 'name mono' },
    { label: 'Location', value: i => i.Location, cls: 'mono' },
    { label: 'Target', value: i => target(i.Target), cls: 'mono' },
    { label: 'Client', value: owner },
    { label: 'Remark', value: i => i.Remark, cls: 'muted' },
    { label: 'Status', value: i => i.IsClose ? badge('closed', 'bad')
        : badge('active', 'ok') },
    { label: 'In / out', value: flow, cls: 'num' },
  ],
};

function card(value, label, note, tone) {
  const box = el('div', undefined, tone ? 'card ' + tone : 'card');
  box.append(el('div', display(value), 'num'), el('div', label, 'label'));
  if (note) box.append(el('div', note, 'note'));
  return box;
}

function renderSummary(s) {
  const replicated = s.replicated || {};
  const note = key => {
    const total = replicated[key];
    return total === null || total === undefined || total === s[key]
      ? '' : total + ' across all edges';
  };
  const cards = [
    card(s.ok + '/' + s.edges, 'edges ok'),
    card(s.clients, 'unique clients', note('clients')),
    card(s.tunnels, 'unique tunnels', note('tunnels')),
    card(s.hosts, 'unique hosts', note('hosts')),
    card(s.in_sync + '/' + s.edges, 'edges in sync', '',
         s.in_sync < s.edges ? 'warn' : ''),
  ];
  if (s.partial) cards.splice(1, 0, card(s.partial, 'partial'));
  summary.replaceChildren(...cards);
}

function countCell(total, extra, label) {
  const cell = el('td', display(total), 'num');
  if (extra !== null && extra !== undefined) cell.append(el('div', extra + ' ' + label, 'sub'));
  return cell;
}

function syncCell(edge) {
  const cell = el('td');
  const missing = edge.missing || {};
  const gaps = Object.entries(missing).filter(entry => entry[1] > 0);
  if (!Object.keys(missing).length) {
    cell.append(el('span', '—', 'muted'));
  } else if (!gaps.length) {
    cell.append(badge('in sync', 'ok'));
  } else {
    cell.append(badge('drift', 'warn'));
    cell.append(el('div', 'missing ' + gaps.map(e => e[1] + ' ' + e[0]).join(', '), 'sub'));
  }
  return cell;
}

function renderEdges(edges) {
  if (!edges) return;
  edgesBody.replaceChildren();
  for (const edge of edges) {
    const row = document.createElement('tr');
    if (edge.name === state.edge) row.className = 'selected';
    row.append(el('td', edge.name, 'mono name'), el('td', edge.region || '—'));
    const status = el('td');
    status.append(edge.ok ? badge('online', 'ok')
                  : edge.partial ? badge('partial', 'warn')
                  : badge('offline', 'bad'));
    if (edge.error) status.append(el('div', edge.error, 'error mono'));
    row.append(status,
               countCell(edge.clients, edge.clients_online, 'online'),
               countCell(edge.tunnels, edge.tunnels_running, 'running'),
               countCell(edge.hosts),
               syncCell(edge));
    const actions = el('td');
    const chips = el('div', undefined, 'chips');
    for (const resource of RESOURCES) {
      const button = el('button', resource);
      button.type = 'button';
      button.setAttribute('aria-pressed',
        String(edge.name === state.edge && resource === state.resource));
      button.onclick = () => loadResource(edge.name, resource);
      chips.append(button);
    }
    actions.append(chips);
    row.append(actions);
    edgesBody.append(row);
  }
}

function renderRows(tbody, count) {
  const columns = COLUMNS[state.resource];
  const needle = state.filter.trim().toLowerCase();
  tbody.replaceChildren();
  let shown = 0;
  for (const item of state.items) {
    const cells = columns.map(column => {
      const value = column.value(item);
      if (value instanceof Node) return value;
      if (value === null || value === undefined || value === '') return el('span', '—', 'muted');
      return document.createTextNode(String(value));
    });
    const text = cells.map(node => node.textContent).join(' ').toLowerCase();
    if (needle && !text.includes(needle)) continue;
    shown++;
    const row = el('tr', undefined, 'item');
    row.tabIndex = 0;
    row.setAttribute('aria-expanded', 'false');
    columns.forEach((column, index) => {
      const cell = el('td', undefined, column.cls);
      cell.append(cells[index]);
      row.append(cell);
    });
    const raw = el('tr', undefined, 'raw');
    raw.hidden = true;
    const toggle = () => {
      const open = raw.hidden;
      if (open && !raw.firstChild) {
        const cell = el('td');
        cell.colSpan = columns.length;
        cell.append(el('pre', JSON.stringify(item, null, 2), 'mono'));
        raw.append(cell);
      }
      raw.hidden = !open;
      row.classList.toggle('open', open);
      row.setAttribute('aria-expanded', String(open));
    };
    row.onclick = toggle;
    row.onkeydown = event => {
      if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); toggle(); }
    };
    tbody.append(row, raw);
  }
  count.textContent = needle ? shown + ' of ' + state.items.length
                             : state.items.length + ' total';
  if (!shown) {
    const row = document.createElement('tr');
    const cell = el('td', needle ? 'No matches.' : 'No ' + state.resource + '.', 'empty');
    cell.colSpan = columns.length;
    row.append(cell);
    tbody.append(row);
  }
}

function closeDetail() {
  state.edge = null;
  state.resource = null;
  detail.replaceChildren();
  renderEdges(state.edges);
}

async function loadResource(edgeName, resource, keepFilter) {
  state.edge = edgeName;
  state.resource = resource;
  state.items = [];
  if (!keepFilter) state.filter = '';
  renderEdges(state.edges);

  const head = el('div', undefined, 'detail-head');
  const title = el('h2');
  title.append(el('span', edgeName, 'mono'), ' / ' + resource);
  const count = el('span', '', 'muted');
  const filter = el('input');
  filter.type = 'search';
  filter.value = state.filter;
  filter.placeholder = 'Filter ' + resource + '…';
  filter.setAttribute('aria-label', 'Filter ' + resource);
  const close = el('button', 'Close');
  close.type = 'button';
  close.onclick = closeDetail;
  head.append(title, count, filter, close);
  const box = el('div', 'Loading…', 'empty');
  detail.replaceChildren(head, box);

  try {
    const response = await fetch('api/edges/' + encodeURIComponent(edgeName) +
                                 '/' + resource);
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error || response.statusText);
    if (state.edge !== edgeName || state.resource !== resource) return;
    state.items = payload.items;
    const table = el('table');
    const head = document.createElement('tr');
    for (const column of COLUMNS[resource]) {
      head.append(el('th', column.label, column.cls && column.cls.startsWith('num') ? 'num' : ''));
    }
    const thead = document.createElement('thead');
    thead.append(head);
    const tbody = document.createElement('tbody');
    table.append(thead, tbody);
    const wrap = el('div', undefined, 'scroll');
    wrap.append(table);
    box.replaceWith(wrap);
    filter.oninput = () => { state.filter = filter.value; renderRows(tbody, count); };
    renderRows(tbody, count);
  } catch (error) {
    box.className = 'error';
    box.textContent = 'Failed to load: ' + error.message;
  }
}

async function load() {
  refreshButton.disabled = true;
  refreshButton.textContent = 'Refreshing…';
  document.body.classList.add('busy');
  const started = performance.now();
  try {
    const response = await fetch('api/overview');
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error || response.statusText);
    state.edges = payload.edges;
    renderSummary(payload.summary);
    renderEdges(payload.edges);
    const seconds = ((performance.now() - started) / 1000).toFixed(1);
    updated.className = 'muted';
    updated.textContent = 'Updated ' + new Date().toLocaleTimeString() +
                          ' (' + seconds + 's)';
    if (state.edge) loadResource(state.edge, state.resource, true);
  } catch (error) {
    updated.className = 'error';
    updated.textContent = 'Refresh failed: ' + error.message;
    if (!state.edges) {
      const row = document.createElement('tr');
      const cell = el('td', 'Failed to load: ' + error.message, 'error');
      cell.colSpan = 8;
      row.append(cell);
      edgesBody.replaceChildren(row);
    }
  } finally {
    refreshButton.disabled = false;
    refreshButton.textContent = 'Refresh';
    document.body.classList.remove('busy');
  }
}

refreshButton.onclick = load;
document.addEventListener('keydown', event => {
  if (event.key === 'Escape' && state.edge && event.target.tagName !== 'INPUT') closeDetail();
});
load();
</script>
</body>
</html>
"""
