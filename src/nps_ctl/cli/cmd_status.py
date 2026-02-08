"""CLI command: status - Show status of all edge nodes."""

import argparse

from rich.live import Live
from rich.spinner import Spinner

from .. import client_mgmt
from ..cluster import NPSCluster
from ..exceptions import NPSError
from .helpers import console, create_table, print_error


def cmd_status(args: argparse.Namespace) -> int:
    """Show status of all edge nodes."""
    try:
        cluster = NPSCluster(args.config)
    except FileNotFoundError as e:
        print_error(str(e))
        return 1

    # Create table
    table = create_table(title="NPS Edge Status")
    table.add_column("Edge", style="bold")
    table.add_column("Region")
    table.add_column("API URL", style="dim")
    table.add_column("Status")

    # Check status with live display
    with Live(
        Spinner("dots", text="Checking edge status..."), console=console, transient=True
    ):
        for name in cluster.edge_names:
            edge = cluster.get_edge(name)
            nps = cluster.get_client(name)
            if not edge or not nps:
                continue

            try:
                # Try to get clients to verify connection
                client_mgmt.list_clients(nps, limit=1)
                status = "[green]✓ Online[/green]"
            except NPSError:
                status = "[red]✗ Offline[/red]"

            table.add_row(name, edge.region, edge.api_url, status)

    console.print(table)
    return 0
