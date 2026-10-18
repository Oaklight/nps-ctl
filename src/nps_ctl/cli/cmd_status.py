"""CLI command: status - Show status of all edge nodes."""

import argparse

from rich.live import Live
from rich.spinner import Spinner

from .. import client_mgmt
from ..cluster import NPSCluster
from ..exceptions import NPSError
from .helpers import console, create_table, print_error


def cmd_edge_list(args: argparse.Namespace) -> int:
    """List configured edges without contacting them."""
    try:
        cluster = NPSCluster(args.config)
    except FileNotFoundError as e:
        print_error(str(e))
        return 1

    table = create_table(title="NPS Edges")
    table.add_column("Edge", style="bold")
    table.add_column("Region")
    table.add_column("API URL", style="dim")
    table.add_column("SSH Host")

    for name in cluster.edge_names:
        edge = cluster.get_edge(name)
        if not edge:
            continue
        table.add_row(name, edge.region, edge.api_url, edge.ssh_host or "-")

    console.print(table)
    console.print(f"[dim]{len(cluster.edge_names)} edges configured[/dim]")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    """Show status of all edge nodes."""
    try:
        cluster = NPSCluster(args.config)
    except FileNotFoundError as e:
        print_error(str(e))
        return 1

    if not cluster.edge_names:
        print_error("No edges configured")
        return 1

    # Create table
    table = create_table(title="NPS Edge Status")
    table.add_column("Edge", style="bold")
    table.add_column("Region")
    table.add_column("API URL", style="dim")
    table.add_column("Status")

    # Check status with live display
    online = 0
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
                online += 1
            except NPSError:
                status = "[red]✗ Offline[/red]"

            table.add_row(name, edge.region, edge.api_url, status)

    console.print(table)
    total = len(cluster.edge_names)
    console.print(f"[dim]{online}/{total} edges online[/dim]")
    return 0 if online == total else 1
