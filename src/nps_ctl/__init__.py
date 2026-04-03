"""nps-ctl: A Python library and CLI tool for managing NPS servers.

This package provides:
- NPSClient: API client for a single NPS server
- NPSCluster: Manager for multiple NPS servers
- Modular API functions: client_mgmt, tunnel, host
- CLI tool for command-line management
- Enhanced logging with configure_logging

Modules:
    base: NPSClient class (authentication and HTTP requests)
    cluster: NPSCluster class (multi-server management)
    client_mgmt: NPC client management functions
    tunnel: Tunnel management functions
    host: Host (domain) management functions
    types: Type definitions (ClientInfo, TunnelInfo, HostInfo, EdgeConfig)
    exceptions: Exception classes (NPSError, NPSAuthError, NPSAPIError)
    deploy: Deployment functions (install, uninstall via SSH)
    utils: Utility functions (auth key generation)
    logging: Logging configuration and utilities
"""

__version__ = "0.3.0"

from .base import NPSClient
from .cluster import NPSCluster
from .logging import configure_logging, set_log_level

__all__ = [
    "NPSClient",
    "NPSCluster",
    "__version__",
    "configure_logging",
    "set_log_level",
]
