"""NPS deployment module for installing and uninstalling NPS servers.

This module provides functions for deploying NPS to remote servers via SSH.
"""

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Default NPS version
DEFAULT_NPS_VERSION = "v0.34.1"

# Default NPC version (same as NPS)
DEFAULT_NPC_VERSION = "v0.34.1"

# Mirror sources for NPS releases (in priority order)
# Uses jsdelivr CDN mirrors which are faster in China and other regions
NPS_MIRROR_SOURCES = [
    "https://fastly.jsdelivr.net/gh/djylb/nps-mirror@{version}/linux_amd64_server.tar.gz",
    "https://cdn.jsdelivr.net/gh/djylb/nps-mirror@{version}/linux_amd64_server.tar.gz",
    "https://github.com/djylb/nps/releases/download/{version}/linux_amd64_server.tar.gz",
]

# Mirror sources for NPC releases (in priority order)
NPC_MIRROR_SOURCES = [
    "https://fastly.jsdelivr.net/gh/djylb/nps-mirror@{version}/linux_amd64_client.tar.gz",
    "https://cdn.jsdelivr.net/gh/djylb/nps-mirror@{version}/linux_amd64_client.tar.gz",
    "https://github.com/djylb/nps/releases/download/{version}/linux_amd64_client.tar.gz",
]

# Default NPS release URL (djylb/nps fork) - kept for backward compatibility
DEFAULT_NPS_RELEASE_URL = (
    "https://github.com/djylb/nps/releases/download/v0.34.1/linux_amd64_server.tar.gz"
)


@dataclass
class DeployResult:
    """Result of a deployment operation."""

    success: bool
    message: str
    stdout: str = ""
    stderr: str = ""


def load_template(template_path: Path | str) -> str:
    """Load a template file.

    Args:
        template_path: Path to the template file.

    Returns:
        Template content as string.

    Raises:
        FileNotFoundError: If template file doesn't exist.
    """
    path = Path(template_path)
    if not path.exists():
        raise FileNotFoundError(f"Template file not found: {path}")
    return path.read_text()


def render_template(template: str, variables: dict[str, Any]) -> str:
    """Render a template with variables.

    Uses simple {variable} substitution.

    Args:
        template: Template string with {variable} placeholders.
        variables: Dictionary of variable names to values.

    Returns:
        Rendered template string.
    """
    result = template
    for key, value in variables.items():
        result = result.replace(f"{{{key}}}", str(value))
    return result


def ssh_execute(
    ssh_host: str,
    script: str,
    timeout: int = 120,
) -> DeployResult:
    """Execute a script on a remote host via SSH.

    Args:
        ssh_host: SSH host (e.g., "cloud.deu1").
        script: Bash script to execute.
        timeout: Command timeout in seconds.

    Returns:
        DeployResult with success status and output.
    """
    try:
        result = subprocess.run(
            ["ssh", ssh_host, "bash -s"],
            input=script,
            capture_output=True,
            text=True,
            timeout=timeout,
        )

        if result.returncode == 0:
            return DeployResult(
                success=True,
                message="Command executed successfully",
                stdout=result.stdout,
                stderr=result.stderr,
            )
        else:
            return DeployResult(
                success=False,
                message=f"Command failed with exit code {result.returncode}",
                stdout=result.stdout,
                stderr=result.stderr,
            )

    except subprocess.TimeoutExpired:
        return DeployResult(
            success=False,
            message="SSH command timed out",
        )
    except Exception as e:
        return DeployResult(
            success=False,
            message=f"SSH error: {e}",
        )


def get_download_urls(version: str = DEFAULT_NPS_VERSION) -> list[str]:
    """Get list of download URLs for NPS release.

    Args:
        version: NPS version tag (e.g., "v0.34.1").

    Returns:
        List of URLs to try in order.
    """
    return [url.format(version=version) for url in NPS_MIRROR_SOURCES]


def get_npc_download_urls(version: str = DEFAULT_NPC_VERSION) -> list[str]:
    """Get list of download URLs for NPC release.

    Args:
        version: NPC version tag (e.g., "v0.34.1").

    Returns:
        List of URLs to try in order.
    """
    return [url.format(version=version) for url in NPC_MIRROR_SOURCES]


def install_nps(
    ssh_host: str,
    nps_conf: str,
    version: str = DEFAULT_NPS_VERSION,
    release_url: str | None = None,
    timeout: int = 120,
) -> DeployResult:
    """Install NPS on a remote server.

    Uses NPS's built-in install command which properly sets up
    /etc/nps/conf and /etc/nps/web directories.

    Downloads from multiple mirror sources (jsdelivr CDN, GitHub) with fallback.

    Args:
        ssh_host: SSH host to install on.
        nps_conf: NPS configuration file content.
        version: NPS version to install (e.g., "v0.34.1").
        release_url: Custom URL to download NPS release tarball (overrides mirrors).
        timeout: Command timeout in seconds.

    Returns:
        DeployResult with installation status.
    """
    # Build download URLs
    if release_url:
        # Use custom URL only
        urls = [release_url]
    else:
        # Use mirror sources
        urls = get_download_urls(version)

    # Build URL list for shell script
    urls_shell = " ".join(f'"{url}"' for url in urls)

    install_script = f"""
set -e

cd /tmp

# Download with fallback mirrors
URLS=({urls_shell})
DOWNLOADED=0

for url in "${{URLS[@]}}"; do
    echo "Trying $url ..."
    if curl -sfSL --connect-timeout 10 -o nps.tar.gz "$url"; then
        if [ -s nps.tar.gz ]; then
            echo "Downloaded successfully from $url"
            DOWNLOADED=1
            break
        fi
    fi
    echo "Failed, trying next mirror..."
done

if [ "$DOWNLOADED" -ne 1 ]; then
    echo "Error: Failed to download NPS from all mirrors"
    exit 1
fi

echo "Extracting..."
tar -xzf nps.tar.gz

echo "Running NPS install..."
chmod +x /tmp/nps
/tmp/nps install

echo "Cleaning up..."
rm -f /tmp/nps.tar.gz /tmp/nps
rm -rf /tmp/web /tmp/conf

echo "Writing configuration..."
cat > /etc/nps/conf/nps.conf << 'EOFCONF'
{nps_conf}
EOFCONF

echo "Initializing data files..."
[ -f /etc/nps/conf/clients.json ] || echo '[]' > /etc/nps/conf/clients.json
[ -f /etc/nps/conf/hosts.json ] || echo '[]' > /etc/nps/conf/hosts.json
[ -f /etc/nps/conf/tasks.json ] || echo '[]' > /etc/nps/conf/tasks.json
[ -f /etc/nps/conf/global.json ] || echo '{{}}' > /etc/nps/conf/global.json

echo "Starting NPS service..."
# NPS install creates Nps.service (capital N)
systemctl daemon-reload
systemctl enable Nps
systemctl start Nps

echo "Checking service status..."
sleep 2
if systemctl is-active --quiet Nps; then
    echo "NPS installed and running successfully."
else
    echo "Warning: NPS service may not be running properly."
    systemctl status Nps --no-pager || true
fi
"""

    return ssh_execute(ssh_host, install_script, timeout)


def uninstall_nps(
    ssh_host: str,
    timeout: int = 60,
) -> DeployResult:
    """Uninstall NPS from a remote server.

    Handles both Nps.service (from nps install) and nps.service (manual).
    Removes files from /opt/nps, /usr/bin/nps, /usr/local/bin/nps, and /etc/nps.

    Args:
        ssh_host: SSH host to uninstall from.
        timeout: Command timeout in seconds.

    Returns:
        DeployResult with uninstallation status.
    """
    uninstall_script = """
set -e

echo "Stopping NPS service..."
# Handle both Nps.service (from nps install) and nps.service (manual)
systemctl stop Nps 2>/dev/null || true
systemctl stop nps 2>/dev/null || true
systemctl disable Nps 2>/dev/null || true
systemctl disable nps 2>/dev/null || true

echo "Removing systemd service..."
rm -f /etc/systemd/system/Nps.service
rm -f /etc/systemd/system/nps.service
systemctl daemon-reload

echo "Removing NPS files..."
# Check /opt/nps first
if [ -d /opt/nps ]; then
    echo "  Found /opt/nps, removing..."
    rm -rf /opt/nps
fi

# Check /usr/bin/nps
if [ -f /usr/bin/nps ]; then
    echo "  Found /usr/bin/nps, removing..."
    rm -f /usr/bin/nps
fi

# Check /usr/local/bin/nps
if [ -f /usr/local/bin/nps ]; then
    echo "  Found /usr/local/bin/nps, removing..."
    rm -f /usr/local/bin/nps
fi

echo "Removing configuration..."
rm -rf /etc/nps

echo "NPS uninstalled successfully."
"""

    return ssh_execute(ssh_host, uninstall_script, timeout)


def check_nps_status(ssh_host: str) -> DeployResult:
    """Check NPS status on a remote server.

    Args:
        ssh_host: SSH host to check.

    Returns:
        DeployResult with status information.
    """
    check_script = """
echo "=== NPS Version ==="
nps --version 2>/dev/null || echo "NPS not installed"

echo ""
echo "=== Service Status ==="
systemctl is-active Nps 2>/dev/null || systemctl is-active nps 2>/dev/null || echo "Not running"

echo ""
echo "=== Listening Ports ==="
ss -tlnp 2>/dev/null | grep nps || echo "No ports"
"""

    return ssh_execute(ssh_host, check_script, timeout=30)


def install_npc(
    ssh_host: str,
    server_addrs: str,
    vkey: str,
    tls_enable: bool = True,
    version: str = DEFAULT_NPC_VERSION,
    release_url: str | None = None,
    timeout: int = 120,
) -> DeployResult:
    """Install NPC on a remote server.

    Uses NPC's built-in install command with no-config mode.
    Downloads from multiple mirror sources (jsdelivr CDN, GitHub) with fallback.

    Args:
        ssh_host: SSH host to install on.
        server_addrs: Comma-separated server addresses (e.g., "host1:51235,host2:51235").
        vkey: Client verification key.
        tls_enable: Whether to enable TLS connection.
        version: NPC version to install (e.g., "v0.34.1").
        release_url: Custom URL to download NPC release tarball (overrides mirrors).
        timeout: Command timeout in seconds.

    Returns:
        DeployResult with installation status.
    """
    # Build download URLs
    if release_url:
        urls = [release_url]
    else:
        urls = get_npc_download_urls(version)

    # Build URL list for shell script
    urls_shell = " ".join(f'"{url}"' for url in urls)

    # Build install arguments
    tls_arg = "-tls_enable=true" if tls_enable else ""

    install_script = f"""
set -e

cd /tmp

# Download with fallback mirrors
URLS=({urls_shell})
DOWNLOADED=0

for url in "${{URLS[@]}}"; do
    echo "Trying $url ..."
    if curl -sfSL --connect-timeout 10 -o npc.tar.gz "$url"; then
        if [ -s npc.tar.gz ]; then
            echo "Downloaded successfully from $url"
            DOWNLOADED=1
            break
        fi
    fi
    echo "Failed, trying next mirror..."
done

if [ "$DOWNLOADED" -ne 1 ]; then
    echo "Error: Failed to download NPC from all mirrors"
    exit 1
fi

echo "Extracting..."
tar -xzf npc.tar.gz

echo "Stopping existing NPC service if running..."
npc stop 2>/dev/null || true

echo "Uninstalling existing NPC if present..."
/tmp/npc uninstall 2>/dev/null || true

echo "Installing NPC..."
chmod +x /tmp/npc
/tmp/npc install -server="{server_addrs}" -vkey="{vkey}" {tls_arg}

echo "Cleaning up..."
rm -f /tmp/npc.tar.gz /tmp/npc

echo "Starting NPC service..."
npc start

echo "Checking service status..."
sleep 2
if npc status 2>/dev/null | grep -q "running"; then
    echo "NPC installed and running successfully."
else
    echo "Warning: NPC service may not be running properly."
    npc status || true
fi
"""

    return ssh_execute(ssh_host, install_script, timeout)


def uninstall_npc(
    ssh_host: str,
    timeout: int = 60,
) -> DeployResult:
    """Uninstall NPC from a remote server.

    Args:
        ssh_host: SSH host to uninstall from.
        timeout: Command timeout in seconds.

    Returns:
        DeployResult with uninstallation status.
    """
    uninstall_script = """
set -e

echo "Stopping NPC service..."
npc stop 2>/dev/null || true

echo "Uninstalling NPC..."
npc uninstall 2>/dev/null || true

echo "Removing NPC files..."
rm -f /usr/bin/npc /usr/local/bin/npc

echo "NPC uninstalled successfully."
"""

    return ssh_execute(ssh_host, uninstall_script, timeout)


def check_npc_status(ssh_host: str) -> DeployResult:
    """Check NPC status on a remote server.

    Args:
        ssh_host: SSH host to check.

    Returns:
        DeployResult with status information.
    """
    check_script = """
echo "=== NPC Version ==="
npc --version 2>/dev/null || echo "NPC not installed"

echo ""
echo "=== Service Status ==="
npc status 2>/dev/null || echo "Not running or not installed"
"""

    return ssh_execute(ssh_host, check_script, timeout=30)


def restart_npc(ssh_host: str) -> DeployResult:
    """Restart NPC service on a remote server.

    Args:
        ssh_host: SSH host to restart NPC on.

    Returns:
        DeployResult with restart status.
    """
    restart_script = """
echo "Restarting NPC service..."
npc restart 2>/dev/null || {
    echo "Failed to restart NPC"
    exit 1
}

sleep 2
echo "Checking service status..."
npc status 2>/dev/null || echo "Status check failed"
"""

    return ssh_execute(ssh_host, restart_script, timeout=30)
