"""CLI helper utilities.

This module provides shared helper functions used across CLI commands,
such as table formatting, configuration path resolution, and shared
argument definitions for the CLI parser.
"""

import argparse
from pathlib import Path
from typing import Any

from rich.table import Table

from ..logging import FlushingConsole, flush_output

# Shared console instance for all CLI commands
# Use force_terminal=True to ensure immediate output through proxies
# Use FlushingConsole to auto-flush after every print
console = FlushingConsole(force_terminal=True)

# Re-export flush_output for convenience
__all__ = ["console", "flush_output", "FlushingConsole"]


def get_clients_config_path(config_path: Path) -> Path:
    """Derive the clients.toml path from the edges config path.

    The clients.toml is expected to be in the same directory as the
    edges config file (edges.toml).

    Args:
        config_path: Path to the edges config file (edges.toml).

    Returns:
        Path to the clients.toml file.
    """
    return config_path.parent / "clients.toml"


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


def create_table(
    title: str | None = None,
    headers: list[str] | None = None,
    show_header: bool = True,
    box_style: Any = None,
) -> Table:
    """Create a rich Table with consistent styling.

    Args:
        title: Optional table title.
        headers: Column headers to add.
        show_header: Whether to show the header row.
        box_style: Box style for the table (default: ROUNDED).

    Returns:
        Configured Table instance.
    """
    from rich.box import ROUNDED

    table = Table(
        title=title,
        show_header=show_header,
        header_style="bold cyan",
        box=box_style or ROUNDED,
    )

    if headers:
        for header in headers:
            table.add_column(header)

    return table


def print_table(
    headers: list[str],
    rows: list[list[str]],
    title: str | None = None,
) -> None:
    """Print a table using rich.

    Args:
        headers: Column headers.
        rows: Table rows.
        title: Optional table title.
    """
    table = create_table(title=title, headers=headers)
    for row in rows:
        table.add_row(*[str(cell) for cell in row])
    console.print(table)


def print_error(message: str) -> None:
    """Print an error message in red.

    Args:
        message: Error message to print.
    """
    console.print(f"[red]Error: {message}[/red]")


def print_success(message: str) -> None:
    """Print a success message in green.

    Args:
        message: Success message to print.
    """
    console.print(f"[green]✓ {message}[/green]")


def print_warning(message: str) -> None:
    """Print a warning message in yellow.

    Args:
        message: Warning message to print.
    """
    console.print(f"[yellow]⚠ {message}[/yellow]")


def print_info(message: str) -> None:
    """Print an info message in blue.

    Args:
        message: Info message to print.
    """
    console.print(f"[blue]{message}[/blue]")


def format_status(success: bool) -> str:
    """Format a status indicator.

    Args:
        success: Whether the status is successful.

    Returns:
        Formatted status string with color.
    """
    return "[green]✓[/green]" if success else "[red]✗[/red]"


# ---- Shared argument factory functions ----


def add_edge_argument(
    parser: argparse.ArgumentParser,
    *,
    required: bool = False,
    nargs: str | int | None = None,
    help_text: str | None = None,
) -> None:
    """Add the standard -e/--edge argument to a parser.

    Args:
        parser: The argument parser to add the argument to.
        required: Whether the argument is required.
        nargs: Number of arguments (e.g., "+" for one or more).
        help_text: Custom help text. Defaults based on required.
    """
    default_help = (
        "Edge name (required, IDs are edge-specific)"
        if required
        else "Edge name (default: all edges)"
    )
    kwargs: dict[str, Any] = {
        "help": help_text or default_help,
    }
    if required:
        kwargs["required"] = True
    if nargs is not None:
        kwargs["nargs"] = nargs
    parser.add_argument("-e", "--edge", **kwargs)


def add_client_argument(
    parser: argparse.ArgumentParser,
    *,
    required: bool = False,
    help_text: str | None = None,
) -> None:
    """Add the standard -c/--client argument to a parser.

    Args:
        parser: The argument parser to add the argument to.
        required: Whether the argument is required.
        help_text: Custom help text.
    """
    kwargs: dict[str, Any] = {
        "help": help_text or "Client name (remark) or numeric ID",
    }
    if required:
        kwargs["required"] = True
    parser.add_argument("-c", "--client", **kwargs)


def add_yes_argument(parser: argparse.ArgumentParser) -> None:
    """Add the standard -y/--yes argument to a parser.

    Args:
        parser: The argument parser to add the argument to.
    """
    parser.add_argument(
        "-y",
        "--yes",
        action="store_true",
        help="Skip confirmation prompts",
    )


def add_verbose_argument(parser: argparse.ArgumentParser) -> None:
    """Add the standard -v/--verbose argument to a parser.

    Args:
        parser: The argument parser to add the argument to.
    """
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Show detailed output",
    )


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
