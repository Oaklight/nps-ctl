"""Base NPS API client with authentication and request infrastructure.

This module provides the core NPSClient class that handles authentication,
HTTP requests, and SSL configuration for communicating with NPS servers.
"""

import hashlib
import json
import logging
import socket
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any

try:
    import socks

    HAS_SOCKS = True
except ImportError:
    HAS_SOCKS = False

from .exceptions import NPSAPIError, NPSAuthError
from .logging import get_operation_logger

logger = logging.getLogger(__name__)
op_logger = get_operation_logger(__name__)


@dataclass
class NPSClient:
    """API client for a single NPS server.

    Provides authenticated HTTP communication with an NPS server's Web API.
    Domain-specific operations (client management, tunnel management, host
    management) are provided by separate modules that operate on an
    NPSClient instance.

    Args:
        base_url: The base URL of the NPS server (e.g., "https://nps.example.com").
        auth_key: The authentication key configured in nps.conf.
        timeout: Request timeout in seconds.
        verify_ssl: Whether to verify SSL certificates.
        proxy: HTTP/HTTPS proxy URL (e.g., "http://127.0.0.1:7890").
        socks_proxy: SOCKS5 proxy address (e.g., "localhost:1080" for SSH tunnel).

    Example:
        >>> from nps_ctl.base import NPSClient
        >>> from nps_ctl.client_mgmt import list_clients
        >>> nps = NPSClient("https://nps.example.com", "your_auth_key")
        >>> clients = list_clients(nps)
        >>> for c in clients:
        ...     print(f"{c['Id']}: {c['Remark']}")
    """

    base_url: str
    auth_key: str
    timeout: int = 30
    verify_ssl: bool = True
    max_retries: int = 3
    retry_backoff: float = 1.0
    proxy: str | None = None
    socks_proxy: str | None = None
    _ssl_context: ssl.SSLContext | None = field(default=None, init=False, repr=False)
    _opener: urllib.request.OpenerDirector | None = field(
        default=None, init=False, repr=False
    )
    _original_socket: type | None = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        """Initialize SSL context and proxy handler."""
        self.base_url = self.base_url.rstrip("/")

        # Setup SSL context
        if not self.verify_ssl:
            self._ssl_context = ssl.create_default_context()
            self._ssl_context.check_hostname = False
            self._ssl_context.verify_mode = ssl.CERT_NONE
            logger.debug(f"SSL verification disabled for {self.base_url}")
        else:
            self._ssl_context = ssl.create_default_context()

        # Setup SOCKS proxy if specified (takes precedence over HTTP proxy)
        if self.socks_proxy:
            if not HAS_SOCKS:
                raise ImportError(
                    "PySocks is required for SOCKS proxy support. "
                    "Install it with: pip install PySocks"
                )
            # Parse socks_proxy address (format: host:port)
            if ":" in self.socks_proxy:
                socks_host, socks_port_str = self.socks_proxy.rsplit(":", 1)
                socks_port = int(socks_port_str)
            else:
                socks_host = self.socks_proxy
                socks_port = 1080  # Default SOCKS port

            op_logger.connection_attempt(
                self.base_url,
                proxy=f"socks5://{socks_host}:{socks_port}",
                verify_ssl=self.verify_ssl,
            )

            # Store original socket class for potential cleanup
            self._original_socket = socket.socket

            # Set default SOCKS proxy globally for this client
            socks.set_default_proxy(socks.SOCKS5, socks_host, socks_port)
            socket.socket = socks.socksocket  # type: ignore[assignment]  # runtime monkey-patch for SOCKS proxy

            logger.info(
                f"SOCKS5 proxy enabled: {socks_host}:{socks_port} for {self.base_url}"
            )

        # Setup HTTP proxy if specified (only if SOCKS proxy is not set)
        elif self.proxy:
            op_logger.connection_attempt(
                self.base_url, proxy=self.proxy, verify_ssl=self.verify_ssl
            )
            proxy_handler = urllib.request.ProxyHandler(
                {"http": self.proxy, "https": self.proxy}
            )
            https_handler = urllib.request.HTTPSHandler(context=self._ssl_context)
            self._opener = urllib.request.build_opener(proxy_handler, https_handler)
        else:
            op_logger.connection_attempt(
                self.base_url, verify_ssl=self.verify_ssl, timeout=self.timeout
            )

        logger.info(f"NPSClient initialized for {self.base_url}")

    def _request_with_retry(
        self,
        req: urllib.request.Request,
        *,
        error_prefix: str = "Request failed",
        error_cls: type[Exception] = NPSAPIError,
    ) -> bytes:
        """Execute an HTTP request with retry and exponential backoff.

        Args:
            req: The prepared urllib Request object.
            error_prefix: Prefix for error messages.
            error_cls: Exception class to raise on final failure.

        Returns:
            Raw response bytes.

        Raises:
            error_cls: If all retries are exhausted.
        """
        last_error: Exception | None = None
        url = req.full_url
        method = req.get_method()
        start_time = time.perf_counter()

        logger.debug(f"Request: {method} {url}")

        for attempt in range(self.max_retries):
            attempt_start = time.perf_counter()
            try:
                if self._opener:
                    with self._opener.open(req, timeout=self.timeout) as response:
                        data = response.read()
                        elapsed_ms = (time.perf_counter() - attempt_start) * 1000
                        op_logger.connection_success(url, response_time_ms=elapsed_ms)
                        logger.debug(
                            f"Response: {response.status} ({len(data)} bytes, "
                            f"{elapsed_ms:.1f}ms)"
                        )
                        return data
                else:
                    with urllib.request.urlopen(
                        req, timeout=self.timeout, context=self._ssl_context
                    ) as response:
                        data = response.read()
                        elapsed_ms = (time.perf_counter() - attempt_start) * 1000
                        op_logger.connection_success(url, response_time_ms=elapsed_ms)
                        logger.debug(
                            f"Response: {response.status} ({len(data)} bytes, "
                            f"{elapsed_ms:.1f}ms)"
                        )
                        return data
            except urllib.error.HTTPError as e:
                last_error = e
                op_logger.connection_failed(
                    url, f"HTTP {e.code} {e.reason}", attempt=attempt + 1
                )
                if attempt < self.max_retries - 1:
                    wait = self.retry_backoff * (2**attempt)
                    logger.info(f"Retrying in {wait:.1f}s...")
                    time.sleep(wait)
            except urllib.error.URLError as e:
                last_error = e
                op_logger.connection_failed(url, str(e.reason), attempt=attempt + 1)
                if attempt < self.max_retries - 1:
                    wait = self.retry_backoff * (2**attempt)
                    logger.info(f"Retrying in {wait:.1f}s...")
                    time.sleep(wait)
            except (TimeoutError, OSError) as e:
                # Handle socket timeout and other OS-level network errors
                last_error = e
                error_msg = "Timeout" if isinstance(e, TimeoutError) else str(e)
                op_logger.connection_failed(url, error_msg, attempt=attempt + 1)
                if attempt < self.max_retries - 1:
                    wait = self.retry_backoff * (2**attempt)
                    logger.info(f"Retrying in {wait:.1f}s...")
                    time.sleep(wait)

        # All retries exhausted
        total_elapsed_ms = (time.perf_counter() - start_time) * 1000
        logger.error(
            f"{error_prefix} after {self.max_retries} attempts "
            f"({total_elapsed_ms:.1f}ms total): {last_error}"
        )
        raise error_cls(f"{error_prefix}: {last_error}") from last_error

    def _get_server_time(self) -> int:
        """Get the server timestamp for authentication.

        Returns:
            Server timestamp as integer.

        Raises:
            NPSAuthError: If failed to get server time.
        """
        url = f"{self.base_url}/auth/gettime"
        logger.debug(f"Getting server time from {url}")
        req = urllib.request.Request(url)
        try:
            raw = self._request_with_retry(
                req,
                error_prefix="Failed to get server time",
                error_cls=NPSAuthError,
            )
            data = json.loads(raw.decode("utf-8"))
            return int(data.get("time", 0))
        except NPSAuthError:
            raise
        except (json.JSONDecodeError, ValueError) as e:
            raise NPSAuthError(f"Invalid server time response: {e}") from e

    def _generate_auth_key(self, timestamp: int) -> str:
        """Generate authentication key using MD5.

        Args:
            timestamp: Server timestamp.

        Returns:
            MD5 hash of auth_key + timestamp.
        """
        raw = f"{self.auth_key}{timestamp}"
        return hashlib.md5(raw.encode("utf-8")).hexdigest()

    def request(
        self,
        endpoint: str,
        method: str = "GET",
        data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Make an authenticated API request.

        Args:
            endpoint: API endpoint (e.g., "/client/list").
            method: HTTP method.
            data: Request data for POST requests.

        Returns:
            JSON response as dictionary.

        Raises:
            NPSAPIError: If the request fails.
        """
        start_time = time.perf_counter()
        op_logger.request_start(method, endpoint, data)

        timestamp = self._get_server_time()
        auth_key = self._generate_auth_key(timestamp)

        # Auth params must be included in POST body, not URL query string
        auth_params = {"auth_key": auth_key, "timestamp": str(timestamp)}

        if method == "POST":
            # For POST requests, include auth params in the body
            post_params = {**auth_params}
            if data:
                post_params.update({k: str(v) for k, v in data.items()})
            post_data = urllib.parse.urlencode(post_params).encode("utf-8")
            url = f"{self.base_url}{endpoint}"
            req = urllib.request.Request(url, data=post_data, method="POST")
            req.add_header("Content-Type", "application/x-www-form-urlencoded")
        else:
            # For GET requests, include auth params in URL
            params = {**auth_params}
            if data:
                params.update({k: str(v) for k, v in data.items()})
            url = f"{self.base_url}{endpoint}?{urllib.parse.urlencode(params)}"
            req = urllib.request.Request(url, method=method)

        try:
            raw = self._request_with_retry(
                req,
                error_prefix=f"API request {endpoint} failed",
            )
            response_data = raw.decode("utf-8")
            result = json.loads(response_data)
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            api_status = result.get("status")
            op_logger.request_success(
                method, endpoint, status=api_status, response_time_ms=elapsed_ms
            )
            return result

        except NPSAPIError as e:
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            op_logger.request_failed(
                method, endpoint, str(e), status_code=getattr(e, "status_code", None)
            )
            raise
        except json.JSONDecodeError as e:
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            op_logger.request_failed(method, endpoint, f"Invalid JSON: {e}")
            raise NPSAPIError(f"Invalid JSON response: {e}") from e
