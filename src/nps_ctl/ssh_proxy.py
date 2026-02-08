"""SSH SOCKS proxy management for NPS API access.

This module provides automatic SSH SOCKS proxy creation and management
for accessing NPS servers through SSH tunnels.
"""

import atexit
import logging
import os
import signal
import socket
import subprocess
import time
from dataclasses import dataclass, field
from typing import ClassVar

logger = logging.getLogger(__name__)


def find_free_port(start: int = 10800, end: int = 10900) -> int:
    """Find a free port in the given range.

    Args:
        start: Start of port range.
        end: End of port range.

    Returns:
        A free port number.

    Raises:
        RuntimeError: If no free port is found.
    """
    for port in range(start, end):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(("127.0.0.1", port))
                return port
        except OSError:
            continue
    raise RuntimeError(f"No free port found in range {start}-{end}")


@dataclass
class SSHProxy:
    """Manages an SSH SOCKS proxy connection.

    This class creates and manages an SSH dynamic port forwarding tunnel
    that acts as a SOCKS5 proxy.

    Args:
        ssh_host: SSH host to connect to (from SSH config).
        local_port: Local port for SOCKS proxy. If 0, auto-select.
        connect_timeout: SSH connection timeout in seconds.

    Example:
        >>> proxy = SSHProxy("cloud.usa4")
        >>> proxy.start()
        >>> print(f"Proxy running on localhost:{proxy.local_port}")
        >>> # Use the proxy...
        >>> proxy.stop()
    """

    ssh_host: str
    local_port: int = 0
    connect_timeout: int = 10
    _process: subprocess.Popen | None = field(default=None, init=False, repr=False)
    _started: bool = field(default=False, init=False)

    # Class-level registry of active proxies for cleanup
    _active_proxies: ClassVar[list["SSHProxy"]] = []
    _cleanup_registered: ClassVar[bool] = False

    def __post_init__(self) -> None:
        """Initialize and register cleanup handler."""
        if self.local_port == 0:
            self.local_port = find_free_port()

        # Register cleanup handler once
        if not SSHProxy._cleanup_registered:
            atexit.register(SSHProxy._cleanup_all)
            SSHProxy._cleanup_registered = True

    @classmethod
    def _cleanup_all(cls) -> None:
        """Clean up all active proxies on exit."""
        for proxy in cls._active_proxies[:]:
            try:
                proxy.stop()
            except Exception:
                pass

    def start(self, wait: bool = True, max_wait: float = 5.0) -> bool:
        """Start the SSH SOCKS proxy.

        Args:
            wait: Whether to wait for the proxy to be ready.
            max_wait: Maximum time to wait for proxy to be ready.

        Returns:
            True if proxy started successfully.

        Raises:
            RuntimeError: If proxy fails to start.
        """
        if self._started:
            logger.debug(f"SSH proxy to {self.ssh_host} already running")
            return True

        cmd = [
            "ssh",
            "-D",
            str(self.local_port),
            "-f",  # Background after authentication
            "-C",  # Compression
            "-q",  # Quiet mode
            "-N",  # No remote command
            "-o",
            f"ConnectTimeout={self.connect_timeout}",
            "-o",
            "ExitOnForwardFailure=yes",
            "-o",
            "ServerAliveInterval=30",
            "-o",
            "ServerAliveCountMax=3",
            self.ssh_host,
        ]

        logger.info(
            f"Starting SSH SOCKS proxy to {self.ssh_host} on port {self.local_port}"
        )

        try:
            # Start SSH process
            # Use -f so SSH backgrounds itself after authentication
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.connect_timeout + 5,
            )

            if result.returncode != 0:
                error_msg = result.stderr.strip() or "Unknown error"
                logger.error(f"SSH proxy failed: {error_msg}")
                raise RuntimeError(f"SSH proxy to {self.ssh_host} failed: {error_msg}")

            # SSH with -f backgrounds itself, so we need to find the process
            # by checking if the port is listening
            if wait:
                if not self._wait_for_ready(max_wait):
                    raise RuntimeError(
                        f"SSH proxy to {self.ssh_host} started but port not ready"
                    )

            self._started = True
            SSHProxy._active_proxies.append(self)
            logger.info(
                f"SSH SOCKS proxy to {self.ssh_host} ready on localhost:{self.local_port}"
            )
            return True

        except subprocess.TimeoutExpired:
            logger.error(f"SSH connection to {self.ssh_host} timed out")
            raise RuntimeError(f"SSH connection to {self.ssh_host} timed out")
        except FileNotFoundError:
            logger.error("SSH command not found")
            raise RuntimeError("SSH command not found. Is OpenSSH installed?")

    def _wait_for_ready(self, max_wait: float) -> bool:
        """Wait for the proxy port to be ready.

        Args:
            max_wait: Maximum time to wait in seconds.

        Returns:
            True if port is ready, False if timeout.
        """
        start = time.perf_counter()
        while time.perf_counter() - start < max_wait:
            if self._is_port_listening():
                return True
            time.sleep(0.1)
        return False

    def _is_port_listening(self) -> bool:
        """Check if the local port is listening."""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(0.5)
                result = s.connect_ex(("127.0.0.1", self.local_port))
                return result == 0
        except Exception:
            return False

    def stop(self) -> None:
        """Stop the SSH SOCKS proxy."""
        if not self._started:
            return

        # Find and kill the SSH process by port
        try:
            # Use lsof to find the process
            result = subprocess.run(
                ["lsof", "-ti", f":{self.local_port}"],
                capture_output=True,
                text=True,
            )
            if result.returncode == 0 and result.stdout.strip():
                pids = result.stdout.strip().split("\n")
                for pid in pids:
                    try:
                        os.kill(int(pid), signal.SIGTERM)
                        logger.debug(f"Killed SSH proxy process {pid}")
                    except (ProcessLookupError, ValueError):
                        pass
        except FileNotFoundError:
            # lsof not available, try pkill
            subprocess.run(
                ["pkill", "-f", f"ssh -D {self.local_port}"],
                capture_output=True,
            )

        self._started = False
        if self in SSHProxy._active_proxies:
            SSHProxy._active_proxies.remove(self)
        logger.info(f"SSH SOCKS proxy to {self.ssh_host} stopped")

    @property
    def address(self) -> str:
        """Get the proxy address in host:port format."""
        return f"localhost:{self.local_port}"

    @property
    def is_running(self) -> bool:
        """Check if the proxy is running."""
        return self._started and self._is_port_listening()

    def __enter__(self) -> "SSHProxy":
        """Context manager entry."""
        self.start()
        return self

    def __exit__(self, *args: object) -> None:
        """Context manager exit."""
        self.stop()


def create_proxy_for_edge(ssh_host: str, port: int = 0) -> SSHProxy:
    """Create an SSH SOCKS proxy for an edge.

    Args:
        ssh_host: SSH host from edge configuration.
        port: Local port (0 for auto-select).

    Returns:
        SSHProxy instance (not started).
    """
    return SSHProxy(ssh_host=ssh_host, local_port=port)
