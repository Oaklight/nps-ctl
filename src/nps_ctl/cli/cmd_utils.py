"""CLI commands: utility commands (auth key, password hashing)."""

import argparse
import getpass
import os

from ..utils import generate_auth_key
from ..web_auth import PBKDF2_ITERATIONS, hash_password


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


def cmd_hash_password(args: argparse.Namespace) -> int:
    """Print a PBKDF2 hash for a dashboard users file.

    The plaintext password is read from ``NPS_WEB_PASSWORD`` or prompted for
    without echo, so it never appears in argv or shell history.

    Args:
        args: Command arguments (optional ``iterations``).

    Returns:
        Exit code.
    """
    password = os.environ.get("NPS_WEB_PASSWORD", "")
    if not password:
        try:
            password = getpass.getpass("Dashboard password: ")
            confirm = getpass.getpass("Repeat password: ")
        except EOFError:
            print("Error: No TTY for the password prompt; set NPS_WEB_PASSWORD")
            return 2
        if password != confirm:
            print("Error: Passwords do not match")
            return 2
    if not password:
        print("Error: Password cannot be empty")
        return 2

    iterations = getattr(args, "iterations", None) or PBKDF2_ITERATIONS
    try:
        encoded = hash_password(password, iterations=iterations)
    except ValueError as e:
        print(f"Error: {e}")
        return 2
    print(encoded)
    return 0
