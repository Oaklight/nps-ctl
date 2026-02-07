"""NPS API client for managing NPS servers.

This module re-exports all public API components for backward compatibility.
New code should import directly from the specific modules:

- ``nps_ctl.base`` - NPSClient (API client for a single NPS server)
- ``nps_ctl.cluster`` - NPSCluster (multi-server management)
- ``nps_ctl.client_mgmt`` - NPC client management functions
- ``nps_ctl.tunnel`` - Tunnel management functions
- ``nps_ctl.host`` - Host (domain) management functions
- ``nps_ctl.types`` - Type definitions (ClientInfo, TunnelInfo, HostInfo, EdgeConfig)
- ``nps_ctl.exceptions`` - Exception classes (NPSError, NPSAuthError, NPSAPIError)
"""

# Re-export everything for backward compatibility
from nps_ctl.base import NPSClient
from nps_ctl.cluster import NPSCluster
from nps_ctl.exceptions import NPSAPIError, NPSAuthError, NPSError
from nps_ctl.types import ClientInfo, EdgeConfig, HostInfo, TunnelInfo

__all__ = [
    "ClientInfo",
    "EdgeConfig",
    "HostInfo",
    "NPSAPIError",
    "NPSAuthError",
    "NPSClient",
    "NPSCluster",
    "NPSError",
    "TunnelInfo",
]
