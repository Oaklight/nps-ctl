"""CLI helper utilities.

This module provides shared helper functions used across CLI commands,
such as table formatting and configuration path resolution.
"""

from pathlib import Path


def get_default_config_path() -> Path:
    """Get the default configuration file path.

    Searches in order:
    1. ./config/edges.toml
    2. ~/.config/nps-ctl/edges.toml
    3. /etc/nps-ctl/edges.toml

    Returns:
        Path to the configuration file.

    Raises:
        FileNotFoundError: If no configuration file is found.
    """
    paths = [
        Path("config/edges.toml"),
        Path.home() / ".config" / "nps-ctl" / "edges.toml",
        Path("/etc/nps-ctl/edges.toml"),
    ]
    for path in paths:
        if path.exists():
            return path
    raise FileNotFoundError(
        "No configuration file found. Create config/edges.toml or use --config."
    )


def format_table(
    headers: list[str], rows: list[list[str]], widths: list[int] | None = None
) -> str:
    """Format data as a simple ASCII table.

    Args:
        headers: Column headers.
        rows: Table rows.
        widths: Optional column widths (auto-calculated if not provided).

    Returns:
        Formatted table string.
    """
    if widths is None:
        widths = [len(h) for h in headers]
        for row in rows:
            for i, cell in enumerate(row):
                if i < len(widths):
                    widths[i] = max(widths[i], len(str(cell)))

    # Build format string
    fmt = "  ".join(f"{{:<{w}}}" for w in widths)
    lines = [fmt.format(*headers)]
    lines.append("  ".join("-" * w for w in widths))
    for row in rows:
        # Pad row if needed
        padded = list(row) + [""] * (len(headers) - len(row))
        lines.append(fmt.format(*[str(c)[:w] for c, w in zip(padded, widths)]))
    return "\n".join(lines)


def get_template_path() -> Path:
    """Get the path to the templates directory.

    Returns:
        Path to templates directory.
    """
    # Try package templates first (inside src/nps_ctl/templates)
    pkg_templates = Path(__file__).parent.parent / "templates"
    if pkg_templates.exists():
        return pkg_templates

    # Try relative to config
    return Path("templates")
