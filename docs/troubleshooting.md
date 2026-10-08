# Troubleshooting

## Common issues

### Connection refused or timeout

**Symptom:** nps-ctl commands fail with connection errors when reaching an edge.

**Solutions:**

1. Verify `api_url` in `edges.toml` is correct and includes the scheme (`https://`).
2. Check that the NPS service is running on the edge server:
    ```bash
    ssh cloud.usa1 "systemctl status Nps"
    ```
3. Confirm the web UI port (default 25412) is reachable. If NPS binds to `127.0.0.1`, ensure your reverse proxy (e.g., Caddy) forwards to it.
4. Check firewall rules — the API port must be open or proxied:
    ```bash
    ssh cloud.usa1 "ufw status | grep 25412"
    ```

### Authentication failed

**Symptom:** API calls return 401 or "auth error" responses.

**Solutions:**

1. Verify `auth_key` in `edges.toml` matches the `auth_key` value in `/etc/nps/conf/nps.conf` on the server.
2. Ensure `auth_crypt_key` in `edges.toml` matches the server's `auth_crypt_key` (exactly 16 characters).
3. For modern API (v0.35.0+), check that `username` and `password` match the server's `web_username` and `web_password`.
4. If using `api_mode = "auto"`, try setting it explicitly to `"legacy"` or `"modern"` to rule out probe failures.

### SSL certificate errors

**Symptom:** Requests fail with SSL/TLS verification errors.

**Solutions:**

- For self-signed certificates during testing, use the `--no-ssl-verify` flag:
    ```bash
    nps-ctl --no-ssl-verify edge status
    ```
- For production, fix the certificate chain on the server. If using Caddy with ACME, verify the domain resolves correctly and ACME challenges succeed.

!!! warning
    `--no-ssl-verify` disables certificate validation entirely. Do not use it in production — fix the underlying certificate issue instead.

### Client not connected

**Symptom:** `client list` shows a client as disconnected, or host mappings return 502 errors.

**Solutions:**

1. Check that the NPC service is running on the client machine:
    ```bash
    nps-ctl client status -c my-server
    ```
    Or directly via SSH:
    ```bash
    ssh my-server "systemctl status Npc"
    ```
2. Verify the bridge ports are open on the edge server's firewall:
    ```bash
    ssh cloud.usa1 "ufw status | grep -E '51234|51235'"
    ```
3. Check NPC logs for connection errors:
    ```bash
    ssh my-server "journalctl -u Npc --no-pager -n 50"
    ```
4. Ensure the client's `vkey` matches what is registered on the edge. Use `client list -e <edge>` to verify.

### Config file not found

**Symptom:** `No configuration file found` error on startup.

**Solutions:**

1. Create the config directory and file:
    ```bash
    mkdir -p ~/.config/nps-ctl
    # Create edges.toml with your edge definitions
    ```
2. Or specify the path explicitly:
    ```bash
    nps-ctl --config /path/to/edges.toml edge status
    ```
3. Check that the file is valid TOML. A common mistake is using `[edges.name]` table syntax instead of the `[[edges]]` array syntax.

### Edge install fails silently

**Symptom:** `edge install` completes without error but NPS is not running.

**Solutions:**

1. Run the install with verbose output to see details:
    ```bash
    nps-ctl edge install -e nps-us -v -y
    ```
2. Verify the binary was deployed:
    ```bash
    ssh cloud.usa1 "which nps && nps --version"
    ```
3. Check the systemd service file exists:
    ```bash
    ssh cloud.usa1 "cat /etc/systemd/system/Nps.service"
    ```
4. Check service logs for startup failures:
    ```bash
    ssh cloud.usa1 "journalctl -u Nps --no-pager -n 30"
    ```

!!! tip
    The install process was improved in nps-ctl v0.7.0 with a fallback systemd service file and hard verification checks. If you are on an older version, upgrade nps-ctl first.

### Host mapping not working

**Symptom:** Domain resolves correctly but returns 502 Bad Gateway or no response.

**Solutions:**

1. Confirm the client is connected on the edge where the host mapping exists:
    ```bash
    nps-ctl client list -e nps-us
    ```
2. Verify DNS resolves to the edge server's IP:
    ```bash
    dig +short app.example.com
    ```
3. Check that the host mapping target is correct (the service must be listening on the specified port on the client machine):
    ```bash
    nps-ctl host list -e nps-us
    ```
4. Test the service locally on the client:
    ```bash
    ssh my-server "curl -s http://127.0.0.1:8080"
    ```
5. If using Caddy in front of NPS, verify the Caddyfile proxies the domain to the NPS HTTP proxy port (default 30080).

## Debug logging

nps-ctl provides two levels of increased verbosity:

```bash
# Verbose — shows API request/response details
nps-ctl -v edge status

# Debug — shows everything including internal state
nps-ctl --debug edge status
```

These flags are global and work with any subcommand. Debug output includes the full HTTP request/response cycle, which is useful for diagnosing API issues.

## FAQ

### Which NPS fork should I use?

Use [djylb/nps](https://github.com/djylb/nps). The original [ehang-io/nps](https://github.com/ehang-io/nps) has been unmaintained since 2021. The djylb fork is actively developed, includes security fixes, and adds features like the modern API (v0.35.0+). nps-ctl is tested against djylb/nps.

### Can I manage both NPS and NPC from nps-ctl?

Yes. The `edge` command group manages NPS server nodes (install, upgrade, reconfig, sync, export). The `client` command group manages NPC clients (install, upgrade, reconfig, status, restart). Both operate over SSH using the `ssh_host` fields in your config files.

### Does nps-ctl work with the original ehang-io/nps?

The legacy API is compatible, so basic operations (listing clients, tunnels, hosts; adding and deleting entries) should work. However, ehang-io/nps is unmaintained and may have unpatched security issues. The modern API fields (`username`, `password`, `platform_token`, `api_mode`) are specific to djylb/nps v0.35.0+.

### How do I generate an auth_key?

Use the built-in utility:

```bash
nps-ctl util generate-auth-key       # 43-character random key
nps-ctl util generate-auth-key 64    # custom length
```

### Can I use nps-ctl with a single edge?

Yes. Define one `[[edges]]` block in `edges.toml` and all commands work the same way. The multi-edge features (sync, broadcast) simply have no additional targets.
