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
            edge = cluster.get_edge(edge_name)
            region = edge.region if edge else ""
            console.print(f"\n[bold cyan]=== {edge_name} ({region}) ===[/bold cyan]")
            tunnels = tunnel.list_tunnels(nps, tunnel_type=tunnel_type)
            _print_tunnels(tunnels)
        except NPSError as e:
            print_error(str(e))
            return 1

    return 0


def cmd_add_tunnel(args: argparse.Namespace) -> int:
    """Add a tunnel to one or all edges."""
    # Port and target are required for tcp/udp tunnels
    if args.type in ("tcp", "udp") and not args.port:
        print_error(f"--port / -p is required for {args.type} tunnels")
        return 1
    if args.type in ("tcp", "udp") and not args.target:
        print_error(f"--target / -T is required for {args.type} tunnels")
        return 1

    try:
        cluster = NPSCluster(args.config)
    except FileNotFoundError as e:
        print_error(str(e))
        return 1

    # Confirm
    if not args.yes:
        targets = [args.edge] if args.edge else cluster.edge_names
        if not targets:
            print_error("No edges configured")
            return 1
        console.print(
            f"Will add [bold]{args.type}[/bold] tunnel to: {', '.join(targets)}"
        )
        console.print(
            f"Client: [bold]{args.client}[/bold], Port: [bold]{args.port}[/bold], "
            f"Target: [bold]{args.target or 'N/A'}[/bold]"
        )
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
            clients = client_mgmt.list_clients(nps, search=args.client)
            matching = [c for c in clients if c.get("Remark") == args.client]
            if not matching:
                print_error(f"Client '{args.client}' not found on {args.edge}")
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
                console.print(f"[green]✓ Added tunnel to {args.edge}[/green]")
            else:
                console.print(f"[red]✗ Failed to add tunnel to {args.edge}[/red]")
                return 1
        except NPSError as e:
            print_error(str(e))
            return 1
    else:
        # All edges
        if not cluster.edge_names:
            print_error("No edges configured")
            return 1
        results = cluster.broadcast_tunnel(
            client_remark=args.client,
            tunnel_type=args.type,
            port=args.port,
            target=args.target or "",
            remark=args.remark or "",
        )
        for edge, success in results.items():
            status = "[green]✓[/green]" if success else "[red]✗[/red]"
            console.print(f"{status} {edge}")

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
    """Delete a tunnel from edge node(s).

    Supports deletion by --id (single edge), -r/--remark, or
    -p/--port + -t/--type (multi-edge).

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

    tunnel_id = getattr(args, "id", None)
    tunnel_remark = getattr(args, "remark", None)
    tunnel_port = getattr(args, "port", None)
    tunnel_type = getattr(args, "type", None)

    # Validate locator
    if tunnel_id is None and not tunnel_remark and tunnel_port is None:
        print_error(
            "Must specify a locator: --id, -r/--remark, or -p/--port + -t/--type"
        )
        return 1

    # --id requires -e
    if tunnel_id is not None and not args.edge:
        print_error("--id requires -e/--edge (IDs are edge-specific)")
        return 1

    # port+type: both should be present for reliable matching
    if tunnel_port is not None and not tunnel_type:
        print_error("-p/--port requires -t/--type for reliable matching")
        return 1

    # remark and port+type are mutually exclusive locators
    if tunnel_remark and tunnel_port is not None:
        print_error("Cannot use -r/--remark and -p/--port together, pick one locator")
        return 1

    if tunnel_id is not None:
        # Delete by ID on a single edge
        nps = cluster.get_client(args.edge)
        if not nps:
            print_error(f"Edge '{args.edge}' not found")
            return 1

        if not args.yes:
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
    else:
        # Delete by remark or port+type across edge(s)
        edges = [args.edge] if args.edge else cluster.edge_names
        if not edges:
            print_error("No edges configured")
            return 1

        if not args.yes:
            if tunnel_remark:
                label = f"remark={tunnel_remark}"
            else:
                label = f"port={tunnel_port}, type={tunnel_type}"
            console.print(f"Will delete tunnel ({label}) from: {', '.join(edges)}")
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
                matching = _find_tunnels(nps, tunnel_remark, tunnel_port, tunnel_type)
                if not matching:
                    console.print(f"[dim]- {edge_name}: not found, skipping[/dim]")
                    continue
                if len(matching) > 1:
                    ids = [str(m["Id"]) for m in matching]
                    console.print(
                        f"[red]✗ {edge_name}: {len(matching)} matches "
                        f"(IDs: {', '.join(ids)}), use --id to be specific[/red]"
                    )
                    has_error = True
                    continue
                tid = matching[0]["Id"]
                if tunnel.del_tunnel(nps, tid):
                    console.print(f"[green]✓ {edge_name}: deleted (ID {tid})[/green]")
                else:
                    console.print(f"[red]✗ {edge_name}: delete failed[/red]")
                    has_error = True
            except NPSError as e:
                console.print(f"[red]✗ {edge_name}: {e}[/red]")
                has_error = True

        if has_error:
            return 1

    return 0


def _find_tunnels(
    nps,
    remark: str | None = None,
    port: int | None = None,
    tunnel_type: str | None = None,
) -> list[TunnelInfo]:
    """Find tunnels matching remark or port+type.

    Args:
        nps: NPS API client.
        remark: Tunnel remark to match.
        port: Server port to match.
        tunnel_type: Tunnel type to match.

    Returns:
        List of matching tunnel dicts.
    """
    all_tunnels = tunnel.list_tunnels(nps)
    if remark:
        return [t for t in all_tunnels if t.get("Remark") == remark]
    if port is not None and tunnel_type:
        return [
            t
            for t in all_tunnels
            if t.get("Port") == port and t.get("Mode") == tunnel_type
        ]
    return []


def cmd_tunnel_edit(args: argparse.Namespace) -> int:
    """Edit a tunnel on edge node(s).

    Supports locating by --id (single edge), -r/--remark, or
    -p/--port + -t/--type (multi-edge). Value changes use --new-target,
    --new-port, --new-remark.

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

    tunnel_id = getattr(args, "id", None)
    locate_remark = getattr(args, "remark", None)
    locate_port = getattr(args, "port", None)
    locate_type = getattr(args, "type", None)

    new_target = getattr(args, "new_target", None)
    new_port = getattr(args, "new_port", None)
    new_remark = getattr(args, "new_remark", None)

    # Validate: at least one locator
    if tunnel_id is None and not locate_remark and locate_port is None:
        print_error(
            "Must specify a locator: --id, -r/--remark, or -p/--port + -t/--type"
        )
        return 1

    # --id requires -e
    if tunnel_id is not None and not args.edge:
        print_error("--id requires -e/--edge (IDs are edge-specific)")
        return 1

    # port+type: both should be present
    if locate_port is not None and not locate_type:
        print_error("-p/--port requires -t/--type for reliable matching")
        return 1

    # remark and port+type are mutually exclusive locators
    if locate_remark and locate_port is not None:
        print_error("Cannot use -r/--remark and -p/--port together, pick one locator")
        return 1

    if not any([new_target, new_port is not None, new_remark is not None]):
        print_error(
            "No changes specified (use --new-target, --new-port, or --new-remark)"
        )
        return 1

    if tunnel_id is not None:
        # Edit by ID on a single edge
        return _edit_tunnel_on_edge(
            cluster, args.edge, tunnel_id, args, new_target, new_port, new_remark
        )
    else:
        # Edit by remark or port+type across edge(s)
        edges = [args.edge] if args.edge else cluster.edge_names
        if not edges:
            print_error("No edges configured")
            return 1

        if not args.yes:
            if locate_remark:
                label = f"remark={locate_remark}"
            else:
                label = f"port={locate_port}, type={locate_type}"
            changes = []
            if new_target:
                changes.append(f"target -> {new_target}")
            if new_port is not None:
                changes.append(f"port -> {new_port}")
            if new_remark is not None:
                changes.append(f"remark -> {new_remark}")
            console.print(f"Will edit tunnel ({label}) on: {', '.join(edges)}")
            console.print(f"Changes: {', '.join(changes)}")
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
                matching = _find_tunnels(nps, locate_remark, locate_port, locate_type)
                if not matching:
                    console.print(f"[dim]- {edge_name}: not found, skipping[/dim]")
                    continue
                if len(matching) > 1:
                    ids = [str(m["Id"]) for m in matching]
                    console.print(
                        f"[red]✗ {edge_name}: {len(matching)} matches "
                        f"(IDs: {', '.join(ids)}), use --id to be specific[/red]"
                    )
                    has_error = True
                    continue
                current = matching[0]
                tid = current["Id"]
                success = _apply_tunnel_edit(
                    nps, tid, current, new_target, new_port, new_remark
                )
                if success:
                    console.print(f"[green]✓ {edge_name}: updated (ID {tid})[/green]")
                else:
                    console.print(f"[red]✗ {edge_name}: update failed[/red]")
                    has_error = True
            except NPSError as e:
                console.print(f"[red]✗ {edge_name}: {e}[/red]")
                has_error = True

        if has_error:
            return 1

    return 0


def _edit_tunnel_on_edge(
    cluster: NPSCluster,
    edge_name: str,
    tunnel_id: int,
    args,
    new_target: str | None,
    new_port: int | None,
    new_remark: str | None,
) -> int:
    """Edit a tunnel by ID on a single edge.

    Args:
        cluster: NPSCluster instance.
        edge_name: Edge name.
        tunnel_id: Tunnel ID.
        args: Parsed args (for --yes).
        new_target: New target address or None.
        new_port: New server port or None.
        new_remark: New remark or None.

    Returns:
        Exit code.
    """
    nps = cluster.get_client(edge_name)
    if not nps:
        print_error(f"Edge '{edge_name}' not found")
        return 1

    try:
        current = tunnel.get_tunnel(nps, tunnel_id)
        if not current:
            print_error(f"Tunnel ID {tunnel_id} not found on {edge_name}")
            return 1

        if not args.yes:
            target_obj = current.get("Target", {})
            console.print(f"Editing tunnel ID [bold]{tunnel_id}[/bold] on {edge_name}:")
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

        success = _apply_tunnel_edit(
            nps, tunnel_id, current, new_target, new_port, new_remark
        )
        if success:
            console.print(f"[green]✓ Updated tunnel {tunnel_id} on {edge_name}[/green]")
        else:
            console.print(f"[red]✗ Failed to update tunnel on {edge_name}[/red]")
            return 1
    except NPSError as e:
        print_error(str(e))
        return 1

    return 0


def _apply_tunnel_edit(
    nps,
    tunnel_id: int,
    current: TunnelInfo,
    new_target: str | None,
    new_port: int | None,
    new_remark: str | None,
) -> bool:
    """Apply a tunnel edit operation.

    Args:
        nps: NPS API client.
        tunnel_id: Tunnel ID to edit.
        current: Current tunnel data.
        new_target: New target address or None.
        new_port: New server port or None.
        new_remark: New remark or None.

    Returns:
        True if successful.
    """
    target_obj = current.get("Target", {})
    client_obj = current.get("Client", {})

    updated_target = new_target or (
        target_obj.get("TargetStr", "") if target_obj else ""
    )
    updated_port = new_port if new_port is not None else current.get("Port", 0)
    updated_remark = new_remark if new_remark is not None else current.get("Remark", "")
    client_id = client_obj.get("Id", 0) if client_obj else 0
    tunnel_type = current.get("Mode", "tcp")

    return tunnel.edit_tunnel(
        nps,
        tunnel_id=tunnel_id,
        client_id=client_id,
        tunnel_type=tunnel_type,
        port=updated_port,
        target=updated_target,
        remark=updated_remark,
    )


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
