"""Tests for remote deployment scripts."""

from __future__ import annotations

import stat
import subprocess

import nps_ctl.deploy as deploy


def _install_script(monkeypatch) -> str:
    captured = {}

    def fake_ssh_execute(ssh_host, script, timeout):
        captured["script"] = script
        return deploy.DeployResult(success=True, message="ok")

    monkeypatch.setattr(deploy, "ssh_execute", fake_ssh_execute)
    deploy.install_nps("example.invalid", "nps_conf = true")

    script = captured["script"]
    start = script.index("CERT_BACKUP=")
    end = script.index('echo "Cleaning up..."')
    return script[start:end]


def _run_cert_block(tmp_path, monkeypatch, certs, install_exit=0):
    """Run the certificate backup/restore block in a fake root."""
    conf = tmp_path / "etc/nps/conf"
    conf.mkdir(parents=True)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()

    for name, content, mode in certs:
        path = conf / name
        path.write_text(content)
        path.chmod(mode)

    fake_nps = bin_dir / "nps"
    fake_nps.write_text(
        f"""#!/bin/bash
if [ "$1" = install ]; then
    mv "{conf}/server.key" "{conf}/server.key.bak" 2>/dev/null || true
    mv "{conf}/server.pem" "{conf}/server.pem.bak" 2>/dev/null || true
fi
exit {install_exit}
"""
    )
    fake_nps.chmod(0o755)

    block = _install_script(monkeypatch)
    block = block.replace("/etc/nps/conf", str(conf))
    block = block.replace("/tmp/nps-certs-preserve", str(tmp_path / "backup"))
    block = block.replace("/tmp/nps install", f"{fake_nps} install")

    script = tmp_path / "cert-block.sh"
    script.write_text(block)
    result = subprocess.run(
        ["bash", str(script)], cwd=tmp_path, capture_output=True, text=True
    )

    return result, conf, tmp_path / "backup"


def test_install_nps_restores_certs_when_install_renames_them(tmp_path, monkeypatch):
    result, conf, backup = _run_cert_block(
        tmp_path,
        monkeypatch,
        [("server.key", "KEY", 0o600), ("server.pem", "PEM", 0o644)],
    )

    assert result.returncode == 0
    assert "Restored TLS certificate: server.key" in result.stdout
    assert "Restored TLS certificate: server.pem" in result.stdout
    assert (conf / "server.key").read_text() == "KEY"
    assert (conf / "server.pem").read_text() == "PEM"
    assert stat.S_IMODE((conf / "server.key").stat().st_mode) == 0o600
    assert stat.S_IMODE((conf / "server.pem").stat().st_mode) == 0o644
    assert not backup.exists()


def test_install_nps_fresh_install_does_not_create_certs(tmp_path, monkeypatch):
    result, conf, backup = _run_cert_block(tmp_path, monkeypatch, [])

    assert result.returncode == 0
    assert "Restored TLS certificate" not in result.stdout
    assert not (conf / "server.key").exists()
    assert not (conf / "server.pem").exists()
    assert not backup.exists()


def test_install_nps_restores_certs_when_install_exits_nonzero(tmp_path, monkeypatch):
    result, conf, backup = _run_cert_block(
        tmp_path,
        monkeypatch,
        [("server.key", "KEY", 0o600), ("server.pem", "PEM", 0o644)],
        install_exit=1,
    )

    assert result.returncode == 0
    assert (conf / "server.key").read_text() == "KEY"
    assert (conf / "server.pem").read_text() == "PEM"
    assert not backup.exists()
