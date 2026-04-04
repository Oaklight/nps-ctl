"""CLI command: tunnels - List and manage tunnels."""

import argparse

from .. import client_mgmt, tunnel
from ..cluster import NPSCluster
from ..exceptions import NPSError
from ..types import TunnelInfo
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


def _print_tunnels(tunnels: list[TunnelInfo]) -> None:
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


def cmd_tunnel_del(args: argparse.Namespace) -> int:
    """Delete a tunnel from an edge node.

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

    nps = cluster.get_client(args.edge)
    if not nps:
        print_error(f"Edge '{args.edge}' not found")
        return 1

    tunnel_id = args.id

    if not args.yes:
        # Try to fetch tunnel info for confirmation display
        try:
            t = tunnel.get_tunnel(nps, tunnel_id)
            if t:
                target_obj = t.get("Target", {})
                target_str = target_obj.get("TargetStr", "") if target_obj else ""
                console.print(
                    f"Will delete tunnel ID [bold]{tunnel_id}[/bold] "
                    f"({t.get('Mode', '')} port {t.get('Port', '')} "
                    f"-> {target_str}) from [bold]{args.edge}[/bold]"
                )
            else:
                console.print(
                    f"Will delete tunnel ID [bold]{tunnel_id}[/bold] "
                    f"from [bold]{args.edge}[/bold]"
                )
        except NPSError:
            console.print(
                f"Will delete tunnel ID [bold]{tunnel_id}[/bold] "
                f"from [bold]{args.edge}[/bold]"
            )
        response = input("Continue? [y/N] ")
        if response.lower() != "y":
            console.print("Aborted.")
            return 0

    try:
        if tunnel.del_tunnel(nps, tunnel_id):
            console.print(
                f"[green]✓ Deleted tunnel {tunnel_id} from {args.edge}[/green]"
            )
        else:
            console.print(
                f"[red]✗ Failed to delete tunnel {tunnel_id} from {args.edge}[/red]"
            )
            return 1
    except NPSError as e:
        print_error(str(e))
        return 1

    return 0


def cmd_tunnel_edit(args: argparse.Namespace) -> int:
    """Edit a tunnel on an edge node.

    Fetches the current tunnel config, merges with provided overrides,
    and submits the edit.

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

    nps = cluster.get_client(args.edge)
    if not nps:
        print_error(f"Edge '{args.edge}' not found")
        return 1

    tunnel_id = args.id
    new_target = getattr(args, "target", None)
    new_port = getattr(args, "port", None)
    new_remark = getattr(args, "remark", None)

    if not any([new_target, new_port is not None, new_remark]):
        print_error("No changes specified (use --target, -p/--port, or -r)")
        return 1

    try:
        current = tunnel.get_tunnel(nps, tunnel_id)
        if not current:
            print_error(f"Tunnel ID {tunnel_id} not found on {args.edge}")
            return 1

        target_obj = current.get("Target", {})
        client_obj = current.get("Client", {})
        updated_target = new_target or (
            target_obj.get("TargetStr", "") if target_obj else ""
        )
        updated_port = new_port if new_port is not None else current.get("Port", 0)
        updated_remark = (
            new_remark if new_remark is not None else current.get("Remark", "")
        )
        client_id = client_obj.get("Id", 0) if client_obj else 0
        tunnel_type = current.get("Mode", "tcp")

        if not args.yes:
            console.print(f"Editing tunnel ID [bold]{tunnel_id}[/bold] on {args.edge}:")
            if new_target:
                old_target = target_obj.get("TargetStr", "") if target_obj else ""
                console.print(f"  Target: {old_target} -> {new_target}")
            if new_port is not None:
                console.print(f"  Port: {current.get('Port', '')} -> {new_port}")
            if new_remark is not None:
                console.print(f"  Remark: {current.get('Remark', '')} -> {new_remark}")
            response = input("Continue? [y/N] ")
            if response.lower() != "y":
                console.print("Aborted.")
                return 0

        success = tunnel.edit_tunnel(
            nps,
            tunnel_id=tunnel_id,
            client_id=client_id,
            tunnel_type=tunnel_type,
            port=updated_port,
            target=updated_target,
            remark=updated_remark,
        )
        if success:
            console.print(f"[green]✓ Updated tunnel {tunnel_id} on {args.edge}[/green]")
        else:
            console.print(f"[red]✗ Failed to update tunnel on {args.edge}[/red]")
            return 1
    except NPSError as e:
        print_error(str(e))
        return 1

    return 0


def cmd_tunnel_start(args: argparse.Namespace) -> int:
    """Start a tunnel on an edge node.

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

    nps = cluster.get_client(args.edge)
    if not nps:
        print_error(f"Edge '{args.edge}' not found")
        return 1

    try:
        if tunnel.start_tunnel(nps, args.id):
            console.print(f"[green]✓ Started tunnel {args.id} on {args.edge}[/green]")
        else:
            console.print(
                f"[red]✗ Failed to start tunnel {args.id} on {args.edge}[/red]"
            )
            return 1
    except NPSError as e:
        print_error(str(e))
        return 1

    return 0


def cmd_tunnel_stop(args: argparse.Namespace) -> int:
    """Stop a tunnel on an edge node.

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

    nps = cluster.get_client(args.edge)
    if not nps:
        print_error(f"Edge '{args.edge}' not found")
        return 1

    try:
        if tunnel.stop_tunnel(nps, args.id):
            console.print(f"[green]✓ Stopped tunnel {args.id} on {args.edge}[/green]")
        else:
            console.print(
                f"[red]✗ Failed to stop tunnel {args.id} on {args.edge}[/red]"
            )
            return 1
    except NPSError as e:
        print_error(str(e))
        return 1

    return 0
