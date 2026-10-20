"""Authentication helpers for the web dashboard.

Passwords are stored as PBKDF2-HMAC-SHA256 hashes in a small TOML file:

    [[users]]
    name = "alice"
    password_hash = "pbkdf2_sha256$260000$<salt-b64>$<hash-b64>"
    role = "operator"   # or "viewer"

Use ``nps-ctl util hash-password`` to generate the hash without putting the
plaintext password in shell history.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import logging
import secrets
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

PBKDF2_PREFIX = "pbkdf2_sha256"
PBKDF2_ITERATIONS = 260_000
MIN_ITERATIONS = 10_000
MAX_ITERATIONS = 10_000_000
ROLES = {"viewer", "operator"}


@dataclass(frozen=True)
class WebUser:
    """One dashboard account."""

    name: str
    password_hash: str
    role: str = "viewer"

    @property
    def can_write(self) -> bool:
        """Whether this user may run dashboard actions."""
        return self.role == "operator"


def hash_password(password: str, *, iterations: int = PBKDF2_ITERATIONS) -> str:
    """Hash a password for a users file.

    Args:
        password: Plaintext password; never stored.
        iterations: PBKDF2 iteration count.

    Returns:
        ``pbkdf2_sha256$iterations$salt$hash`` with base64 salt and digest.

    Raises:
        ValueError: If the password is empty or the iteration count is invalid.
    """
    if not password:
        raise ValueError("Password cannot be empty")
    if not MIN_ITERATIONS <= iterations <= MAX_ITERATIONS:
        raise ValueError(
            f"iterations must be between {MIN_ITERATIONS} and {MAX_ITERATIONS}"
        )
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iterations)
    return (
        f"{PBKDF2_PREFIX}${iterations}$"
        f"{base64.b64encode(salt).decode()}${base64.b64encode(digest).decode()}"
    )


def _parse_hash(encoded: str) -> tuple[int, bytes, bytes] | None:
    """Parse a stored hash, returning None for anything malformed."""
    try:
        prefix, iterations_text, salt_text, digest_text = encoded.split("$")
        iterations = int(iterations_text)
        salt = base64.b64decode(salt_text, validate=True)
        digest = base64.b64decode(digest_text, validate=True)
    except (ValueError, binascii.Error, TypeError):
        return None
    if prefix != PBKDF2_PREFIX:
        return None
    if not MIN_ITERATIONS <= iterations <= MAX_ITERATIONS:
        return None
    if not salt or len(digest) != hashlib.sha256().digest_size:
        return None
    return iterations, salt, digest


def verify_password(password: str, encoded: str) -> bool:
    """Verify a password against a stored hash in constant time."""
    parsed = _parse_hash(encoded)
    if parsed is None:
        return False
    iterations, salt, expected = parsed
    actual = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iterations)
    return hmac.compare_digest(actual, expected)


def load_users_file(path: str | Path) -> dict[str, WebUser]:
    """Load dashboard users from a TOML file.

    Args:
        path: Path to the users file.

    Returns:
        Mapping of username to :class:`WebUser`, in file order.

    Raises:
        OSError: If the file cannot be read.
        ValueError: If the file is malformed, has duplicate names, an invalid
            role, or an invalid password hash.
    """
    users_path = Path(path)
    with open(users_path, "rb") as f:
        config = tomllib.load(f)

    entries = config.get("users")
    if not isinstance(entries, list) or not entries:
        raise ValueError("users file must contain at least one [[users]] entry")

    users: dict[str, WebUser] = {}
    for index, entry in enumerate(entries, 1):
        if not isinstance(entry, dict):
            raise ValueError(f"users entry {index} must be a table")
        name = str(entry.get("name", "")).strip()
        if not name:
            raise ValueError(f"users entry {index} is missing 'name'")
        if name in users:
            raise ValueError(f"duplicate user '{name}'")
        encoded = entry.get("password_hash", "")
        if not isinstance(encoded, str) or _parse_hash(encoded) is None:
            raise ValueError(f"user '{name}' has an invalid password_hash")
        role = str(entry.get("role", "viewer")).strip().lower()
        if role not in ROLES:
            raise ValueError(
                f"user '{name}' has invalid role '{role}'; use one of "
                f"{', '.join(sorted(ROLES))}"
            )
        users[name] = WebUser(name=name, password_hash=encoded, role=role)

    try:
        mode = users_path.stat().st_mode & 0o777
    except OSError:
        mode = 0
    if mode & 0o077:
        logger.warning(
            "Users file %s is readable by group/other (mode %o); restrict it to 0600",
            users_path,
            mode,
        )
    return users


def users_from_credentials(username: str, password: str) -> dict[str, WebUser]:
    """Build a single operator user for ``--username/--password`` mode."""
    return {
        username: WebUser(
            name=username,
            password_hash=hash_password(password),
            role="operator",
        )
    }


def describe_users(users: dict[str, WebUser]) -> dict[str, Any]:
    """Return non-sensitive user metadata for display/logging."""
    return {
        "count": len(users),
        "operators": sum(1 for user in users.values() if user.can_write),
        "viewers": sum(1 for user in users.values() if not user.can_write),
    }
