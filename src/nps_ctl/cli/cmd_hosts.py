"""CLI commands: hosts, add-host - List and manage host mappings."""

import argparse

from .. import client_mgmt, host
from ..cluster import NPSCluster
from ..exceptions import NPSError
from ..types import HostInfo
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
            edge = cluster.get_edge(edge_name)
            region = edge.region if edge else ""
            console.print(f"\n[bold cyan]=== {edge_name} ({region}) ===[/bold cyan]")
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


def _print_hosts(hosts: list[HostInfo]) -> None:
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


def cmd_host_del(args: argparse.Namespace) -> int:
    """Delete a host mapping from edge node(s).

    Supports deletion by --id (single edge), -d/--domain, or -r/--remark
    (multi-edge).

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

    host_id = getattr(args, "id", None)
    host_domain = getattr(args, "domain", None)
    host_remark = getattr(args, "remark", None)

    # --id requires -e
    if host_id is not None and not args.edge:
        print_error("--id requires -e/--edge (IDs are edge-specific)")
        return 1

    if host_id is not None:
        # Delete by ID on a single edge
        nps = cluster.get_client(args.edge)
        if not nps:
            print_error(f"Edge '{args.edge}' not found")
            return 1

        if not args.yes:
            console.print(
                f"Will delete host ID [bold]{host_id}[/bold] "
                f"from [bold]{args.edge}[/bold]"
            )
            response = input("Continue? [y/N] ")
            if response.lower() != "y":
                console.print("Aborted.")
                return 0

        try:
            if host.del_host(nps, host_id):
                console.print(
                    f"[green]✓ Deleted host {host_id} from {args.edge}[/green]"
                )
            else:
                console.print(
                    f"[red]✗ Failed to delete host {host_id} from {args.edge}[/red]"
                )
                return 1
        except NPSError as e:
            print_error(str(e))
            return 1
    else:
        # Delete by domain or remark across edge(s)
        search_key = host_domain or host_remark
        search_field = "Host" if host_domain else "Remark"
        assert search_key is not None  # guaranteed by mutually exclusive group

        edges = [args.edge] if args.edge else cluster.edge_names
        if not edges:
            print_error("No edges configured")
            return 1

        if not args.yes:
            label = f"domain={host_domain}" if host_domain else f"remark={host_remark}"
            console.print(f"Will delete host ({label}) from: {', '.join(edges)}")
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
                hosts = host.list_hosts(nps, search=search_key)
                matching = [h for h in hosts if h.get(search_field) == search_key]
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
                hid = matching[0]["Id"]
                if host.del_host(nps, hid):
                    console.print(f"[green]✓ {edge_name}: deleted (ID {hid})[/green]")
                else:
                    console.print(f"[red]✗ {edge_name}: delete failed[/red]")
                    has_error = True
            except NPSError as e:
                console.print(f"[red]✗ {edge_name}: {e}[/red]")
                has_error = True

        if has_error:
            return 1

    return 0


def cmd_host_edit(args: argparse.Namespace) -> int:
    """Edit a host mapping on edge node(s).

    Supports locating by --id (single edge), -d/--domain, or -r/--remark
    (multi-edge). Value changes use --new-domain, --new-target, --new-remark.

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

    host_id = getattr(args, "id", None)
    locate_domain = getattr(args, "domain", None)
    locate_remark = getattr(args, "remark", None)

    new_domain = getattr(args, "new_domain", None)
    new_target = getattr(args, "new_target", None)
    new_remark = getattr(args, "new_remark", None)

    # Validate: at least one locator
    if host_id is None and not locate_domain and not locate_remark:
        print_error("Must specify a locator: --id, -d/--domain, or -r/--remark")
        return 1

    # --id requires -e
    if host_id is not None and not args.edge:
        print_error("--id requires -e/--edge (IDs are edge-specific)")
        return 1

    if not any([new_domain, new_target, new_remark is not None]):
        print_error(
            "No changes specified (use --new-domain, --new-target, or --new-remark)"
        )
        return 1

    if host_id is not None:
        # Edit by ID on a single edge
        return _edit_host_on_edge(
            cluster, args.edge, host_id, args, new_domain, new_target, new_remark
        )
    else:
        # Edit by domain or remark across edge(s)
        search_key = locate_domain or locate_remark
        search_field = "Host" if locate_domain else "Remark"

        edges = [args.edge] if args.edge else cluster.edge_names
        if not edges:
            print_error("No edges configured")
            return 1

        if not args.yes:
            label = (
                f"domain={locate_domain}"
                if locate_domain
                else f"remark={locate_remark}"
            )
            changes = []
            if new_domain:
                changes.append(f"domain -> {new_domain}")
            if new_target:
                changes.append(f"target -> {new_target}")
            if new_remark is not None:
                changes.append(f"remark -> {new_remark}")
            console.print(f"Will edit host ({label}) on: {', '.join(edges)}")
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
                hosts = host.list_hosts(nps, search=search_key)
                matching = [h for h in hosts if h.get(search_field) == search_key]
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
                hid = matching[0]["Id"]
                result = _apply_host_edit(
                    nps, hid, matching[0], new_domain, new_target, new_remark
                )
                if result:
                    console.print(f"[green]✓ {edge_name}: updated (ID {hid})[/green]")
                else:
                    console.print(f"[red]✗ {edge_name}: update failed[/red]")
                    has_error = True
            except NPSError as e:
                console.print(f"[red]✗ {edge_name}: {e}[/red]")
                has_error = True

        if has_error:
            return 1

    return 0


def _edit_host_on_edge(
    cluster: NPSCluster,
    edge_name: str,
    host_id: int,
    args,
    new_domain: str | None,
    new_target: str | None,
    new_remark: str | None,
) -> int:
    """Edit a host by ID on a single edge.

    Args:
        cluster: NPSCluster instance.
        edge_name: Edge name.
        host_id: Host ID.
        args: Parsed args (for --yes).
        new_domain: New domain name or None.
        new_target: New target address or None.
        new_remark: New remark or None.

    Returns:
        Exit code.
    """
    nps = cluster.get_client(edge_name)
    if not nps:
        print_error(f"Edge '{edge_name}' not found")
        return 1

    try:
        current = host.get_host(nps, host_id)
        if not current:
            print_error(f"Host ID {host_id} not found on {edge_name}")
            return 1

        if not args.yes:
            console.print(f"Editing host ID [bold]{host_id}[/bold] on {edge_name}:")
            if new_domain:
                console.print(f"  Domain: {current.get('Host', '')} -> {new_domain}")
            if new_target:
                target_obj = current.get("Target", {})
                old_target = target_obj.get("TargetStr", "") if target_obj else ""
                console.print(f"  Target: {old_target} -> {new_target}")
            if new_remark is not None:
                console.print(f"  Remark: {current.get('Remark', '')} -> {new_remark}")
            response = input("Continue? [y/N] ")
            if response.lower() != "y":
                console.print("Aborted.")
                return 0

        success = _apply_host_edit(
            nps, host_id, current, new_domain, new_target, new_remark
        )
        if success:
            console.print(f"[green]✓ Updated host {host_id} on {edge_name}[/green]")
        else:
            console.print(f"[red]✗ Failed to update host on {edge_name}[/red]")
            return 1
    except NPSError as e:
        print_error(str(e))
        return 1

    return 0


def _apply_host_edit(
    nps,
    host_id: int,
    current: HostInfo,
    new_domain: str | None,
    new_target: str | None,
    new_remark: str | None,
) -> bool:
    """Apply a host edit operation.

    Args:
        nps: NPS API client.
        host_id: Host ID to edit.
        current: Current host data.
        new_domain: New domain name or None.
        new_target: New target address or None.
        new_remark: New remark or None.

    Returns:
        True if successful.
    """
    target_obj = current.get("Target", {})
    client_obj = current.get("Client", {})

    updated_host = new_domain or current.get("Host", "")
    updated_target = new_target or (
        target_obj.get("TargetStr", "") if target_obj else ""
    )
    updated_remark = new_remark if new_remark is not None else current.get("Remark", "")
    client_id = client_obj.get("Id", 0) if client_obj else 0

    return host.edit_host(
        nps,
        host_id=host_id,
        client_id=client_id,
        host=updated_host,
        target=updated_target,
        remark=updated_remark,
        location=current.get("Location", ""),
        scheme=current.get("Scheme", "all"),
        header_change=current.get("Header", ""),
        host_change=current.get("HostChange", ""),
    )
