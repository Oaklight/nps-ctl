"""Type definitions for NPS API.

This module defines TypedDict types for NPS API responses and
dataclass configurations.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Generic, TypedDict, TypeVar

# Type alias for client ID mapping (source_id -> target_id)
ClientIdMapping = dict[int, int]

T = TypeVar("T")


class EdgeResults(dict[str, list[T]], Generic[T]):
    """Per-edge fetch results with failure information.

    Behaves like the previous ``dict[str, list[T]]`` return value so existing
    callers keep working. Failed edges are present with an empty list, and
    their reason is recorded in :attr:`errors`.

    Attributes:
        errors: Mapping of edge name to the error message for edges whose
            fetch failed.
    """

    def __init__(
        self,
        *args: Any,
        errors: Mapping[str, str] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.errors: dict[str, str] = dict(errors or {})

    @property
    def failed_edges(self) -> list[str]:
        """Edge names whose fetch failed, in result order."""
        return [name for name in self if name in self.errors]

    @property
    def ok_edges(self) -> list[str]:
        """Edge names whose fetch succeeded, in result order."""
        return [name for name in self if name not in self.errors]


class ClientInfo(TypedDict, total=False):
    """Client information from NPS API."""

    Id: int
    VerifyKey: str
    Addr: str
    Remark: str
    Status: bool
    IsConnect: bool
    RateLimit: int
    Flow: dict[str, Any]
    MaxConn: int
    NowConn: int
    WebUserName: str
    WebPassword: str
    ConfigConnAllow: bool
    Cnf: dict[str, Any]


class TunnelInfo(TypedDict, total=False):
    """Tunnel information from NPS API."""

    Id: int
    Port: int
    ServerIp: str
    Mode: str
    Status: bool
    RunStatus: bool
    Client: ClientInfo
    Ports: str
    Flow: dict[str, Any]
    Password: str
    Remark: str
    TargetAddr: str
    NoStore: bool
    LocalPath: str
    StripPre: str
    Target: dict[str, Any]


class HostInfo(TypedDict, total=False):
    """Host (domain) information from NPS API."""

    Id: int
    Host: str
    HeaderChange: str
    HostChange: str
    Location: str
    Remark: str
    Scheme: str
    CertFilePath: str
    KeyFilePath: str
    NoStore: bool
    IsClose: bool
    Flow: dict[str, Any]
    Client: ClientInfo
    Target: dict[str, Any]
    AutoHttps: bool


@dataclass
class EdgeConfig:
    """Configuration for a single NPS edge node.

    Supports both legacy auth (auth_key) and modern auth (username/password
    or platform_token). When api_mode is "auto" (default), the client probes
    the server to determine which API is available.
    """

    name: str
    api_url: str
    auth_key: str = ""
    region: str = ""
    ssh_host: str = ""
    # Modern API credentials (v0.35.0+)
    username: str = ""
    password: str = ""
    platform_token: str = ""
    api_mode: str = "auto"  # "legacy" | "modern" | "auto"


@dataclass
class NPCClientConfig:
    """Configuration for a single NPC client to be deployed."""

    name: str
    ssh_host: str
    edges: list[str]
    vkey: str = ""
    remark: str = ""
    conn_type: str = "tls"
    ssh_user: str = ""
    http_proxy: str = ""

    def __post_init__(self) -> None:
        """Set default remark to name if not provided."""
        if not self.remark:
            self.remark = self.name
