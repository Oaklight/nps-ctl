"""CLI commands: hosts, add-host - List and manage host mappings."""

import argparse
from typing import Any

from .. import client_mgmt, host
from ..cluster import NPSCluster
from ..exceptions import NPSError
from .helpers import console, create_table, print_error


def cmd_hosts(args: argparse.Namespace) -> int:
    """List host mappings on edge nodes."""
    try:
        cluster = NPSCluster(args.config)
    except FileNotFoundError as e:
        print_error(str(e))
        return 1

    if args.all:
        all_hosts = cluster.get_all_hosts()
        for edge_name, hosts in all_hosts.items():
            edge = cluster.get_edge(edge_name)
            region = edge.region if edge else ""
            console.print(f"\n[bold cyan]=== {edge_name} ({region}) ===[/bold cyan]")
            _print_hosts(hosts)
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
            hosts = host.list_hosts(nps)
            _print_hosts(hosts)
        except NPSError as e:
            print_error(str(e))
            return 1

    return 0


def cmd_add_host(args: argparse.Namespace) -> int:
    """Add a host mapping to edges."""
    try:
        cluster = NPSCluster(args.config)
    except FileNotFoundError as e:
        print_error(str(e))
        return 1

    # Confirm
    if not args.yes:
        if args.edge:
            targets = [args.edge]
        else:
            targets = cluster.edge_names
        console.print(
            f"Will add host [bold]{args.domain}[/bold] -> [bold]{args.target}[/bold] "
            f"to: {', '.join(targets)}"
        )
        console.print(f"Client: [bold]{args.client}[/bold]")
        response = input("Continue? [y/N] ")
        if response.lower() != "y":
            console.print("Aborted.")
            return 0

    if args.edge:
        # Single edge
        nps = cluster.get_client(args.edge)
        if not nps:
            print_error(f"Edge '{args.edge}' not found")
            return 1

        try:
            # Find client
            clients = client_mgmt.list_clients(nps, search=args.client)
            matching = [c for c in clients if c.get("Remark") == args.client]
            if not matching:
                print_error(f"Client '{args.client}' not found on {args.edge}")
                return 1

            client_id = matching[0]["Id"]
            success = host.add_host(
                nps,
                client_id=client_id,
                host=args.domain,
                target=args.target,
                remark=args.remark or "",
            )
            if success:
                console.print(f"[green]✓ Added host to {args.edge}[/green]")
            else:
                console.print(f"[red]✗ Failed to add host to {args.edge}[/red]")
                return 1
        except NPSError as e:
            print_error(str(e))
            return 1
    else:
        # All edges
        results = cluster.broadcast_host(
            client_remark=args.client,
            host_domain=args.domain,
            target=args.target,
            remark=args.remark or "",
        )
        for edge, success in results.items():
            status = "[green]✓[/green]" if success else "[red]✗[/red]"
            console.print(f"{status} {edge}")

    return 0


def _print_hosts(hosts: list[dict[str, Any]]) -> None:
    """Print host list as table."""
    table = create_table()
    table.add_column("ID", style="dim")
    table.add_column("Host", style="bold cyan")
    table.add_column("Target", style="green")
    table.add_column("Client")
    table.add_column("Scheme", style="dim")

    for h in hosts:
        client_info = h.get("Client", {})
        client_name = client_info.get("Remark", "") if client_info else ""
        target = h.get("Target", {})
        target_addr = target.get("TargetStr", "") if target else ""

        table.add_row(
            str(h.get("Id", "")),
            h.get("Host", ""),
            target_addr,
            client_name,
            h.get("Scheme", "all"),
        )

    console.print(table)
