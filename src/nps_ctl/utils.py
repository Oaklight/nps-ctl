"""Utility functions for NPS management.

This module provides utility functions that can be used independently
or as part of the nps-ctl CLI.
"""

import base64
import secrets


def generate_auth_key(length: int = 43) -> str:
    """Generate a random auth key for NPS API authentication.

    The generated key uses URL-safe base64 encoding, which is compatible
    with NPS auth_key requirements.

    Args:
        length: Length of the auth key. Default is 43, matching NPS default.

    Returns:
        A random URL-safe base64 encoded string of the specified length.

    Examples:
        >>> key = generate_auth_key()
        >>> len(key)
        43
        >>> key = generate_auth_key(32)
        >>> len(key)
        32
    """
    # Generate random bytes and encode as URL-safe base64
    # base64 encoding produces 4 characters for every 3 bytes
    num_bytes = (length * 3 + 3) // 4
    random_bytes = secrets.token_bytes(num_bytes)
    return base64.urlsafe_b64encode(random_bytes).decode("ascii")[:length]
