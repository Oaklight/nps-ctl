"""Type definitions for NPS API.

This module defines TypedDict types for NPS API responses and
dataclass configurations.
"""

from dataclasses import dataclass
from typing import Any, TypedDict


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
    """Configuration for a single NPS edge node."""

    name: str
    api_url: str
    auth_key: str
    region: str = ""
    ssh_host: str = ""
