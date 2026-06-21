"""Base NPS API client with authentication and request infrastructure.

This module provides the core NPSClient class that handles authentication,
HTTP requests, and SSL configuration for communicating with NPS servers.
"""

import hashlib
import json
import logging
import socket
import ssl
import threading
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
        auth_key: The authentication key for legacy API (configured in nps.conf).
        timeout: Request timeout in seconds.
        verify_ssl: Whether to verify SSL certificates.
        proxy: HTTP/HTTPS proxy URL (e.g., "http://127.0.0.1:7890").
        socks_proxy: SOCKS5 proxy address (e.g., "localhost:1080" for SSH tunnel).
        username: Username for modern API auth (v0.35.0+).
        password: Password for modern API auth (v0.35.0+).
        platform_token: Static platform token for modern API (v0.35.0+).
        api_mode: API mode selection ("legacy", "modern", or "auto").

    Example:
        >>> from nps_ctl.base import NPSClient
        >>> from nps_ctl.client_mgmt import list_clients
        >>> nps = NPSClient("https://nps.example.com", "your_auth_key")
        >>> clients = list_clients(nps)
        >>> for c in clients:
        ...     print(f"{c['Id']}: {c['Remark']}")
    """

    base_url: str
    auth_key: str = ""
    timeout: int = 30
    verify_ssl: bool = True
    max_retries: int = 3
    retry_backoff: float = 1.0
    proxy: str | None = None
    socks_proxy: str | None = None
    # Modern API credentials (v0.35.0+)
    username: str = ""
    password: str = ""
    platform_token: str = ""
    api_mode: str = "auto"  # "legacy" | "modern" | "auto"
    # Private fields
    _ssl_context: ssl.SSLContext | None = field(default=None, init=False, repr=False)
    _opener: urllib.request.OpenerDirector | None = field(
        default=None, init=False, repr=False
    )
    _original_socket: type | None = field(default=None, init=False, repr=False)
    _bearer_token: str | None = field(default=None, init=False, repr=False)
    _api_mode_detected: bool | None = field(default=None, init=False, repr=False)
    _auth_lock: threading.Lock = field(
        default_factory=threading.Lock, init=False, repr=False
    )

    def __post_init__(self) -> None:
        """Initialize SSL context and proxy handler."""
        self.base_url = self.base_url.rstrip("/")

        # Validate timeout type (catches misuse like passing auth_crypt_key positionally)
        if not isinstance(self.timeout, (int, float)):
            raise TypeError(
                f"timeout must be a number, got {type(self.timeout).__name__}: "
                f"{self.timeout!r}"
            )
        self.timeout = int(self.timeout)

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

    def cleanup(self) -> None:
        """Restore original socket class if SOCKS proxy was used.

        Call this when done with the client to undo the global socket
        monkey-patch. Also called automatically via context manager.
        """
        if self._original_socket is not None:
            socket.socket = self._original_socket  # type: ignore[assignment]  # ty: ignore[invalid-assignment]  # restoring original socket
            self._original_socket = None
            if HAS_SOCKS:
                socks.set_default_proxy()
            logger.debug(f"SOCKS proxy cleaned up for {self.base_url}")

    def __enter__(self) -> "NPSClient":
        """Enter context manager."""
        return self

    def __exit__(self, *exc: object) -> None:
        """Exit context manager, restoring original socket."""
        self.cleanup()

    def __del__(self) -> None:
        """Restore original socket on garbage collection."""
        self.cleanup()

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

    # --- Modern API support (v0.35.0+) ---

    @property
    def is_modern(self) -> bool:
        """Check if this server supports the modern /api/* management API.

        Returns:
            True if the server supports modern API and credentials are configured.
        """
        if self.api_mode == "legacy":
            return False
        # No modern credentials → can't use modern API
        if not self.username and not self.platform_token:
            return False
        if self.api_mode == "modern":
            return True
        # auto: probe once with double-checked locking
        if self._api_mode_detected is not None:
            return self._api_mode_detected
        with self._auth_lock:
            if self._api_mode_detected is None:
                self._api_mode_detected = self._detect_modern()
        return self._api_mode_detected

    def _detect_modern(self) -> bool:
        """Probe the server to check if the modern API is available.

        Sends a GET request to /api/system/health with a short timeout
        and no retry. Returns True on HTTP 200, False otherwise.

        Returns:
            True if the modern API is available.
        """
        url = f"{self.base_url}/api/system/health"
        req = urllib.request.Request(url, method="GET")
        detect_timeout = min(5, self.timeout)
        try:
            if self._opener:
                with self._opener.open(req, timeout=detect_timeout) as response:
                    is_modern = response.status == 200
            else:
                with urllib.request.urlopen(
                    req, timeout=detect_timeout, context=self._ssl_context
                ) as response:
                    is_modern = response.status == 200
            logger.info(
                f"Modern API detection for {self.base_url}: "
                f"{'available' if is_modern else 'not available'}"
            )
            return is_modern
        except Exception:
            logger.debug(f"Modern API not available at {self.base_url}")
            return False

    def _get_bearer_token(self) -> str:
        """Get or refresh the Bearer token for modern API authentication.

        Uses platform_token directly if configured, otherwise authenticates
        via POST /api/auth/token with username/password.

        Returns:
            Bearer token string.

        Raises:
            NPSAuthError: If token acquisition fails.
        """
        if self.platform_token:
            return self.platform_token

        with self._auth_lock:
            if self._bearer_token:
                return self._bearer_token

            url = f"{self.base_url}/api/auth/token"
            payload = json.dumps(
                {"username": self.username, "password": self.password}
            ).encode("utf-8")
            req = urllib.request.Request(url, data=payload, method="POST")
            req.add_header("Content-Type", "application/json")

            try:
                raw = self._request_with_retry(
                    req,
                    error_prefix="Failed to acquire Bearer token",
                    error_cls=NPSAuthError,
                )
                data = json.loads(raw.decode("utf-8"))
                # Extract token from response — try common locations
                token = (
                    data.get("token")
                    or data.get("data", {}).get("token")
                    or data.get("access_token")
                )
                if not token:
                    raise NPSAuthError(
                        f"No token in auth response: {list(data.keys())}"
                    )
                self._bearer_token = token
                logger.info(f"Bearer token acquired for {self.base_url}")
                return token
            except NPSAuthError:
                raise
            except (json.JSONDecodeError, ValueError) as e:
                raise NPSAuthError(f"Invalid auth response: {e}") from e

    def _invalidate_token(self) -> None:
        """Clear the cached Bearer token to force re-authentication."""
        with self._auth_lock:
            self._bearer_token = None

    def api_request(
        self,
        method: str,
        endpoint: str,
        data: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Make an authenticated modern API request with JSON body.

        Args:
            method: HTTP method (GET, POST, etc.).
            endpoint: API endpoint (e.g., "/api/hosts").
            data: JSON body for POST requests.
            params: Query parameters for GET requests.

        Returns:
            JSON response as dictionary.

        Raises:
            NPSAPIError: If the request fails.
        """
        start_time = time.perf_counter()
        op_logger.request_start(method, endpoint, data)

        token = self._get_bearer_token()

        # Build URL with query params
        url = f"{self.base_url}{endpoint}"
        if params:
            filtered = {k: str(v) for k, v in params.items() if v is not None}
            if filtered:
                url = f"{url}?{urllib.parse.urlencode(filtered)}"

        # Build request
        if data is not None and method != "GET":
            body = json.dumps(data).encode("utf-8")
            req = urllib.request.Request(url, data=body, method=method)
            req.add_header("Content-Type", "application/json")
        else:
            req = urllib.request.Request(url, method=method)

        # Set auth header
        if self.platform_token:
            req.add_header("X-Node-Token", token)
        else:
            req.add_header("Authorization", f"Bearer {token}")

        try:
            raw = self._request_with_retry(
                req, error_prefix=f"API request {endpoint} failed"
            )
            result = json.loads(raw.decode("utf-8"))
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            op_logger.request_success(method, endpoint, response_time_ms=elapsed_ms)
            return result

        except NPSAPIError as e:
            # On 401, invalidate token and retry once
            if "401" in str(e):
                logger.info("Got 401, refreshing token and retrying...")
                self._invalidate_token()
                token = self._get_bearer_token()
                if self.platform_token:
                    req.remove_header("X-Node-Token")
                    req.add_header("X-Node-Token", token)
                else:
                    req.remove_header("Authorization")
                    req.add_header("Authorization", f"Bearer {token}")
                try:
                    raw = self._request_with_retry(
                        req, error_prefix=f"API request {endpoint} failed (retry)"
                    )
                    result = json.loads(raw.decode("utf-8"))
                    elapsed_ms = (time.perf_counter() - start_time) * 1000
                    op_logger.request_success(
                        method, endpoint, response_time_ms=elapsed_ms
                    )
                    return result
                except Exception:
                    pass  # Fall through to original error
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            op_logger.request_failed(
                method,
                endpoint,
                str(e),
                status_code=getattr(e, "status_code", None),
            )
            raise
        except json.JSONDecodeError as e:
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            op_logger.request_failed(method, endpoint, f"Invalid JSON: {e}")
            raise NPSAPIError(f"Invalid JSON response: {e}") from e
