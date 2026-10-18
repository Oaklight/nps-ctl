"""CLI command: tunnels - List and manage tunnels."""

import argparse

from rich.markup import escape

from .. import client_mgmt, tunnel
from ..cluster import NPSCluster
from ..exceptions import NPSError
from ..status import build_status_payload, collect_edge_status
from ..types import TunnelInfo
from .helpers import (
    build_edge_results_payload,
    clients_cell,
    console,
    count_cell,
    create_table,
    edge_region,
    normalize_auth,
    print_edge_summary,
    print_error,
    print_json,
    print_status_errors,
    redact_user_auth,
    resolve_write_edges,
    status_cell,
    status_spinner,
    sum_counts,
    validate_read_target,
)


def cmd_tunnels(args: argparse.Namespace) -> int:
    """List tunnels on edge nodes."""
    json_mode = getattr(args, "json", False)
    try:
        cluster = NPSCluster(args.config)
    except FileNotFoundError as e:
        if json_mode:
            print_json({"error": str(e)})
        else:
            print_error(str(e))
        return 1

    tunnel_type = getattr(args, "type", "") or ""

    target_error = validate_read_target(args)
    if target_error is not None:
        if json_mode:
            print_json({"error": target_error})
        else:
            print_error(target_error)
        return 2

    if not cluster.edge_names:
        message = "No edges configured"
        if json_mode:
            print_json({"error": message})
        else:
            print_error(message)
        return 1

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
            tunnels = tunnel.list_tunnels(nps, tunnel_type=tunnel_type)
        except NPSError as e:
            if json_mode:
                print_json(
                    build_edge_results_payload(
                        {edge_name: []},
                        {edge_name: str(e)},
                        lambda name: edge_region(cluster, name),
                        configured=len(cluster.edge_names),
                    )
                )
            else:
                print_error(str(e))
            return 1

        if json_mode:
            print_json(
                build_edge_results_payload(
                    {edge_name: redact_user_auth(tunnels)},
                    {},
                    lambda name: edge_region(cluster, name),
                    configured=len(cluster.edge_names),
                )
            )
            return 0

        edge = cluster.get_edge(edge_name)
        region = edge.region if edge else ""
        console.print(f"\n[bold cyan]=== {edge_name} ({region}) ===[/bold cyan]")
        _print_tunnels(tunnels)
        return 0

    all_tunnels = cluster.get_all_tunnels()
    if json_mode:
        print_json(
            build_edge_results_payload(
                {name: redact_user_auth(items) for name, items in all_tunnels.items()},
                all_tunnels.errors,
                lambda name: edge_region(cluster, name),
            )
        )
        return 1 if all_tunnels.errors else 0

    for edge_name, tunnels in all_tunnels.items():
        edge = cluster.get_edge(edge_name)
        region = edge.region if edge else ""
        if edge_name in all_tunnels.errors:
            console.print(
                f"\n[red]✗ {edge_name} ({region}): "
                f"{all_tunnels.errors[edge_name]}[/red]"
            )
            continue
        console.print(f"\n[bold cyan]=== {edge_name} ({region}) ===[/bold cyan]")
        _print_tunnels(tunnels)

    return print_edge_summary(all_tunnels, all_tunnels.errors)


def cmd_tunnel_status(args: argparse.Namespace) -> int:
    """Show tunnel inventory and client liveness per edge."""
    json_mode = getattr(args, "json", False)
    usage_error = validate_read_target(args)
    if usage_error:
        if json_mode:
            print_json({"error": usage_error})
        else:
            print_error(usage_error)
        return 2

    try:
        cluster = NPSCluster(args.config)
    except FileNotFoundError as e:
        if json_mode:
            print_json({"error": str(e)})
        else:
            print_error(str(e))
        return 1

    if not cluster.edge_names:
        if json_mode:
            print_json({"error": "No edges configured"})
        else:
            print_error("No edges configured")
        return 1

    edge_name = getattr(args, "edge", None)
    if edge_name and cluster.get_edge(edge_name) is None:
        message = f"Edge '{edge_name}' not found"
        if json_mode:
            print_json({"error": message})
        else:
            print_error(message)
        return 1

    selected = [edge_name] if edge_name else None
    with status_spinner("Checking tunnel status...", json_mode=json_mode):
        rows = collect_edge_status(
            cluster,
            edge_names=selected,
            include_hosts=False,
            include_tunnels=True,
        )

    if json_mode:
        print_json(build_status_payload(rows))
        return 0 if all(row.ok for row in rows) else 1

    table = create_table(title="NPS Tunnel Status")
    table.add_column("Edge", style="bold")
    table.add_column("Region")
    table.add_column("Status")
    table.add_column("Clients", justify="right")
    table.add_column("Tunnels", justify="right")
    table.add_column("Running", justify="right")
    table.add_column("Ports", justify="right")

    for row in rows:
        table.add_row(
            escape(row.edge),
            escape(row.region or "-"),
            status_cell(row),
            clients_cell(row),
            count_cell(row.tunnels_total),
            count_cell(row.tunnels_running),
            count_cell(row.tunnel_ports),
        )

    console.print(table, crop=False)

    online = sum(1 for row in rows if row.online)
    clients_online = sum_counts([row.clients_online for row in rows])
    clients_total = sum_counts([row.clients_total for row in rows])
    tunnels_total = sum_counts([row.tunnels_total for row in rows])
    tunnels_running = sum_counts([row.tunnels_running for row in rows])
    tunnel_ports = sum_counts([row.tunnel_ports for row in rows])
    clients_text = "-" if clients_total is None else f"{clients_online}/{clients_total}"
    console.print(
        f"[dim]{online}/{len(rows)} edges online; clients {clients_text} online, "
        f"{count_cell(tunnels_total)} tunnels "
        f"({count_cell(tunnels_running)} running, "
        f"{count_cell(tunnel_ports)} server ports)[/dim]"
    )
    print_status_errors(rows)
    return 0 if all(row.ok for row in rows) else 1


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

    targets, code = resolve_write_edges(args, cluster.edge_names)
    if targets is None:
        return code

    # Normalize auth: comma-separated -> newline-separated for NPS API
    auth_str = normalize_auth(getattr(args, "auth", None) or "")

    # Confirm
    if not args.yes:
        console.print(
            f"Will add [bold]{args.type}[/bold] tunnel to: {', '.join(targets)}"
        )
        console.print(
            f"Client: [bold]{args.client}[/bold], Port: [bold]{args.port}[/bold], "
            f"Target: [bold]{args.target or 'N/A'}[/bold]"
        )
        if auth_str:
            console.print("[bold yellow]Basic Auth: enabled[/bold yellow]")
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
                auth=auth_str,
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
            auth=auth_str,
        )
        for edge, success in results.items():
            status = "[green]✓[/green]" if success else "[red]✗[/red]"
            console.print(f"{status} {edge}")
        if not all(results.values()):
            return 1

    return 0


def _print_tunnels(tunnels: list[TunnelInfo]) -> None:
    """Print tunnel list as table."""
    table = create_table()
    table.add_column("ID", style="dim")
    table.add_column("Type", style="bold magenta")
    table.add_column("Port", style="cyan", justify="right")
    table.add_column("Target", style="green", overflow="fold")
    table.add_column("Client")
    table.add_column("Status")
    table.add_column("Auth", style="dim")

    for t in tunnels:
        client_info = t.get("Client", {})
        client_name = client_info.get("Remark", "") if client_info else ""
        is_running = t.get("RunStatus", False)
        status = "[green]Running[/green]" if is_running else "[red]Stopped[/red]"
        target = t.get("Target", {})
        target_addr = target.get("TargetStr", "") if target else t.get("TargetAddr", "")
        user_auth = t.get("UserAuth", {})
        auth_display = "✓" if user_auth and user_auth.get("Content") else ""

        table.add_row(
            str(t.get("Id", "")),
            t.get("Mode", ""),
            str(t.get("Port", "")),
            target_addr,
            client_name,
            status,
            auth_display,
        )

    console.print(table, crop=False)


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
    if tunnel_id is not None and getattr(args, "all", False):
        print_error("--id targets a single edge; use -e/--edge, not -a/--all")
        return 2
    if tunnel_id is not None and not args.edge:
        print_error("--id requires -e/--edge (IDs are edge-specific)")
        return 2

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
        edges, code = resolve_write_edges(args, cluster.edge_names)
        if edges is None:
            return code

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
    new_auth = getattr(args, "auth", None)
    if new_auth is not None:
        new_auth = normalize_auth(new_auth)

    # Validate: at least one locator
    if tunnel_id is None and not locate_remark and locate_port is None:
        print_error(
            "Must specify a locator: --id, -r/--remark, or -p/--port + -t/--type"
        )
        return 1

    # --id requires -e
    if tunnel_id is not None and getattr(args, "all", False):
        print_error("--id targets a single edge; use -e/--edge, not -a/--all")
        return 2
    if tunnel_id is not None and not args.edge:
        print_error("--id requires -e/--edge (IDs are edge-specific)")
        return 2

    # port+type: both should be present
    if locate_port is not None and not locate_type:
        print_error("-p/--port requires -t/--type for reliable matching")
        return 1

    # remark and port+type are mutually exclusive locators
    if locate_remark and locate_port is not None:
        print_error("Cannot use -r/--remark and -p/--port together, pick one locator")
        return 1

    if not any(
        [
            new_target,
            new_port is not None,
            new_remark is not None,
            new_auth is not None,
        ]
    ):
        print_error(
            "No changes specified "
            "(use --new-target, --new-port, --new-remark, or --auth)"
        )
        return 1

    if tunnel_id is not None:
        # Edit by ID on a single edge
        return _edit_tunnel_on_edge(
            cluster,
            args.edge,
            tunnel_id,
            args,
            new_target,
            new_port,
            new_remark,
            new_auth,
        )
    else:
        # Edit by remark or port+type across edge(s)
        edges, code = resolve_write_edges(args, cluster.edge_names)
        if edges is None:
            return code

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
            if new_auth is not None:
                changes.append("auth -> " + ("enabled" if new_auth else "cleared"))
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
                    nps, tid, current, new_target, new_port, new_remark, new_auth
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
    new_auth: str | None = None,
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
        new_auth: New Basic Auth credentials or None.

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
            if new_auth is not None:
                if new_auth:
                    console.print("[bold yellow]  Auth: enabled[/bold yellow]")
                else:
                    console.print("  Auth: [dim]cleared[/dim]")
            response = input("Continue? [y/N] ")
            if response.lower() != "y":
                console.print("Aborted.")
                return 0

        success = _apply_tunnel_edit(
            nps, tunnel_id, current, new_target, new_port, new_remark, new_auth
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
    new_auth: str | None = None,
) -> bool:
    """Apply a tunnel edit operation.

    Args:
        nps: NPS API client.
        tunnel_id: Tunnel ID to edit.
        current: Current tunnel data.
        new_target: New target address or None.
        new_port: New server port or None.
        new_remark: New remark or None.
        new_auth: New Basic Auth credentials or None to keep existing.

    Returns:
        True if successful.
    """
    target_obj = current.get("Target", {})
    client_obj = current.get("Client", {})
    user_auth = current.get("UserAuth", {})

    updated_target = new_target or (
        target_obj.get("TargetStr", "") if target_obj else ""
    )
    updated_port = new_port if new_port is not None else current.get("Port", 0)
    updated_remark = new_remark if new_remark is not None else current.get("Remark", "")
    updated_auth = (
        new_auth
        if new_auth is not None
        else (user_auth.get("Content", "") if user_auth else "")
    )
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
        auth=updated_auth,
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
