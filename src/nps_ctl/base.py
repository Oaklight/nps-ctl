"""Base NPS API client with authentication and request infrastructure.

This module provides the core NPSClient class that handles authentication,
HTTP requests, and SSL configuration for communicating with NPS servers.
"""

import hashlib
import json
import logging
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any

from .exceptions import NPSAPIError, NPSAuthError

logger = logging.getLogger(__name__)


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
    _ssl_context: ssl.SSLContext | None = field(default=None, init=False, repr=False)
    _opener: urllib.request.OpenerDirector | None = field(
        default=None, init=False, repr=False
    )

    def __post_init__(self) -> None:
        """Initialize SSL context and proxy handler."""
        self.base_url = self.base_url.rstrip("/")

        # Setup SSL context
        if not self.verify_ssl:
            self._ssl_context = ssl.create_default_context()
            self._ssl_context.check_hostname = False
            self._ssl_context.verify_mode = ssl.CERT_NONE
        else:
            self._ssl_context = ssl.create_default_context()

        # Setup proxy if specified
        if self.proxy:
            logger.debug(f"Using proxy: {self.proxy}")
            proxy_handler = urllib.request.ProxyHandler(
                {"http": self.proxy, "https": self.proxy}
            )
            https_handler = urllib.request.HTTPSHandler(context=self._ssl_context)
            self._opener = urllib.request.build_opener(proxy_handler, https_handler)

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
        logger.debug(f"Request: {req.get_method()} {url}")

        for attempt in range(self.max_retries):
            try:
                if self._opener:
                    with self._opener.open(req, timeout=self.timeout) as response:
                        data = response.read()
                        logger.debug(f"Response: {response.status} ({len(data)} bytes)")
                        return data
                else:
                    with urllib.request.urlopen(
                        req, timeout=self.timeout, context=self._ssl_context
                    ) as response:
                        data = response.read()
                        logger.debug(f"Response: {response.status} ({len(data)} bytes)")
                        return data
            except urllib.error.HTTPError as e:
                last_error = e
                logger.warning(
                    f"{error_prefix} (attempt {attempt + 1}/{self.max_retries}): "
                    f"HTTP {e.code} {e.reason}"
                )
                if attempt < self.max_retries - 1:
                    wait = self.retry_backoff * (2**attempt)
                    logger.debug(f"Retrying in {wait:.1f}s...")
                    time.sleep(wait)
            except urllib.error.URLError as e:
                last_error = e
                if attempt < self.max_retries - 1:
                    wait = self.retry_backoff * (2**attempt)
                    logger.warning(
                        f"{error_prefix} (attempt {attempt + 1}/{self.max_retries},"
                        f" retrying in {wait:.1f}s): {e}"
                    )
                    time.sleep(wait)
                else:
                    logger.error(
                        f"{error_prefix} (attempt {attempt + 1}/{self.max_retries},"
                        f" giving up): {e}"
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

        logger.debug(f"API request: {method} {endpoint}")
        try:
            raw = self._request_with_retry(
                req,
                error_prefix=f"API request {endpoint} failed",
            )
            response_data = raw.decode("utf-8")
            result = json.loads(response_data)
            logger.debug(f"API response: status={result.get('status')}")
            return result

        except NPSAPIError:
            raise
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON response for {endpoint}: {e}")
            raise NPSAPIError(f"Invalid JSON response: {e}") from e
