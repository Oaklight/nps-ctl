"""CLI commands: npc-install, npc-uninstall, npc-status, npc-restart, npc-list.

Deploy and manage NPC clients on remote servers.
"""

from __future__ import annotations

import argparse
import sys
from typing import TYPE_CHECKING

from rich.table import Table

from ..cluster import NPSCluster
from ..deploy import (
    DEFAULT_NPC_VERSION,
    check_npc_status,
    install_npc,
    restart_npc,
    uninstall_npc,
)
from .helpers import console

if TYPE_CHECKING:
    pass


def cmd_npc_install(args: argparse.Namespace) -> int:
    """Install NPC on client machines via SSH."""
    try:
        cluster = NPSCluster(args.config)
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    # Determine target clients
    if args.client:
        if args.client not in cluster.npc_client_names:
            print(f"Error: NPC client '{args.client}' not found", file=sys.stderr)
            return 1
        target_clients = [args.client]
    else:
        target_clients = cluster.npc_client_names

    if not target_clients:
        print("Error: No NPC clients configured in edges.toml", file=sys.stderr)
        return 1

    # Get version
    version = args.version or DEFAULT_NPC_VERSION

    # Check for force reinstall
    force_reinstall = getattr(args, "force_reinstall", False)

    # Confirm
    if not args.yes:
        print(f"Will install NPC {version} on: {', '.join(target_clients)}")
        if force_reinstall:
            print("This will (force reinstall):")
            print("  - Uninstall existing NPC first")
        else:
            print("This will:")
        print("  - Download NPC from mirrors (jsdelivr CDN, GitHub)")
        print("  - Install using npc install (no-config mode)")
        print("  - Configure and start NPC service")
        response = input("Continue? [y/N] ")
        if response.lower() != "y":
            print("Aborted.")
            return 0

    success_count = 0
    fail_count = 0

    for client_name in target_clients:
        npc_config = cluster.get_npc_client(client_name)
        if not npc_config:
            print(f"✗ {client_name}: Configuration not found")
            fail_count += 1
            continue

        print(f"\nProcessing {client_name} ({npc_config.ssh_host})...")

        # Get vkey
        vkey = cluster.get_vkey_for_npc(npc_config)
        if not vkey:
            print(f"✗ {client_name}: Could not obtain vkey")
            print(
                f"  Hint: Either configure vkey in edges.toml or ensure client "
                f"'{npc_config.remark}' exists in NPS"
            )
            fail_count += 1
            continue

        # Get server addresses
        server_addrs = cluster.get_server_addrs_for_npc(npc_config)
        if not server_addrs:
            print(f"✗ {client_name}: No valid server addresses")
            fail_count += 1
            continue

        print(f"  Server addresses: {server_addrs}")
        print(f"  Connection type: {npc_config.conn_type}")

        # Force reinstall: uninstall first
        if force_reinstall:
            print("  Uninstalling existing NPC...")
            uninstall_result = uninstall_npc(ssh_host=npc_config.ssh_host)
            if uninstall_result.success:
                print("  ✓ Uninstalled successfully")
            else:
                print(f"  ⚠ Uninstall: {uninstall_result.message}")

        # Install NPC
        print("  Installing NPC...")
        result = install_npc(
            ssh_host=npc_config.ssh_host,
            server_addrs=server_addrs,
            vkey=vkey,
            tls_enable=(npc_config.conn_type == "tls"),
            version=version,
            release_url=args.release_url,
        )

        if result.success:
            print(f"✓ {client_name}: Installed successfully")
            if args.verbose and result.stdout:
                for line in result.stdout.strip().split("\n"):
                    print(f"  {line}")
            success_count += 1
        else:
            print(f"✗ {client_name}: {result.message}")
            if result.stderr:
                for line in result.stderr.strip().split("\n"):
                    print(f"  {line}")
            if result.stdout:
                for line in result.stdout.strip().split("\n"):
                    print(f"  {line}")
            fail_count += 1

    print(f"\nSummary: {success_count} succeeded, {fail_count} failed")
    return 0 if fail_count == 0 else 1


def cmd_npc_uninstall(args: argparse.Namespace) -> int:
    """Uninstall NPC from client machines via SSH."""
    try:
        cluster = NPSCluster(args.config)
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    # Determine target clients
    if args.client:
        if args.client not in cluster.npc_client_names:
            print(f"Error: NPC client '{args.client}' not found", file=sys.stderr)
            return 1
        target_clients = [args.client]
    else:
        target_clients = cluster.npc_client_names

    if not target_clients:
        print("Error: No NPC clients configured", file=sys.stderr)
        return 1

    # Confirm
    if not args.yes:
        print(f"Will uninstall NPC from: {', '.join(target_clients)}")
        print("This will:")
        print("  - Stop NPC service")
        print("  - Uninstall NPC")
        print("  - Remove NPC binary")
        response = input("Continue? [y/N] ")
        if response.lower() != "y":
            print("Aborted.")
            return 0

    success_count = 0
    fail_count = 0

    for client_name in target_clients:
        npc_config = cluster.get_npc_client(client_name)
        if not npc_config:
            print(f"✗ {client_name}: Configuration not found")
            fail_count += 1
            continue

        print(f"\nUninstalling NPC from {client_name} ({npc_config.ssh_host})...")

        result = uninstall_npc(ssh_host=npc_config.ssh_host)

        if result.success:
            print(f"✓ {client_name}: Uninstalled successfully")
            if args.verbose and result.stdout:
                for line in result.stdout.strip().split("\n"):
                    print(f"  {line}")
            success_count += 1
        else:
            print(f"✗ {client_name}: {result.message}")
            if result.stderr:
                for line in result.stderr.strip().split("\n"):
                    print(f"  {line}")
            fail_count += 1

    print(f"\nSummary: {success_count} succeeded, {fail_count} failed")
    return 0 if fail_count == 0 else 1


def cmd_npc_status(args: argparse.Namespace) -> int:
    """Check NPC status on client machines."""
    try:
        cluster = NPSCluster(args.config)
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    # Determine target clients
    if args.client:
        if args.client not in cluster.npc_client_names:
            print(f"Error: NPC client '{args.client}' not found", file=sys.stderr)
            return 1
        target_clients = [args.client]
    else:
        target_clients = cluster.npc_client_names

    if not target_clients:
        print("Error: No NPC clients configured", file=sys.stderr)
        return 1

    for client_name in target_clients:
        npc_config = cluster.get_npc_client(client_name)
        if not npc_config:
            print(f"✗ {client_name}: Configuration not found")
            continue

        print(f"\n=== {client_name} ({npc_config.ssh_host}) ===")

        result = check_npc_status(ssh_host=npc_config.ssh_host)

        if result.success:
            if result.stdout:
                print(result.stdout.strip())
        else:
            print(f"Error: {result.message}")
            if result.stderr:
                print(result.stderr.strip())

    return 0


def cmd_npc_restart(args: argparse.Namespace) -> int:
    """Restart NPC service on client machines."""
    try:
        cluster = NPSCluster(args.config)
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    # Determine target clients
    if args.client:
        if args.client not in cluster.npc_client_names:
            print(f"Error: NPC client '{args.client}' not found", file=sys.stderr)
            return 1
        target_clients = [args.client]
    else:
        target_clients = cluster.npc_client_names

    if not target_clients:
        print("Error: No NPC clients configured", file=sys.stderr)
        return 1

    success_count = 0
    fail_count = 0

    for client_name in target_clients:
        npc_config = cluster.get_npc_client(client_name)
        if not npc_config:
            print(f"✗ {client_name}: Configuration not found")
            fail_count += 1
            continue

        print(f"Restarting NPC on {client_name} ({npc_config.ssh_host})...")

        result = restart_npc(ssh_host=npc_config.ssh_host)

        if result.success:
            print(f"✓ {client_name}: Restarted successfully")
            if args.verbose and result.stdout:
                for line in result.stdout.strip().split("\n"):
                    print(f"  {line}")
            success_count += 1
        else:
            print(f"✗ {client_name}: {result.message}")
            if result.stderr:
                for line in result.stderr.strip().split("\n"):
                    print(f"  {line}")
            fail_count += 1

    print(f"\nSummary: {success_count} succeeded, {fail_count} failed")
    return 0 if fail_count == 0 else 1


def handle_npc_list(args, cluster: NPSCluster) -> None:
    """Handle the npc-list command.

    Fetch client list from a specific edge's NPS API and update
    the clients.toml configuration file.

    Args:
        args: Parsed command line arguments.
        cluster: NPSCluster instance.
    """
    from .. import client_mgmt

    edge_name = args.edge
    dry_run = args.dry_run

    # Validate edge name
    if edge_name not in cluster.edge_names:
        console.print(
            f"[red]Error:[/red] Edge '{edge_name}' not found. "
            f"Available edges: {', '.join(cluster.edge_names)}"
        )
        return

    # Get NPS API client for the edge
    nps = cluster.get_client(edge_name)

    console.print(f"\n[bold]Fetching clients from edge:[/bold] {edge_name}")

    try:
        clients = client_mgmt.list_clients(nps)
    except Exception as e:
        console.print(f"[red]Error fetching clients:[/red] {e}")
        return

    if not clients:
        console.print("[yellow]No clients found on this edge.[/yellow]")
        return

    # Display clients in a table
    table = Table(title=f"Clients on {edge_name}")
    table.add_column("ID", style="cyan", justify="right")
    table.add_column("Remark", style="green")
    table.add_column("VKey", style="yellow")
    table.add_column("Status", style="bold")

    for client in clients:
        vkey = client.get("VerifyKey", "")
        is_connect = client.get("IsConnect", False)
        status = "[green]Connected[/green]" if is_connect else "[red]Disconnected[/red]"
        table.add_row(
            str(client.get("Id", "")),
            client.get("Remark", ""),
            vkey[:20] + "..." if len(vkey) > 20 else vkey,
            status,
        )

    console.print(table)
    console.print(f"\nTotal: {len(clients)} client(s)")

    # Update clients.toml
    _update_clients_toml(cluster, edge_name, clients, dry_run)


def _update_clients_toml(
    cluster: NPSCluster,
    edge_name: str,
    api_clients: list,
    dry_run: bool = False,
) -> None:
    """Update clients.toml with client info fetched from NPS API.

    For each client returned by the API, update the vkey in the existing
    clients.toml entry (matched by remark/name), or add a new entry if
    it doesn't exist.

    Args:
        cluster: NPSCluster instance.
        edge_name: Name of the edge the clients were fetched from.
        api_clients: List of ClientInfo dicts from the NPS API.
        dry_run: If True, only show what would be written.
    """
    import tomllib

    clients_path = cluster.clients_config_path

    # Load existing clients.toml if it exists
    existing_clients: list[dict] = []
    if clients_path.exists():
        with open(clients_path, "rb") as f:
            data = tomllib.load(f)
        existing_clients = data.get("clients", [])

    # Build a lookup by name/remark for existing clients
    existing_by_name: dict[str, dict] = {}
    for c in existing_clients:
        existing_by_name[c["name"]] = c

    # Update existing entries and track new ones
    updated_count = 0
    added_count = 0

    for api_client in api_clients:
        remark = api_client.get("Remark", "").strip()
        vkey = api_client.get("VerifyKey", "")

        if not remark:
            continue

        if remark in existing_by_name:
            # Update vkey if changed
            old_vkey = existing_by_name[remark].get("vkey", "")
            if old_vkey != vkey:
                existing_by_name[remark]["vkey"] = vkey
                updated_count += 1
                console.print(f"  [cyan]Updated[/cyan] vkey for '{remark}'")
            # Ensure this edge is in the edges list
            edges = existing_by_name[remark].get("edges", [])
            if edge_name not in edges:
                edges.append(edge_name)
                existing_by_name[remark]["edges"] = edges
                console.print(f"  [cyan]Added[/cyan] edge '{edge_name}' to '{remark}'")
        else:
            # Add new client entry
            new_entry = {
                "name": remark,
                "ssh_host": remark,
                "edges": [edge_name],
                "remark": remark,
                "vkey": vkey,
            }
            existing_by_name[remark] = new_entry
            existing_clients.append(new_entry)
            added_count += 1
            console.print(f"  [green]Added[/green] new client '{remark}'")

    # Generate TOML content
    toml_content = _generate_clients_toml(list(existing_by_name.values()))

    if dry_run:
        console.print("\n[bold yellow]Dry run - would write:[/bold yellow]")
        console.print(toml_content)
        return

    # Write to file
    with open(clients_path, "w") as f:
        f.write(toml_content)

    console.print(
        f"\n[bold green]Updated {clients_path}:[/bold green] "
        f"{updated_count} updated, {added_count} added"
    )


def _generate_clients_toml(clients: list[dict]) -> str:
    """Generate TOML content for clients configuration.

    Args:
        clients: List of client configuration dicts.

    Returns:
        TOML formatted string.
    """
    lines = [
        "# NPC client configurations",
        "# This file defines NPC (NPS client) deployment targets.",
        "# Use `nps-ctl npc-list -e <edge>` to refresh client info from NPS API.",
        "",
    ]

    for client in clients:
        lines.append("[[clients]]")
        lines.append(f'name = "{client["name"]}"')
        lines.append(f'ssh_host = "{client.get("ssh_host", client["name"])}"')

        # Format edges list
        edges = client.get("edges", [])
        edges_str = ", ".join(f'"{e}"' for e in edges)
        lines.append(f"edges = [{edges_str}]")

        # Optional fields - only write if they have non-default values
        remark = client.get("remark", "")
        if remark and remark != client["name"]:
            lines.append(f'remark = "{remark}"')

        conn_type = client.get("conn_type", "")
        if conn_type and conn_type != "tls":
            lines.append(f'conn_type = "{conn_type}"')

        vkey = client.get("vkey", "")
        lines.append(f'vkey = "{vkey}"')

        lines.append("")  # blank line between entries

    return "\n".join(lines) + "\n"
