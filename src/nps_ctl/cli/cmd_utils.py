"""CLI commands: generate-auth-key - Utility commands."""

import argparse

from ..utils import generate_auth_key


def cmd_generate_auth_key(args: argparse.Namespace) -> int:
    """Generate a random auth key for NPS API authentication.

    Args:
        args: Command arguments containing length parameter.

    Returns:
        Exit code (0 for success).
    """
    auth_key = generate_auth_key(args.length)
    print(auth_key)
    return 0
