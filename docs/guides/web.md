# Web dashboard

`nps-ctl web` serves a dashboard for every configured edge. It is read-only
unless started with `--allow-writes`.

```bash
# Single operator
export NPS_WEB_PASSWORD='choose-a-password'
nps-ctl web --username admin --allow-writes
# http://127.0.0.1:8080/
```

The server binds to `127.0.0.1` by default. A non-loopback bind without
credentials is refused unless `--insecure` is passed, and writes are always
refused on a network-reachable bind without authentication. Put TLS in front
of the loopback listener before exposing it; see
[Deployment](#deployment).

## Users and roles

A single operator can use `--username` with `--password` or
`NPS_WEB_PASSWORD`. For more than one user, create a users file and generate
each hash locally:

```bash
nps-ctl util hash-password
# pbkdf2_sha256$260000$...$...
```

```toml
# web-users.toml
[[users]]
name = "admin"
password_hash = "pbkdf2_sha256$260000$...$..."
role = "operator"

[[users]]
name = "viewer"
password_hash = "pbkdf2_sha256$260000$...$..."
role = "viewer"
```

```bash
nps-ctl web --users-file web-users.toml --allow-writes
```

`operator` users can run every action; `viewer` users get the same dashboard
with no action buttons and a read-only server-side check. `hash-password`
reads `NPS_WEB_PASSWORD` or prompts without echo, so the plaintext password
never appears in argv or shell history. Keep the users file at mode `0600`
(the server warns if it is group/other-readable).

Passing both `--users-file` and `--username/--password` is an error.

## Actions

With `--allow-writes`:

| Action | What it does |
| --- | --- |
| Sync edges | Copy missing clients, tunnels and hosts from a source edge to the selected targets. Optionally enable **prune** to delete resources absent from the source. |
| Add client | Create a client on the selected edges with one shared verify key, shown once. |
| Add tunnel / host | Add a tunnel or host mapping for a client (matched by exact remark) on the selected edges. Existing mappings are reported as `exists`. |
| Add edge | Append an entry to `edges.toml`; the running cluster reloads without a restart. |
| Edit / delete | Change a client, tunnel or host on one edge, or delete it. Edits are scoped to the edge and row you opened. |

Every action:

- targets an explicit list of edges (there is no implicit cluster-wide write);
- shows a review step before applying (edits show the item and edge);
- requires a per-process `X-CSRF-Token` and rejects cross-origin, non-JSON and
  oversized bodies;
- runs one at a time (a second request receives `409`);
- reports a result per edge and never redacts the one-time client verify key
  from the action response.

`sync --prune` is the only destructive bulk action. It deletes extras on each
target (tunnels and hosts before clients) and aborts before changing anything
if a selected source fetch fails, so an unreachable source is never treated as
an empty one. The CLI exposes the same behavior as `nps-ctl edge sync --prune`.

## Add edge from the dashboard

The **Add edge** dialog appends a `[[edges]]` entry and reloads the cluster in
place. Fields: name, API URL, auth key (optional), region, SSH host. The auth
key is sent only over the authenticated connection, is never echoed back or
logged, and is written to `edges.toml` (mode preserved). The new edge is
probed on the next overview refresh; if it is unreachable it appears offline
without affecting the others.

## Deployment

`deploy/web` in the repository contains:

- `nps-ctl-web.service` — systemd unit running as `nps-ctl`, with the config
  directory writable for the Add edge action;
- `Caddyfile.nps-admin` — a Caddy site block for `nps-admin.oaklight.top` with
  automatic TLS;
- `web-users.example.toml` — users file template.

Point DNS at the server, install `nps-ctl`, copy `edges.toml` and the users
file to `/etc/nps-ctl`, enable the unit, and add the Caddy block. The
dashboard listens only on loopback; Caddy terminates TLS and reverse-proxies
to it.

## Security notes

- Reads redact client verify keys, tunnel passwords and Basic Auth.
- The dashboard sends `Cache-Control: no-store`, `nosniff`, a strict CSP and
  `X-Frame-Options: DENY`.
- Without an auth configuration, a loopback bind rejects non-loopback `Host`
  headers to defeat DNS rebinding. A non-loopback `--insecure` bind is
  explicitly read-only.
- The server speaks plain HTTP; terminate TLS before exposing it.
