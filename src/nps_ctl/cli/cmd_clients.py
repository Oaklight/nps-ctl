"""CLI command: clients - List and manage NPC clients."""

import argparse

from .. import client_mgmt
from ..cluster import NPSCluster
from ..exceptions import NPSError
from ..types import ClientInfo
from .helpers import (
    build_edge_results_payload,
    console,
    create_table,
    edge_region,
    print_edge_summary,
    print_error,
    print_json,
    resolve_write_edges,
    validate_read_target,
)


def cmd_clients(args: argparse.Namespace) -> int:
    """List clients on edge nodes."""
    json_mode = getattr(args, "json", False)
    try:
        cluster = NPSCluster(args.config)
    except FileNotFoundError as e:
        if json_mode:
            print_json({"error": str(e)})
        else:
            print_error(str(e))
        return 1

    target_error = validate_read_target(args)
    if target_error is not None:
        if json_mode:
            print_json({"error": target_error})
        else:
            print_error(target_error)
        return 2

    edge_name = getattr(args, "edge", None)
    if edge_name:
        nps = cluster.get_client(edge_name)
        if not nps:
            message = f"Edge '{edge_name}' not found"
            if json_mode:
                print_json({"error": message})
            else:
                print_error(message)
            return 1

        try:
            clients = client_mgmt.list_clients(nps)
        except NPSError as e:
            if json_mode:
                print_json(
                    build_edge_results_payload(
                        {edge_name: []},
                        {edge_name: str(e)},
                        lambda name: edge_region(cluster, name),
                    )
                )
            else:
                print_error(str(e))
            return 1

        if json_mode:
            print_json(
                build_edge_results_payload(
                    {edge_name: clients},
                    {},
                    lambda name: edge_region(cluster, name),
                )
            )
            return 0

        edge = cluster.get_edge(edge_name)
        region = edge.region if edge else ""
        console.print(f"\n[bold cyan]=== {edge_name} ({region}) ===[/bold cyan]")
        _print_clients(clients)
        return 0

    all_clients = cluster.get_all_clients()
    if json_mode:
        print_json(
            build_edge_results_payload(
                all_clients,
                all_clients.errors,
                lambda name: edge_region(cluster, name),
            )
        )
        return 1 if all_clients.errors else 0

    for edge_name, clients in all_clients.items():
        edge = cluster.get_edge(edge_name)
        region = edge.region if edge else ""
        if edge_name in all_clients.errors:
            console.print(
                f"\n[red]✗ {edge_name} ({region}): "
                f"{all_clients.errors[edge_name]}[/red]"
            )
            continue
        console.print(f"\n[bold cyan]=== {edge_name} ({region}) ===[/bold cyan]")
        _print_clients(clients)

    return print_edge_summary(all_clients, all_clients.errors)


def _print_clients(clients: list[ClientInfo]) -> None:
    """Print client list as table."""
    table = create_table()
    table.add_column("ID", style="dim")
    table.add_column("Remark", style="bold", overflow="fold")
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

    Supports deletion by --id (single edge) or -r/--remark (multi-edge).

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
    client_name = getattr(args, "remark", None)

    # --id requires -e
    if client_id is not None and getattr(args, "all", False):
        print_error("--id targets a single edge; use -e/--edge, not -a/--all")
        return 2
    if client_id is not None and not args.edge:
        print_error("--id requires -e/--edge (IDs are edge-specific)")
        return 2

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
        edges, code = resolve_write_edges(args, cluster.edge_names)
        if edges is None:
            return code

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
