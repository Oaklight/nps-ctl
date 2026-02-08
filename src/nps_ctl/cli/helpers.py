"""CLI helper utilities.

This module provides shared helper functions used across CLI commands,
such as table formatting and configuration path resolution.
"""

from pathlib import Path
from typing import Any

from rich.console import Console
from rich.table import Table

# Shared console instance for all CLI commands
console = Console()


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
