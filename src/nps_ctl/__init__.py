"""nps-ctl: A Python library and CLI tool for managing NPS servers.

This package provides:
- NPSClient: API client for a single NPS server
- NPSCluster: Manager for multiple NPS servers
- CLI tool for command-line management
"""

__version__ = "0.1.0"

from nps_ctl.api import NPSClient, NPSCluster

__all__ = ["NPSClient", "NPSCluster", "__version__"]
