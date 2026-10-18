"""Tests for remote deployment scripts."""

from __future__ import annotations

import nps_ctl.deploy as deploy


def test_install_nps_preserves_and_restores_tls_certs(monkeypatch):
    captured = {}

    def fake_ssh_execute(ssh_host, script, timeout):
        captured["script"] = script
        return deploy.DeployResult(success=True, message="ok")

    monkeypatch.setattr(deploy, "ssh_execute", fake_ssh_execute)

    deploy.install_nps("example.invalid", "nps_conf = true")

    script = captured["script"]
    backup = script.index("CERT_BACKUP=/tmp/nps-certs-preserve")
    install = script.index("Running NPS install")
    restore = script.index("Restored TLS certificate")

    assert backup < install < restore
    assert "for cert in server.key server.pem; do" in script
    assert 'cp -p "/etc/nps/conf/$cert" "$CERT_BACKUP/$cert"' in script
    assert 'cp -p "$CERT_BACKUP/$cert" "/etc/nps/conf/$cert"' in script
    assert 'rm -rf "$CERT_BACKUP"' in script
