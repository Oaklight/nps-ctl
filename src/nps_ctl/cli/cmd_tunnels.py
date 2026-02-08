"""CLI command: tunnels - List and manage tunnels."""

import argparse
from typing import Any

from .. import client_mgmt, tunnel
from ..cluster import NPSCluster
from ..exceptions import NPSError
from .helpers import console, create_table, print_error


def cmd_tunnels(args: argparse.Namespace) -> int:
    """List tunnels on edge nodes."""
    try:
        cluster = NPSCluster(args.config)
    except FileNotFoundError as e:
        print_error(str(e))
        return 1

    tunnel_type = getattr(args, "type", "") or ""

    if args.all:
        all_tunnels = cluster.get_all_tunnels()
        for edge_name, tunnels in all_tunnels.items():
            edge = cluster.get_edge(edge_name)
            region = edge.region if edge else ""
            console.print(f"\n[bold cyan]=== {edge_name} ({region}) ===[/bold cyan]")
            _print_tunnels(tunnels)
    else:
        edge_name = args.edge
        if not edge_name:
            edge_name = cluster.edge_names[0] if cluster.edge_names else None
            if not edge_name:
                print_error("No edges configured")
                return 1

        nps = cluster.get_client(edge_name)
        if not nps:
            print_error(f"Edge '{edge_name}' not found")
            return 1

        try:
            tunnels = tunnel.list_tunnels(nps, tunnel_type=tunnel_type)
            _print_tunnels(tunnels)
        except NPSError as e:
            print_error(str(e))
            return 1

    return 0


def cmd_add_tunnel(args: argparse.Namespace) -> int:
    """Add a tunnel to an edge."""
    try:
        cluster = NPSCluster(args.config)
    except FileNotFoundError as e:
        print_error(str(e))
        return 1

    edge_name = args.edge
    if not edge_name:
        edge_name = cluster.edge_names[0] if cluster.edge_names else None
        if not edge_name:
            print_error("No edges configured")
            return 1

    nps = cluster.get_client(edge_name)
    if not nps:
        print_error(f"Edge '{edge_name}' not found")
        return 1

    # Confirm
    if not args.yes:
        console.print(
            f"Will add [bold]{args.type}[/bold] tunnel on [bold]{edge_name}[/bold]"
        )
        console.print(
            f"Client: [bold]{args.client}[/bold], Port: [bold]{args.port}[/bold], "
            f"Target: [bold]{args.target or 'N/A'}[/bold]"
        )
        response = input("Continue? [y/N] ")
        if response.lower() != "y":
            console.print("Aborted.")
            return 0

    try:
        # Find client
        clients = client_mgmt.list_clients(nps, search=args.client)
        matching = [c for c in clients if c.get("Remark") == args.client]
        if not matching:
            print_error(f"Client '{args.client}' not found")
            return 1

        client_id = matching[0]["Id"]
        success = tunnel.add_tunnel(
            nps,
            client_id=client_id,
            tunnel_type=args.type,
            port=args.port,
            target=args.target or "",
            remark=args.remark or "",
        )
        if success:
            console.print(f"[green]✓ Added tunnel to {edge_name}[/green]")
        else:
            console.print("[red]✗ Failed to add tunnel[/red]")
            return 1
    except NPSError as e:
        print_error(str(e))
        return 1

    return 0


def _print_tunnels(tunnels: list[dict[str, Any]]) -> None:
    """Print tunnel list as table."""
    table = create_table()
    table.add_column("ID", style="dim")
    table.add_column("Type", style="bold magenta")
    table.add_column("Port", style="cyan", justify="right")
    table.add_column("Target", style="green")
    table.add_column("Client")
    table.add_column("Status")

    for t in tunnels:
        client_info = t.get("Client", {})
        client_name = client_info.get("Remark", "") if client_info else ""
        is_running = t.get("RunStatus", False)
        status = "[green]Running[/green]" if is_running else "[red]Stopped[/red]"
        target = t.get("Target", {})
        target_addr = target.get("TargetStr", "") if target else t.get("TargetAddr", "")

        table.add_row(
            str(t.get("Id", "")),
            t.get("Mode", ""),
            str(t.get("Port", "")),
            target_addr,
            client_name,
            status,
        )

    console.print(table)
