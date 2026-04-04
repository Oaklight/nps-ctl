"""CLI command: clients - List and manage NPC clients."""

import argparse

from .. import client_mgmt
from ..cluster import NPSCluster
from ..exceptions import NPSError
from ..types import ClientInfo
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


def _print_clients(clients: list[ClientInfo]) -> None:
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


def cmd_client_del(args: argparse.Namespace) -> int:
    """Delete a client from edge node(s).

    Supports deletion by --id (single edge) or --name (multi-edge).

    Args:
        args: Parsed command line arguments.

    Returns:
        Exit code.
    """
    try:
        cluster = NPSCluster(args.config)
    except FileNotFoundError as e:
        print_error(str(e))
        return 1

    client_id = getattr(args, "id", None)
    client_name = getattr(args, "name", None)

    # --id requires -e
    if client_id is not None and not args.edge:
        print_error("--id requires -e/--edge (IDs are edge-specific)")
        return 1

    if client_id is not None:
        # Delete by ID on a single edge
        nps = cluster.get_client(args.edge)
        if not nps:
            print_error(f"Edge '{args.edge}' not found")
            return 1

        if not args.yes:
            console.print(
                f"Will delete client ID [bold]{client_id}[/bold] "
                f"from [bold]{args.edge}[/bold]"
            )
            response = input("Continue? [y/N] ")
            if response.lower() != "y":
                console.print("Aborted.")
                return 0

        try:
            if client_mgmt.del_client(nps, client_id):
                console.print(
                    f"[green]✓ Deleted client {client_id} from {args.edge}[/green]"
                )
            else:
                console.print(
                    f"[red]✗ Failed to delete client {client_id} from {args.edge}[/red]"
                )
                return 1
        except NPSError as e:
            print_error(str(e))
            return 1
    else:
        # Delete by name across edge(s)
        assert client_name is not None  # guaranteed by mutually exclusive group
        edges = [args.edge] if args.edge else cluster.edge_names
        if not edges:
            print_error("No edges configured")
            return 1

        if not args.yes:
            console.print(
                f"Will delete client [bold]{client_name}[/bold] "
                f"from: {', '.join(edges)}"
            )
            response = input("Continue? [y/N] ")
            if response.lower() != "y":
                console.print("Aborted.")
                return 0

        has_error = False
        for edge_name in edges:
            nps = cluster.get_client(edge_name)
            if not nps:
                console.print(f"[red]✗ {edge_name}: edge not found[/red]")
                has_error = True
                continue
            try:
                clients = client_mgmt.list_clients(nps, search=client_name)
                matching = [c for c in clients if c.get("Remark") == client_name]
                if not matching:
                    console.print(f"[dim]- {edge_name}: not found, skipping[/dim]")
                    continue
                cid = matching[0]["Id"]
                if client_mgmt.del_client(nps, cid):
                    console.print(f"[green]✓ {edge_name}: deleted (ID {cid})[/green]")
                else:
                    console.print(f"[red]✗ {edge_name}: delete failed[/red]")
                    has_error = True
            except NPSError as e:
                console.print(f"[red]✗ {edge_name}: {e}[/red]")
                has_error = True

        if has_error:
            return 1

    return 0
