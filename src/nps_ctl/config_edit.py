"""Comment-preserving edits to edges.toml.

``tomllib`` is read-only and the config files are hand-maintained with
comments, so edits are applied as small text changes and the result is
re-parsed before it is written.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
import tomllib
from pathlib import Path

_TABLE_HEADER = re.compile(r"^\s*\[")
_PRIMARY_LINE = re.compile(r"^\s*primary\s*=")


def _toml_string(value: str) -> str:
    """Quote a value as a TOML basic string."""
    return json.dumps(value, ensure_ascii=False)


def _validated(text: str) -> dict:
    """Parse edited text, raising ValueError if the edit broke the file."""
    try:
        return tomllib.loads(text)
    except tomllib.TOMLDecodeError as e:
        raise ValueError(f"Edit would produce invalid TOML: {e}") from e


def set_primary_text(text: str, edge_name: str) -> str:
    """Return config text with the top-level ``primary`` key set.

    An existing top-level ``primary`` line is replaced in place. Otherwise
    the key is inserted before the first table header, above any comment
    block that introduces that header.

    Args:
        text: Current edges.toml content.
        edge_name: Edge to mark as primary.

    Returns:
        Updated content.

    Raises:
        ValueError: If the result is not valid TOML.
    """
    lines = text.splitlines(keepends=True)
    new_line = f"primary = {_toml_string(edge_name)}\n"

    first_table = next(
        (i for i, line in enumerate(lines) if _TABLE_HEADER.match(line)),
        len(lines),
    )
    for i in range(first_table):
        if _PRIMARY_LINE.match(lines[i]):
            lines[i] = new_line
            break
    else:
        insert_at = first_table
        while insert_at > 0 and lines[insert_at - 1].lstrip().startswith("#"):
            insert_at -= 1
        block = [new_line]
        if insert_at > 0 and lines[insert_at - 1].strip():
            block.insert(0, "\n")
        if insert_at < len(lines):
            block.append("\n")
        lines[insert_at:insert_at] = block

    result = "".join(lines)
    _validated(result)
    return result


def append_edge_text(
    text: str,
    *,
    name: str,
    api_url: str,
    auth_key: str = "",
    region: str = "",
    ssh_host: str = "",
) -> str:
    """Return config text with a new ``[[edges]]`` entry appended.

    Args:
        text: Current edges.toml content.
        name: Edge name; must not already exist.
        api_url: Edge API URL.
        auth_key: Legacy API auth key.
        region: Display region.
        ssh_host: SSH host alias for install/upgrade commands.

    Returns:
        Updated content.

    Raises:
        ValueError: If the edge already exists or the result is invalid.
    """
    existing = {edge.get("name") for edge in _validated(text).get("edges", [])}
    if name in existing:
        raise ValueError(f"Edge '{name}' already exists")

    fields = [("name", name), ("api_url", api_url)]
    for key, value in (
        ("auth_key", auth_key),
        ("region", region),
        ("ssh_host", ssh_host),
    ):
        if value:
            fields.append((key, value))
    block = "[[edges]]\n" + "".join(
        f"{key} = {_toml_string(value)}\n" for key, value in fields
    )

    prefix = text
    if prefix and not prefix.endswith("\n"):
        prefix += "\n"
    if prefix.strip():
        prefix += "\n"
    result = prefix + block
    _validated(result)
    return result


def _write_atomic(path: Path, text: str) -> None:
    """Replace ``path`` with ``text`` atomically, keeping its file mode.

    The file holds every edge's auth key, so a crash or full disk must never
    leave it truncated.
    """
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        if path.exists():
            os.chmod(tmp, path.stat().st_mode & 0o777)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def set_primary(path: str | Path, edge_name: str) -> None:
    """Set the primary edge in an edges.toml file."""
    path = Path(path)
    _write_atomic(path, set_primary_text(path.read_text(encoding="utf-8"), edge_name))


def append_edge(path: str | Path, **fields: str) -> None:
    """Append an edge entry to an edges.toml file (see append_edge_text)."""
    path = Path(path)
    _write_atomic(path, append_edge_text(path.read_text(encoding="utf-8"), **fields))
