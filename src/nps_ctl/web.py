"""Web dashboard for an NPS cluster.

The dashboard is intentionally dependency-free: it uses the standard
library HTTP server and serves one HTML page backed by JSON endpoints.
It is read-only unless started with ``allow_writes``; write endpoints then
require a per-process CSRF token, a same-origin request, and run one at a
time.
"""

from __future__ import annotations

import base64
import binascii
import hmac
import html
import json
import logging
import secrets
import string
import threading
from collections.abc import Callable, Mapping
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import TYPE_CHECKING, Any, cast
from urllib.parse import unquote, urlparse

from . import client_mgmt, host, tunnel
from .config_edit import append_edge
from .exceptions import NPSError
from .status import build_status_payload, collect_cluster_status
from .web_auth import WebUser, users_from_credentials, verify_password

if TYPE_CHECKING:
    from .cluster import NPSCluster

logger = logging.getLogger(__name__)

LOOPBACK_HOSTS = {"127.0.0.1", "::1", "localhost"}
RESOURCES = {"clients", "tunnels", "hosts"}
SENSITIVE_ROW_KEYS = ("VerifyKey", "Password", "WebPassword", "BasicPassword")
MAX_BODY_BYTES = 64 * 1024
WEB_TUNNEL_TYPES = ("tcp", "udp", "socks5", "httpProxy")
SYNC_TYPES = ("clients", "tunnels", "hosts")


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
                "unknown": status.unknown.get(row.edge, []),
                "in_sync": status.in_sync(row.edge),
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
            "in_sync": sum(1 for row in rows if status.in_sync(row.edge)),
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


class ActionError(ValueError):
    """A write request failed validation."""


def _require_str(payload: dict[str, Any], key: str, *, required: bool = True) -> str:
    """Return a stripped string field, enforcing presence when required."""
    value = payload.get(key, "")
    if value is None:
        value = ""
    if not isinstance(value, str):
        raise ActionError(f"'{key}' must be a string")
    value = value.strip()
    if required and not value:
        raise ActionError(f"'{key}' is required")
    return value


def _target_edges(cluster: NPSCluster, payload: dict[str, Any]) -> list[str]:
    """Validate the explicit target edge list; there is no implicit default."""
    edges = payload.get("edges")
    if (
        not isinstance(edges, list)
        or not edges
        or not all(isinstance(name, str) for name in edges)
    ):
        raise ActionError("'edges' must be a non-empty list of edge names")
    unknown = [name for name in edges if name not in cluster.edge_names]
    if unknown:
        raise ActionError(f"Unknown edges: {', '.join(unknown)}")
    return list(dict.fromkeys(cast("list[str]", edges)))


def _per_edge(
    cluster: NPSCluster,
    edges: list[str],
    fn: Callable[[Any], dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Run ``fn`` against each edge client concurrently, in edge order."""

    def run(name: str) -> tuple[str, dict[str, Any]]:
        try:
            return name, fn(cluster.get_client(name))
        except NPSError as e:
            return name, {"ok": False, "error": str(e)}

    with ThreadPoolExecutor(max_workers=min(4, len(edges))) as executor:
        results = dict(executor.map(run, edges))
    return {name: results[name] for name in edges}


def _added(ok: bool) -> dict[str, Any]:
    return (
        {"ok": True, "status": "added"}
        if ok
        else {"ok": False, "error": "rejected by edge"}
    )


def _find_client_id(nps: Any, remark: str) -> int | None:
    """Return the ID of the client whose remark matches exactly."""
    for client in client_mgmt.list_clients(nps, search=remark):
        if client.get("Remark") == remark:
            return client.get("Id")
    return None


def _generate_vkey() -> str:
    alphabet = string.ascii_lowercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(16))


def _action_add_client(cluster: NPSCluster, payload: dict[str, Any]) -> dict[str, Any]:
    """Add a client to the selected edges with one shared verify key."""
    remark = _require_str(payload, "remark")
    vkey = _require_str(payload, "vkey", required=False) or _generate_vkey()
    edges = _target_edges(cluster, payload)

    def add(nps: Any) -> dict[str, Any]:
        if _find_client_id(nps, remark) is not None:
            return {"ok": True, "status": "exists"}
        return _added(client_mgmt.add_client(nps, remark=remark, vkey=vkey))

    results = _per_edge(cluster, edges, add)
    response: dict[str, Any] = {"results": results}
    if any(r.get("status") == "added" for r in results.values()):
        # Shown once so the operator can configure npc; reads stay redacted.
        response["vkey"] = vkey
    return response


def _action_add_tunnel(cluster: NPSCluster, payload: dict[str, Any]) -> dict[str, Any]:
    """Add a tunnel for a client (matched by remark) on the selected edges."""
    client = _require_str(payload, "client")
    tunnel_type = _require_str(payload, "type", required=False) or "tcp"
    if tunnel_type not in WEB_TUNNEL_TYPES:
        raise ActionError(f"'type' must be one of {', '.join(WEB_TUNNEL_TYPES)}")
    port = payload.get("port")
    if not isinstance(port, int) or isinstance(port, bool) or not 1 <= port <= 65535:
        raise ActionError("'port' must be an integer between 1 and 65535")
    target = _require_str(payload, "target", required=tunnel_type in ("tcp", "udp"))
    remark = _require_str(payload, "remark", required=False)
    edges = _target_edges(cluster, payload)

    def add(nps: Any) -> dict[str, Any]:
        client_id = _find_client_id(nps, client)
        if client_id is None:
            return {"ok": False, "error": f"client '{client}' not found"}
        return _added(
            tunnel.add_tunnel(
                nps,
                client_id=client_id,
                tunnel_type=tunnel_type,
                port=port,
                target=target,
                remark=remark,
            )
        )

    return {"results": _per_edge(cluster, edges, add)}


def _action_add_host(cluster: NPSCluster, payload: dict[str, Any]) -> dict[str, Any]:
    """Add a host mapping for a client (matched by remark) on the selected edges."""
    client = _require_str(payload, "client")
    domain = _require_str(payload, "host")
    target = _require_str(payload, "target")
    location = _require_str(payload, "location", required=False)
    remark = _require_str(payload, "remark", required=False)
    edges = _target_edges(cluster, payload)

    def add(nps: Any) -> dict[str, Any]:
        for entry in host.list_hosts(nps, search=domain):
            if entry.get("Host") == domain and (entry.get("Location") or "/") == (
                location or "/"
            ):
                return {"ok": True, "status": "exists"}
        client_id = _find_client_id(nps, client)
        if client_id is None:
            return {"ok": False, "error": f"client '{client}' not found"}
        return _added(
            host.add_host(
                nps,
                client_id=client_id,
                host=domain,
                target=target,
                remark=remark,
                location=location,
            )
        )

    return {"results": _per_edge(cluster, edges, add)}


def _action_sync(cluster: NPSCluster, payload: dict[str, Any]) -> dict[str, Any]:
    """Copy missing resources from a source edge to the selected edges."""
    source = _require_str(payload, "source")
    if source not in cluster.edge_names:
        raise ActionError(f"Unknown source edge: {source}")
    types = payload.get("types", list(SYNC_TYPES))
    if not isinstance(types, list) or not types or not set(types) <= set(SYNC_TYPES):
        raise ActionError(f"'types' must be a subset of {', '.join(SYNC_TYPES)}")
    prune = payload.get("prune", False)
    if not isinstance(prune, bool):
        raise ActionError("'prune' must be a boolean")
    edges = [name for name in _target_edges(cluster, payload) if name != source]
    if not edges:
        raise ActionError("Select at least one target edge besides the source")

    raw = cluster.sync_from(
        source,
        sync_clients="clients" in types,
        sync_tunnels="tunnels" in types,
        sync_hosts="hosts" in types,
        target_edges=edges,
        quiet=True,
        prune=prune,
    )
    results: dict[str, dict[str, Any]] = {}
    for name in edges:
        ops = raw.get(name)
        if ops is None:
            results[name] = {"ok": False, "error": "no result"}
        elif "_edge_failed" in ops:
            results[name] = {"ok": False, "error": "edge failed"}
        else:
            failed = sorted(op for op, ok in ops.items() if ok is False)
            results[name] = {
                "ok": not failed,
                "status": f"{len(ops)} checked",
                "failed": failed,
            }
    return {"source": source, "prune": prune, "results": results}


def _action_add_edge(cluster: NPSCluster, payload: dict[str, Any]) -> dict[str, Any]:
    """Append an edge to edges.toml and reload the cluster in place."""
    name = _require_str(payload, "name")
    api_url = _require_str(payload, "api_url").rstrip("/")
    parts = urlparse(api_url)
    if parts.scheme not in ("http", "https") or not parts.netloc:
        raise ActionError("'api_url' must be an http(s) URL")
    if name in cluster.edge_names:
        raise ActionError(f"Edge '{name}' already exists")
    if not getattr(cluster, "config_path", None):
        raise ActionError("This cluster has no edges.toml path")
    try:
        append_edge(
            cluster.config_path,
            name=name,
            api_url=api_url,
            auth_key=_require_str(payload, "auth_key", required=False),
            region=_require_str(payload, "region", required=False),
            ssh_host=_require_str(payload, "ssh_host", required=False),
        )
    except ValueError as e:
        raise ActionError(str(e)) from e
    except OSError as e:
        raise ActionError(f"Could not write edges.toml: {e}") from e

    # Pick up the new edge without a restart. If this fails the file is still
    # valid (append_edge re-parses it), so report the failure rather than
    # pretending the dashboard can see the edge.
    try:
        cluster.reload()
    except Exception as e:
        raise ActionError(
            f"Edge was added to edges.toml but the cluster could not reload: {e}"
        ) from e

    return {
        "results": {name: {"ok": True, "status": "added"}},
        "edge": name,
    }


def _single_edge(cluster: NPSCluster, payload: dict[str, Any]) -> tuple[str, Any]:
    """Resolve the single edge named by a per-row mutation payload."""
    edge = _require_str(payload, "edge")
    nps = cluster.get_client(edge)
    if nps is None:
        raise ActionError(f"Unknown edge: {edge}")
    return edge, nps


def _require_id(payload: dict[str, Any]) -> int:
    """Return a positive integer resource ID."""
    value = payload.get("id")
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise ActionError("'id' must be a positive integer")
    return value


def _mutation_result(edge: str, item_id: int, ok: bool, status: str) -> dict[str, Any]:
    if not ok:
        return {"results": {edge: {"ok": False, "error": "rejected by edge"}}}
    return {"results": {edge: {"ok": True, "status": status}}, "id": item_id}


def _optional(payload: dict[str, Any], key: str, current: str = "") -> str:
    """Return a stripped optional string, falling back to ``current``."""
    value = payload.get(key)
    if value is None:
        return current
    if not isinstance(value, str):
        raise ActionError(f"'{key}' must be a string")
    return value.strip()


def _action_edit_client(cluster: NPSCluster, payload: dict[str, Any]) -> dict[str, Any]:
    """Edit a client's remark or verify key on one edge."""
    edge, nps = _single_edge(cluster, payload)
    client_id = _require_id(payload)
    current = client_mgmt.get_client(nps, client_id)
    if current is None:
        raise ActionError(f"client {client_id} not found on {edge}")
    cnf = current.get("Cnf") or {}
    ok = client_mgmt.edit_client(
        nps,
        client_id,
        remark=_optional(payload, "remark", "") or current.get("Remark", ""),
        vkey=_optional(payload, "vkey", "") or current.get("VerifyKey", ""),
        basic_username=cnf.get("U", "") or "",
        basic_password=cnf.get("P", "") or "",
        rate_limit=int(current.get("RateLimit", 0) or 0),
        max_conn=int(current.get("MaxConn", 0) or 0),
        web_username=current.get("WebUserName", "") or "",
        web_password=current.get("WebPassword", "") or "",
    )
    return _mutation_result(edge, client_id, ok, "updated")


def _action_delete_client(
    cluster: NPSCluster, payload: dict[str, Any]
) -> dict[str, Any]:
    """Delete a client on one edge."""
    edge, nps = _single_edge(cluster, payload)
    client_id = _require_id(payload)
    if client_mgmt.get_client(nps, client_id) is None:
        raise ActionError(f"client {client_id} not found on {edge}")
    ok = client_mgmt.del_client(nps, client_id)
    return _mutation_result(edge, client_id, ok, "deleted")


def _action_edit_tunnel(cluster: NPSCluster, payload: dict[str, Any]) -> dict[str, Any]:
    """Edit a tunnel's remark, port, target or type on one edge."""
    edge, nps = _single_edge(cluster, payload)
    tunnel_id = _require_id(payload)
    current = tunnel.get_tunnel(nps, tunnel_id)
    if current is None:
        raise ActionError(f"tunnel {tunnel_id} not found on {edge}")

    tunnel_type = _optional(payload, "mode", current.get("Mode", "tcp")) or "tcp"
    if tunnel_type not in WEB_TUNNEL_TYPES and tunnel_type != tunnel.MIX_PROXY:
        raise ActionError(f"'mode' must be one of {', '.join(WEB_TUNNEL_TYPES)}")
    port_value = payload.get("port", current.get("Port", 0))
    if not isinstance(port_value, int) or isinstance(port_value, bool):
        raise ActionError("'port' must be an integer between 1 and 65535")
    # A tunnel without a listen port can still be edited; keep its current 0
    # instead of forcing the operator to invent one.
    if port_value == 0 and current.get("Port", 0) == 0:
        pass
    elif not 1 <= port_value <= 65535:
        raise ActionError("'port' must be an integer between 1 and 65535")
    target = _optional(
        payload, "target", (current.get("Target") or {}).get("TargetStr", "")
    )
    if tunnel_type in ("tcp", "udp") and not target:
        raise ActionError("'target' is required for tcp/udp tunnels")
    user_auth = current.get("UserAuth") or {}
    ok = tunnel.edit_tunnel(
        nps,
        tunnel_id,
        client_id=(current.get("Client") or {}).get("Id", 0),
        tunnel_type=tunnel_type,
        port=port_value,
        target=target,
        remark=_optional(payload, "remark", current.get("Remark", "")),
        password=current.get("Password", "") or "",
        auth=user_auth.get("Content", "") or "",
        enable_socks5=current.get("Socks5Proxy") if tunnel_type == "mixProxy" else None,
        enable_http=current.get("HttpProxy") if tunnel_type == "mixProxy" else None,
    )
    return _mutation_result(edge, tunnel_id, ok, "updated")


def _action_delete_tunnel(
    cluster: NPSCluster, payload: dict[str, Any]
) -> dict[str, Any]:
    """Delete a tunnel on one edge."""
    edge, nps = _single_edge(cluster, payload)
    tunnel_id = _require_id(payload)
    if tunnel.get_tunnel(nps, tunnel_id) is None:
        raise ActionError(f"tunnel {tunnel_id} not found on {edge}")
    ok = tunnel.del_tunnel(nps, tunnel_id)
    return _mutation_result(edge, tunnel_id, ok, "deleted")


def _action_edit_host(cluster: NPSCluster, payload: dict[str, Any]) -> dict[str, Any]:
    """Edit a host mapping's domain, target, location or remark on one edge."""
    edge, nps = _single_edge(cluster, payload)
    host_id = _require_id(payload)
    current = host.get_host(nps, host_id)
    if current is None:
        raise ActionError(f"host {host_id} not found on {edge}")
    domain = _optional(payload, "host", current.get("Host", ""))
    if not domain:
        raise ActionError("'host' is required")
    target = _optional(
        payload, "target", (current.get("Target") or {}).get("TargetStr", "")
    )
    if not target:
        raise ActionError("'target' is required")
    scheme = _optional(payload, "scheme", current.get("Scheme", "all")) or "all"
    if scheme not in ("http", "https", "all"):
        raise ActionError("'scheme' must be one of http, https, all")
    user_auth = current.get("UserAuth") or {}
    ok = host.edit_host(
        nps,
        host_id,
        client_id=(current.get("Client") or {}).get("Id", 0),
        host=domain,
        target=target,
        remark=_optional(payload, "remark", current.get("Remark", "")),
        location=_optional(payload, "location", current.get("Location", "")),
        scheme=scheme,
        header_change=current.get("HeaderChange", "") or "",
        host_change=current.get("HostChange", "") or "",
        auth=user_auth.get("Content", "") or "",
    )
    return _mutation_result(edge, host_id, ok, "updated")


def _action_delete_host(cluster: NPSCluster, payload: dict[str, Any]) -> dict[str, Any]:
    """Delete a host mapping on one edge."""
    edge, nps = _single_edge(cluster, payload)
    host_id = _require_id(payload)
    if host.get_host(nps, host_id) is None:
        raise ActionError(f"host {host_id} not found on {edge}")
    ok = host.del_host(nps, host_id)
    return _mutation_result(edge, host_id, ok, "deleted")


ACTIONS: dict[str, Callable[[Any, dict[str, Any]], dict[str, Any]]] = {
    "/api/actions/sync": _action_sync,
    "/api/actions/edges": _action_add_edge,
    "/api/actions/clients": _action_add_client,
    "/api/actions/clients/edit": _action_edit_client,
    "/api/actions/clients/delete": _action_delete_client,
    "/api/actions/tunnels": _action_add_tunnel,
    "/api/actions/tunnels/edit": _action_edit_tunnel,
    "/api/actions/tunnels/delete": _action_delete_tunnel,
    "/api/actions/hosts": _action_add_host,
    "/api/actions/hosts/edit": _action_edit_host,
    "/api/actions/hosts/delete": _action_delete_host,
}


def _render_dashboard(server: AdminServer, user: WebUser | None = None) -> str:
    """Return the dashboard HTML with this server's client config embedded."""
    can_write = server.allow_writes and (user is None or user.can_write)
    config = {
        "writes": can_write,
        "csrf": server.csrf_token if can_write else "",
        "primary": getattr(server.cluster, "primary_edge", None),
        "role": user.role if user else "operator",
        "user": user.name if user else None,
    }
    return _DASHBOARD_HTML.replace(
        "__NPS_CONFIG__", html.escape(json.dumps(config), quote=True)
    )


class _AdminHandler(BaseHTTPRequestHandler):
    """HTTP handler for the dashboard and its JSON API."""

    server_version = "nps-ctl-web"

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        if not self._check_host():
            return
        ok, user = self._check_auth()
        if not ok:
            return

        path = urlparse(self.path).path.rstrip("/") or "/"
        try:
            if path == "/":
                self._send_html(
                    _render_dashboard(cast("AdminServer", self.server), user)
                )
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

    def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        if not self._check_host():
            return
        ok, user = self._check_auth()
        if not ok:
            return
        server = cast("AdminServer", self.server)
        path = urlparse(self.path).path.rstrip("/")
        action = ACTIONS.get(path)
        if action is None:
            self._send_json({"error": "Not found"}, status=404)
            return
        if not server.allow_writes:
            self._send_json(
                {"error": "Writes are disabled; restart with --allow-writes"},
                status=403,
            )
            return
        if user is not None and not user.can_write:
            self._send_json(
                {"error": "Read-only role: viewers cannot change the cluster"},
                status=403,
            )
            return
        token = self.headers.get("X-CSRF-Token", "")
        if not hmac.compare_digest(
            token.encode("utf-8"), server.csrf_token.encode("utf-8")
        ):
            self._send_json({"error": "Missing or invalid CSRF token"}, status=403)
            return
        origin = self.headers.get("Origin")
        if origin and urlparse(origin).netloc != self.headers.get("Host", ""):
            self._send_json({"error": "Cross-origin request rejected"}, status=403)
            return
        content_type = self.headers.get("Content-Type", "").split(";")[0].strip()
        if content_type != "application/json":
            self._send_json({"error": "Expected application/json"}, status=415)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = -1
        if not 0 <= length <= MAX_BODY_BYTES:
            self._send_json({"error": "Invalid request size"}, status=413)
            return
        try:
            payload = json.loads(self.rfile.read(length) or b"{}")
        except (ValueError, UnicodeDecodeError):
            payload = None
        if not isinstance(payload, dict):
            self._send_json({"error": "Body must be a JSON object"}, status=400)
            return

        if not server.write_lock.acquire(blocking=False):
            self._send_json({"error": "Another change is in progress"}, status=409)
            return
        try:
            result = action(server.cluster, payload)
        except ActionError as e:
            self._send_json({"error": str(e)}, status=400)
            return
        except NPSError as e:
            self._send_json({"error": str(e)}, status=502)
            return
        except Exception:
            logger.exception("Dashboard action failed: %s", path)
            self._send_json({"error": "Internal server error"}, status=500)
            return
        finally:
            server.write_lock.release()
        logger.info("Dashboard action %s: %s", path, json.dumps(result.get("results")))
        self._send_json(result)

    def _check_host(self) -> bool:
        """Reject non-loopback Host headers when no auth is configured.

        Without Basic Auth the only gate is the loopback bind, which a DNS
        rebinding page defeats: the browser sends ``Host: evil.example`` to
        127.0.0.1, so ``Origin`` matches ``Host`` and the page can read the
        CSRF token. Pinning ``Host`` to loopback names closes that.

        A non-loopback bind without auth is the explicit ``--insecure`` mode:
        writes are refused there, and the operator has already accepted
        unauthenticated network access, so Host pinning would only break the
        documented remote read-only dashboard.
        """
        if getattr(self.server, "users", None):
            return True
        if getattr(self.server, "bind_host", "127.0.0.1") not in LOOPBACK_HOSTS:
            return True
        host = urlparse("//" + (self.headers.get("Host") or "")).hostname or ""
        if host in LOOPBACK_HOSTS:
            return True
        self._send_json({"error": "Host not allowed"}, status=403)
        return False

    def _check_auth(self) -> tuple[bool, WebUser | None]:
        """Validate Basic Auth, returning the authenticated user.

        Returns:
            ``(True, user)`` on success (``user`` is None when authentication
            is disabled), or ``(False, None)`` after sending a 401.
        """
        users: Mapping[str, WebUser] = getattr(self.server, "users", {})
        if not users:
            return True, None
        supplied = self.headers.get("Authorization", "")
        if supplied.startswith("Basic "):
            try:
                decoded = base64.b64decode(supplied[6:], validate=True).decode("utf-8")
                username, _, password = decoded.partition(":")
            except (binascii.Error, UnicodeDecodeError, ValueError):
                username = password = ""
            user = users.get(username)
            if user is not None:
                valid = verify_password(password, user.password_hash)
            else:
                # Spend the same PBKDF2 work for an unknown username so the
                # response time cannot be used to enumerate accounts.
                verify_password(password, next(iter(users.values())).password_hash)
                valid = False
            if valid:
                return True, user
        self.send_response(401)
        self.send_header("WWW-Authenticate", 'Basic realm="nps-ctl"')
        self.send_header("Content-Length", "0")
        self._common_headers()
        self.end_headers()
        return False, None

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
            "style-src 'unsafe-inline'; connect-src 'self'; frame-ancestors 'none'",
        )
        self.send_header("X-Frame-Options", "DENY")

    def log_message(self, format: str, *args: Any) -> None:
        logger.info("%s - %s", self.address_string(), format % args)


class AdminServer(ThreadingHTTPServer):
    """HTTP server carrying the cluster, dashboard users, and write settings."""

    daemon_threads = True

    def __init__(
        self,
        address: tuple[str, int],
        cluster: NPSCluster,
        users: Mapping[str, WebUser] | None = None,
        allow_writes: bool = False,
    ) -> None:
        super().__init__(address, _AdminHandler)
        self.cluster = cluster
        self.bind_host = address[0]
        self.users = dict(users or {})
        self.allow_writes = allow_writes
        self.csrf_token = secrets.token_urlsafe(32)
        self.write_lock = threading.Lock()


def create_server(
    cluster: NPSCluster,
    host: str = "127.0.0.1",
    port: int = 8080,
    username: str = "",
    password: str = "",
    *,
    users: Mapping[str, WebUser] | None = None,
    allow_insecure: bool = False,
    allow_writes: bool = False,
) -> AdminServer:
    """Create the dashboard server.

    Args:
        cluster: NPSCluster instance.
        host: Bind address.
        port: Bind port (0 chooses an ephemeral port).
        username: Optional single-user Basic Auth username.
        password: Optional single-user Basic Auth password.
        users: Optional multi-user mapping, e.g. from ``load_users_file``.
            Mutually exclusive with ``username``/``password``.
        allow_insecure: Allow a non-loopback bind without authentication.
        allow_writes: Enable the write endpoints (add/sync/edit/delete).

    Returns:
        A configured, not-yet-serving AdminServer.

    Raises:
        ValueError: If credentials are contradictory, a username has no
            password, or a non-loopback bind has no authentication and
            ``allow_insecure`` is false.
    """
    if users and (username or password):
        raise ValueError("Pass either --users-file or --username/--password, not both")
    if username and not password:
        raise ValueError("Basic Auth username requires a non-empty password")
    if username and password:
        users = users_from_credentials(username, password)
    authenticated = bool(users)
    if host not in LOOPBACK_HOSTS and not authenticated and not allow_insecure:
        raise ValueError(
            "Refusing to expose the dashboard without authentication; "
            "set --username/--password or --users-file, or pass --insecure"
        )
    if allow_writes and host not in LOOPBACK_HOSTS and not authenticated:
        raise ValueError(
            "Refusing to enable writes on a network-reachable dashboard "
            "without authentication"
        )
    return AdminServer(
        (host, port),
        cluster,
        users=users,
        allow_writes=allow_writes,
    )


_DASHBOARD_HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="nps-config" content="__NPS_CONFIG__">
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
  #actions { display: flex; gap: 6px; flex-wrap: wrap; }
  dialog { border: 1px solid var(--line); border-radius: 10px; padding: 20px;
           width: min(520px, calc(100vw - 32px)); background: var(--card);
           color: var(--fg); }
  dialog::backdrop { background: rgba(0, 0, 0, 0.45); }
  dialog h2 { margin-bottom: 8px; }
  dialog fieldset { border: 0; padding: 0; margin: 0; min-width: 0; }
  .field { display: flex; flex-direction: column; gap: 4px; margin: 10px 0; }
  .field > span { font-size: 12px; color: var(--muted); }
  .field input, .field select { font: inherit; padding: 5px 8px; color: var(--fg);
                                background: var(--bg); border: 1px solid var(--line);
                                border-radius: 6px; }
  .checks { display: flex; flex-wrap: wrap; gap: 4px 14px; margin: 10px 0; }
  .checks legend { font-size: 12px; color: var(--muted); padding: 0; margin-bottom: 4px; }
  .message { margin: 10px 0; }
  .message.warn, p.warn { color: var(--warn); }
  .results { list-style: none; padding: 0; margin: 0; }
  .results li { padding: 4px 0; }
  .dialog-buttons { display: flex; justify-content: flex-end; gap: 8px; margin-top: 16px; }
  button.primary { background: var(--accent); border-color: var(--accent); color: #ffffff; }
  button.danger { background: var(--bad); border-color: var(--bad); color: #ffffff; }
  @media (max-width: 640px) { body { padding: 16px; } }
</style>
</head>
<body>
<main>
<header>
  <h1>NPS Cluster</h1>
  <div id="actions" aria-label="Cluster actions"></div>
  <span id="mode"></span>
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
<dialog id="action-dialog" aria-label="Cluster action"></dialog>
<script>
const summary = document.getElementById('summary');
const edgesBody = document.getElementById('edges');
const detail = document.getElementById('detail');
const refreshButton = document.getElementById('refresh');
const updated = document.getElementById('updated');
const RESOURCES = ['clients', 'tunnels', 'hosts'];
const state = { edges: null, edge: null, resource: null, items: [], filter: '' };
const config = (() => {
  try {
    return JSON.parse(document.querySelector('meta[name="nps-config"]').content);
  } catch (error) {
    return { writes: false, csrf: '', primary: null };
  }
})();
const actionsBar = document.getElementById('actions');
const dialog = document.getElementById('action-dialog');
const canWrite = !!config.writes;

const ACTIONS = {
  sync: {
    label: 'Sync edges', url: 'api/actions/sync', excludeSource: true,
    intro: 'Copy clients, tunnels and hosts that are missing on the selected ' +
           'edges from the source edge. Nothing is overwritten unless prune ' +
           'is checked, which deletes resources absent from the source.',
    fields: [
      { name: 'source', label: 'Source edge', kind: 'source' },
      { name: 'types', label: 'Copy', kind: 'types' },
      { name: 'prune', label: 'Delete extras (prune)', kind: 'bool' },
    ],
  },
  clients: {
    label: 'Add client', url: 'api/actions/clients',
    intro: 'Create a client on the selected edges with one shared verify key.',
    fields: [
      { name: 'remark', label: 'Remark (client name)', required: true },
      { name: 'vkey', label: 'Verify key (blank to generate)' },
    ],
  },
  edges: {
    label: 'Add edge', url: 'api/actions/edges', targets: false,
    intro: 'Append an edge to edges.toml. The dashboard reloads the cluster; ' +
           'the new edge is checked on the next refresh.',
    fields: [
      { name: 'name', label: 'Edge name', required: true },
      { name: 'api_url', label: 'API URL (https://…)', required: true },
      { name: 'auth_key', label: 'API auth key', type: 'password' },
      { name: 'region', label: 'Region' },
      { name: 'ssh_host', label: 'SSH host' },
    ],
  },
  tunnels: {
    label: 'Add tunnel', url: 'api/actions/tunnels',
    intro: 'Add a tunnel for an existing client on the selected edges.',
    fields: [
      { name: 'client', label: 'Client remark', required: true },
      { name: 'type', label: 'Type', options: ['tcp', 'udp', 'socks5', 'httpProxy'] },
      { name: 'port', label: 'Server port', type: 'number', required: true },
      { name: 'target', label: 'Target (host:port, required for tcp/udp)' },
      { name: 'remark', label: 'Remark' },
    ],
  },
  hosts: {
    label: 'Add host', url: 'api/actions/hosts',
    intro: 'Map a domain to an existing client on the selected edges.',
    fields: [
      { name: 'host', label: 'Domain', required: true },
      { name: 'client', label: 'Client remark', required: true },
      { name: 'target', label: 'Target (host:port)', required: true },
      { name: 'location', label: 'Location (path prefix)' },
      { name: 'remark', label: 'Remark' },
    ],
  },
};

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
  const unknown = edge.unknown || [];
  const gaps = Object.entries(missing).filter(entry => entry[1] > 0);
  if (gaps.length) {
    cell.append(badge('drift', 'warn'));
    cell.append(el('div', 'missing ' + gaps.map(e => e[1] + ' ' + e[0]).join(', '), 'sub'));
  } else if (edge.in_sync) {
    cell.append(badge('in sync', 'ok'));
  } else {
    cell.append(el('span', '—', 'muted'));
  }
  if (unknown.length) cell.append(el('div', 'unknown: ' + unknown.join(', '), 'sub'));
  return cell;
}

function renderEdges(edges) {
  if (!edges) return;
  edgesBody.replaceChildren();
  for (const edge of edges) {
    const row = document.createElement('tr');
    if (edge.name === state.edge) row.className = 'selected';
    const nameCell = el('td', edge.name, 'mono name');
    if (edge.name === config.primary) nameCell.append(' ', badge('primary', 'muted'));
    row.append(nameCell, el('td', edge.region || '—'));
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
  const span = columns.length + (canWrite ? 1 : 0);
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
    if (canWrite) {
      const actions = el('td');
      const chips = el('div', undefined, 'chips');
      const edit = el('button', 'Edit');
      edit.type = 'button';
      edit.onclick = event => { event.stopPropagation(); openMutation('edit', item); };
      const remove = el('button', 'Delete');
      remove.type = 'button';
      remove.onclick = event => { event.stopPropagation(); openMutation('delete', item); };
      chips.append(edit, remove);
      actions.append(chips);
      row.append(actions);
    }
    const raw = el('tr', undefined, 'raw');
    raw.hidden = true;
    const toggle = () => {
      const open = raw.hidden;
      if (open && !raw.firstChild) {
        const cell = el('td');
        cell.colSpan = span;
        cell.append(el('pre', JSON.stringify(item, null, 2), 'mono'));
        raw.append(cell);
      }
      raw.hidden = !open;
      row.classList.toggle('open', open);
      row.setAttribute('aria-expanded', String(open));
    };
    row.onclick = toggle;
    row.onkeydown = event => {
      if (event.target !== row) return;
      if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); toggle(); }
    };
    tbody.append(row, raw);
  }
  count.textContent = needle ? shown + ' of ' + state.items.length
                             : state.items.length + ' total';
  if (!shown) {
    const row = document.createElement('tr');
    const cell = el('td', needle ? 'No matches.' : 'No ' + state.resource + '.', 'empty');
    cell.colSpan = span;
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
    if (canWrite) head.append(el('th', 'Actions'));
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
    enableActions();
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
  if (event.key === 'Escape' && state.edge && !dialog.open &&
      event.target.tagName !== 'INPUT') closeDetail();
});
function edgeNames() { return (state.edges || []).map(edge => edge.name); }

function checkbox(name, value, text, checked = true) {
  const box = el('label');
  const check = el('input');
  check.type = 'checkbox';
  check.name = name;
  check.value = value;
  check.checked = checked;
  box.append(check, ' ' + text);
  return box;
}

function field(spec) {
  if (spec.kind === 'types') {
    const group = el('fieldset', undefined, 'checks');
    group.append(el('legend', spec.label));
    for (const type of RESOURCES) group.append(checkbox('types', type, type));
    return group;
  }
  if (spec.kind === 'bool') {
    const group = el('fieldset', undefined, 'checks');
    group.append(checkbox(spec.name, 'true', spec.label, false));
    return group;
  }
  const wrap = el('label', undefined, 'field');
  wrap.append(el('span', spec.label + (spec.required ? ' *' : '')));
  let input;
  if (spec.kind === 'source' || spec.options) {
    input = el('select');
    const values = spec.kind === 'source' ? edgeNames() : spec.options;
    for (const value of values) {
      const label = spec.kind === 'source' && value === config.primary
        ? value + ' (primary)' : value;
      const option = el('option', label);
      option.value = value;
      input.append(option);
    }
    if (spec.kind === 'source' && config.primary) input.value = config.primary;
  } else {
    input = el('input');
    input.type = spec.type || 'text';
    if (spec.type === 'number') { input.min = '1'; input.max = '65535'; }
  }
  input.name = spec.name;
  if (spec.value !== undefined && spec.value !== null) input.value = spec.value;
  input.required = !!spec.required;
  wrap.append(input);
  return wrap;
}

function collect(form, spec) {
  const data = new FormData(form);
  const payload = {};
  for (const f of spec.fields) {
    if (f.kind === 'types') payload.types = data.getAll('types');
    else if (f.kind === 'bool') payload[f.name] = data.get(f.name) === 'true';
    else if (f.type === 'number') payload[f.name] = Number(data.get(f.name));
    else payload[f.name] = String(data.get(f.name) || '').trim();
  }
  let edges = data.getAll('edges');
  if (spec.excludeSource) edges = edges.filter(name => name !== payload.source);
  if (spec.targets !== false) payload.edges = edges;
  return payload;
}

function renderResults(result) {
  const box = el('div');
  const list = el('ul', undefined, 'results');
  for (const [name, r] of Object.entries(result.results || {})) {
    const item = el('li');
    item.append(el('span', name, 'mono'), ' ',
                r.ok ? badge(r.status || 'ok', 'ok') : badge('failed', 'bad'));
    const extra = r.error || (r.failed && r.failed.length
      ? 'failed: ' + r.failed.join(', ') : '');
    if (extra) item.append(' ', el('span', extra, r.ok ? 'muted' : 'error'));
    list.append(item);
  }
  box.append(list);
  if (result.vkey) {
    const note = el('p', 'Verify key (shown once; configure npc with it): ', 'warn');
    note.append(el('code', result.vkey, 'mono'));
    box.append(note);
  }
  return box;
}

async function postAction(url, payload) {
  const response = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': config.csrf },
    body: JSON.stringify(payload),
  });
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || response.statusText);
  return result;
}

function mutationLabel(resource, item) {
  if (resource === 'clients') return item.Remark || ('client ' + item.Id);
  if (resource === 'tunnels') return item.Remark || ('tunnel ' + item.Id);
  return item.Host || ('host ' + item.Id);
}

function mutationFields(resource, item) {
  if (resource === 'clients') {
    return [
      { name: 'remark', label: 'Remark', value: item.Remark || '' },
      { name: 'vkey', label: 'Verify key (blank keeps current)', value: '' },
    ];
  }
  if (resource === 'tunnels') {
    return [
      { name: 'remark', label: 'Remark', value: item.Remark || '' },
      { name: 'port', label: 'Server port', type: 'number', value: item.Port || '' },
      { name: 'target', label: 'Target (host:port)', value: target(item.Target) },
    ];
  }
  return [
    { name: 'host', label: 'Domain', value: item.Host || '', required: true },
    { name: 'target', label: 'Target (host:port)', value: target(item.Target), required: true },
    { name: 'location', label: 'Location (path prefix)', value: item.Location || '' },
    { name: 'remark', label: 'Remark', value: item.Remark || '' },
    { name: 'scheme', label: 'Scheme', options: ['all', 'http', 'https'],
      value: item.Scheme || 'all' },
  ];
}

function openMutation(kind, item) {
  const resource = state.resource;
  const edge = state.edge;
  const id = item.Id;
  const label = mutationLabel(resource, item);
  const noun = resource.slice(0, -1);
  const specs = kind === 'edit' ? mutationFields(resource, item) : [];
  const form = el('form');
  const fields = el('fieldset');
  fields.append(el('h2', (kind === 'delete' ? 'Delete ' : 'Edit ') + noun));
  fields.append(el('p', edge + ' / ' + label, 'mono'));
  for (const spec of specs) fields.append(field(spec));
  if (kind === 'delete') fields.append(el('p', 'This cannot be undone.', 'error'));
  const message = el('div', '', 'message');
  message.setAttribute('aria-live', 'polite');
  const cancel = el('button', 'Cancel');
  cancel.type = 'button';
  cancel.onclick = () => dialog.close();
  const submit = el('button', kind === 'delete' ? 'Delete' : 'Review',
                     kind === 'delete' ? 'danger' : 'primary');
  submit.type = 'submit';
  const buttons = el('div', undefined, 'dialog-buttons');
  buttons.append(cancel, submit);
  form.append(fields, message, buttons);

  let confirming = false;
  form.oninput = () => {
    if (!confirming) return;
    confirming = false;
    submit.textContent = 'Review';
    submit.className = 'primary';
    message.className = 'message';
    message.textContent = '';
  };
  form.onsubmit = async event => {
    event.preventDefault();
    const payload = { edge: edge, id: id };
    if (kind === 'edit') {
      const data = new FormData(form);
      for (const spec of specs) {
        payload[spec.name] = spec.type === 'number'
          ? Number(data.get(spec.name))
          : String(data.get(spec.name) || '').trim();
      }
    }
    if (!confirming) {
      confirming = true;
      message.className = 'message warn';
      message.textContent = kind === 'delete'
        ? 'This will permanently delete ' + label + ' from ' + edge + '.'
        : 'This will update ' + label + ' on ' + edge + '.';
      submit.textContent = kind === 'delete' ? 'Delete permanently' : 'Apply';
      submit.className = 'danger';
      return;
    }
    fields.disabled = true;
    submit.disabled = true;
    cancel.disabled = true;
    submit.textContent = 'Applying…';
    message.className = 'message muted';
    message.textContent = 'Applying…';
    try {
      await postAction('api/actions/' + resource + '/' + kind, payload);
      dialog.close();
      load();
    } catch (error) {
      message.className = 'message error';
      message.textContent = 'Failed: ' + error.message;
      fields.disabled = false;
      submit.disabled = false;
      cancel.disabled = false;
      confirming = false;
      submit.textContent = kind === 'delete' ? 'Delete' : 'Review';
      submit.className = kind === 'delete' ? 'danger' : 'primary';
    }
  };
  dialog.replaceChildren(form);
  dialog.showModal();
  const first = form.querySelector('input, select');
  if (first) first.focus();
}

function openAction(key) {
  const spec = ACTIONS[key];
  const form = el('form');
  const fields = el('fieldset');
  fields.append(el('p', spec.intro, 'muted'));
  for (const f of spec.fields) fields.append(field(f));
  if (spec.targets !== false) {
    const targets = el('fieldset', undefined, 'checks');
    targets.append(el('legend', 'Target edges'));
    for (const name of edgeNames()) targets.append(checkbox('edges', name, name));
    fields.append(targets);
  }
  const message = el('div', '', 'message');
  message.setAttribute('aria-live', 'polite');
  const cancel = el('button', 'Cancel');
  cancel.type = 'button';
  cancel.onclick = () => dialog.close();
  const submit = el('button', 'Review', 'primary');
  submit.type = 'submit';
  const buttons = el('div', undefined, 'dialog-buttons');
  buttons.append(cancel, submit);
  form.append(el('h2', spec.label), fields, message, buttons);

  let confirming = false;
  const resetReview = () => {
    confirming = false;
    submit.textContent = 'Review';
    submit.className = 'primary';
  };
  form.oninput = () => {
    if (!confirming) return;
    resetReview();
    message.className = 'message';
    message.textContent = '';
  };
  form.onsubmit = async event => {
    event.preventDefault();
    const payload = collect(form, spec);
    if (!payload.edges?.length && spec.targets !== false) {
      message.className = 'message error';
      message.textContent = 'Select at least one target edge.';
      return;
    }
    if (payload.types && !payload.types.length) {
      message.className = 'message error';
      message.textContent = 'Select at least one resource type to copy.';
      return;
    }
    if (!confirming) {
      confirming = true;
      message.className = 'message warn';
      if (spec.targets === false) {
        message.textContent = 'This will add edge ' + payload.name +
                              ' to edges.toml.';
        submit.textContent = 'Add edge';
      } else {
        const count = payload.edges.length;
        message.textContent = (payload.prune ? 'This will change and prune '
                                             : 'This will change ') +
          count + ' edge' + (count === 1 ? '' : 's') + ': ' +
          payload.edges.join(', ') + '.';
        submit.textContent = (payload.prune ? 'Apply and prune '
                                            : 'Apply to ') +
          count + ' edge' + (count === 1 ? '' : 's');
      }
      submit.className = 'danger';
      return;
    }
    fields.disabled = true;
    submit.disabled = true;
    cancel.disabled = true;
    submit.textContent = 'Applying…';
    message.className = 'message muted';
    message.textContent = 'Applying…';
    try {
      const response = await fetch(spec.url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': config.csrf },
        body: JSON.stringify(payload),
      });
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || response.statusText);
      message.className = 'message';
      message.replaceChildren(renderResults(result));
      submit.hidden = true;
      cancel.textContent = 'Close';
      cancel.disabled = false;
      load();
    } catch (error) {
      message.className = 'message error';
      message.textContent = 'Failed: ' + error.message;
      fields.disabled = false;
      submit.disabled = false;
      cancel.disabled = false;
      resetReview();
    }
  };
  dialog.replaceChildren(form);
  dialog.showModal();
  const first = form.querySelector('input:not([type=checkbox]), select');
  if (first) first.focus();
}

function renderActions() {
  const mode = document.getElementById('mode');
  if (!config.writes) {
    mode.replaceChildren(badge('read-only', 'muted'));
    mode.title = 'Start nps-ctl web with --allow-writes to enable actions';
    return;
  }
  for (const [key, spec] of Object.entries(ACTIONS)) {
    const button = el('button', spec.label);
    button.type = 'button';
    button.disabled = true;
    button.onclick = () => openAction(key);
    actionsBar.append(button);
  }
}

function enableActions() {
  for (const button of actionsBar.querySelectorAll('button')) button.disabled = false;
}

renderActions();
load();
</script>
</body>
</html>
"""
