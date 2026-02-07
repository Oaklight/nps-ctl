"""Base NPS API client with authentication and request infrastructure.

This module provides the core NPSClient class that handles authentication,
HTTP requests, and SSL configuration for communicating with NPS servers.
"""

import hashlib
import json
import logging
import ssl
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any

from nps_ctl.exceptions import NPSAPIError, NPSAuthError

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
    _ssl_context: ssl.SSLContext | None = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        """Initialize SSL context."""
        self.base_url = self.base_url.rstrip("/")
        if not self.verify_ssl:
            self._ssl_context = ssl.create_default_context()
            self._ssl_context.check_hostname = False
            self._ssl_context.verify_mode = ssl.CERT_NONE

    def _get_server_time(self) -> int:
        """Get the server timestamp for authentication.

        Returns:
            Server timestamp as integer.

        Raises:
            NPSAuthError: If failed to get server time.
        """
        url = f"{self.base_url}/auth/gettime"
        try:
            req = urllib.request.Request(url)
            with urllib.request.urlopen(
                req, timeout=self.timeout, context=self._ssl_context
            ) as response:
                data = json.loads(response.read().decode("utf-8"))
                return int(data.get("time", 0))
        except urllib.error.URLError as e:
            raise NPSAuthError(f"Failed to get server time: {e}") from e
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

        try:
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

            with urllib.request.urlopen(
                req, timeout=self.timeout, context=self._ssl_context
            ) as response:
                response_data = response.read().decode("utf-8")
                result = json.loads(response_data)
                return result

        except urllib.error.HTTPError as e:
            raise NPSAPIError(
                f"HTTP error: {e.code} {e.reason}", status_code=e.code
            ) from e
        except urllib.error.URLError as e:
            raise NPSAPIError(f"URL error: {e.reason}") from e
        except json.JSONDecodeError as e:
            raise NPSAPIError(f"Invalid JSON response: {e}") from e
