"""CLI command: clients - List and manage NPC clients."""

import argparse
from typing import Any

from .. import client_mgmt
from ..cluster import NPSCluster
from ..exceptions import NPSError
from .helpers import console, create_table, print_error


def cmd_clients(args: argparse.Namespace) -> int:
    """List clients on edge nodes."""
    try:
        cluster = NPSCluster(args.config)
    except FileNotFoundError as e:
        print_error(str(e))
        return 1

    if args.all:
        # Show clients from all edges
        all_clients = cluster.get_all_clients()
        for edge_name, clients in all_clients.items():
            edge = cluster.get_edge(edge_name)
            region = edge.region if edge else ""
            console.print(f"\n[bold cyan]=== {edge_name} ({region}) ===[/bold cyan]")
            _print_clients(clients)
    else:
        # Show clients from specific edge
        edge_name = args.edge
        if not edge_name:
            # Use first edge as default
            edge_name = cluster.edge_names[0] if cluster.edge_names else None
            if not edge_name:
                print_error("No edges configured")
                return 1

        nps = cluster.get_client(edge_name)
        if not nps:
            print_error(f"Edge '{edge_name}' not found")
            return 1

        try:
            clients = client_mgmt.list_clients(nps)
            _print_clients(clients)
        except NPSError as e:
            print_error(str(e))
            return 1

    return 0


def _print_clients(clients: list[dict[str, Any]]) -> None:
    """Print client list as table."""
    table = create_table()
    table.add_column("ID", style="dim")
    table.add_column("Remark", style="bold")
    table.add_column("VKey", style="dim")
    table.add_column("Status")
    table.add_column("Conn", justify="right")

    for c in clients:
        is_connected = c.get("IsConnect", False)
        status = (
            "[green]Connected[/green]" if is_connected else "[red]Disconnected[/red]"
        )
        vkey = c.get("VerifyKey", "")
        vkey_display = vkey[:20] + "..." if len(vkey) > 20 else vkey

        table.add_row(
            str(c.get("Id", "")),
            c.get("Remark", ""),
            vkey_display,
            status,
            str(c.get("NowConn", 0)),
        )

    console.print(table)
