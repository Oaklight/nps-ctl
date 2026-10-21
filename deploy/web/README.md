# Deploying the nps-ctl dashboard

The dashboard is a single Python process on `127.0.0.1:8080`; Caddy terminates
TLS for `nps-admin.oaklight.top` and reverse-proxies to it. Both pieces are
shipped here:

| File | Purpose |
| --- | --- |
| `nps-ctl-web.service` | systemd unit, runs as the `nps-ctl` user |
| `Caddyfile.nps-admin` | Caddy site block with automatic TLS |
| `web-users.example.toml` | users/roles file template |

## Prerequisites

1. DNS: point `nps-admin.oaklight.top` at the server (A/AAAA or CNAME record).
2. `nps-ctl` installed on `PATH` system-wide (for example with
   `uv tool install` or `pipx`; a user-local install is not visible to the
   systemd unit).
3. `/etc/nps-ctl/edges.toml` and, if used, `/etc/nps-ctl/clients.toml`.
   The service user must be able to read and write `edges.toml` (the web
   "Add edge" action appends to it).
4. Caddy installed and running on the server.

## Users

Generate a hash without echoing the password:

```bash
nps-ctl util hash-password
```

Put the result in `/etc/nps-ctl/web-users.toml`:

```toml
[[users]]
name = "admin"
password_hash = "pbkdf2_sha256$260000$...$..."
role = "operator"

[[users]]
name = "viewer"
password_hash = "pbkdf2_sha256$260000$...$..."
role = "viewer"
```

Use `operator` for anyone who may change the cluster and `viewer` for
read-only access. The file contains password hashes, not plaintext; keep it
at mode `0600`.

## Install

```bash
useradd --system --home /var/lib/nps-ctl --shell /usr/sbin/nologin nps-ctl
install -d -o nps-ctl -g nps-ctl -m 0750 /etc/nps-ctl
install -o nps-ctl -g nps-ctl -m 0600 edges.toml /etc/nps-ctl/edges.toml
install -o nps-ctl -g nps-ctl -m 0600 web-users.toml /etc/nps-ctl/web-users.toml

install -m 0644 nps-ctl-web.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now nps-ctl-web
systemctl status nps-ctl-web --no-pager
```

Verify the loopback listener:

```bash
curl -fsS -u admin:YOUR_PASSWORD http://127.0.0.1:8080/api/overview >/dev/null
```

## Caddy

Append the site block to `/etc/caddy/Caddyfile` (or include it from there):

```bash
cat Caddyfile.nps-admin >> /etc/caddy/Caddyfile
caddy validate --config /etc/caddy/Caddyfile
systemctl reload caddy
```

Then open `https://nps-admin.oaklight.top/`. The app already sends CSP,
`X-Frame-Options`, `Cache-Control: no-store`, and `nosniff`; Caddy adds HSTS.

## Updating

```bash
uv tool install --reinstall /path/to/nps-ctl   # or pip install --upgrade nps-ctl
systemctl restart nps-ctl-web
```

The dashboard reloads `edges.toml` in place when an edge is added; a restart
is only needed after upgrading the package or changing the users file.
