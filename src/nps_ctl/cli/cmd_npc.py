"""CLI commands: npc-install, npc-uninstall, npc-status, npc-restart, npc-list.

Deploy and manage NPC clients on remote servers.
"""

from __future__ import annotations

import argparse
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
)
from rich.table import Table

from ..cluster import NPSCluster
from ..deploy import (
    DEFAULT_NPC_VERSION,
    check_npc_status,
    install_npc,
    restart_npc,
    uninstall_npc,
)
from ..types import NPCClientConfig
from .helpers import console


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


def _parse_npc_status_output(
    stdout: str,
) -> tuple[str, str]:
    """Parse NPC status check output into status and details.

    Extracts version and service status from the SSH command output
    produced by ``check_npc_status``.

    Args:
        stdout: Raw stdout from the SSH status check command.

    Returns:
        A tuple of (status, details) where *status* is a rich-markup
        string like ``[green]Running[/green]`` and *details* contains
        extra information such as the NPC version.
    """
    lines = stdout.strip().splitlines()

    version = ""
    service_status = ""

    section = ""
    for line in lines:
        stripped = line.strip()
        if stripped == "=== NPC Version ===":
            section = "version"
            continue
        elif stripped == "=== Service Status ===":
            section = "service"
            continue

        if section == "version" and stripped:
            if "not installed" in stripped.lower():
                version = "Not installed"
            else:
                version = stripped
        elif section == "service" and stripped:
            if not service_status:
                service_status = stripped

    # Determine rich-formatted status string
    if not version or version == "Not installed":
        status = "[red]Not Installed[/red]"
    elif "running" in service_status.lower():
        status = "[green]Running[/green]"
    elif "stopped" in service_status.lower() or "not running" in service_status.lower():
        status = "[yellow]Stopped[/yellow]"
    else:
        status = f"[yellow]{service_status or 'Unknown'}[/yellow]"

    # Build details string
    details_parts: list[str] = []
    if version and version != "Not installed":
        details_parts.append(version)
    if service_status and "running" not in service_status.lower():
        details_parts.append(service_status)

    return status, ", ".join(details_parts)


def cmd_npc_status(args: argparse.Namespace) -> int:
    """Check NPC status on client machines and display as a rich table.

    When ``--parallel`` is passed, SSH checks run concurrently using a
    thread pool, which significantly speeds up status collection for
    many clients.
    """
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

    parallel = getattr(args, "parallel", False)

    # Collect rows: list of (client_name, ssh_host, edges_str, status, details)
    rows: list[tuple[str, str, str, str, str]] = []

    # Pre-resolve configs and identify missing ones
    configs: dict[str, NPCClientConfig] = {}
    for client_name in target_clients:
        npc_config = cluster.get_npc_client(client_name)
        if not npc_config:
            rows.append((client_name, "—", "—", "[red]Config Not Found[/red]", ""))
        else:
            configs[client_name] = npc_config

    # Fetch status (parallel or sequential)
    valid_clients = [n for n in target_clients if n in configs]

    if parallel and len(valid_clients) > 1:
        # Parallel SSH checks
        results_map: dict[str, tuple[str, str]] = {}

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            MofNCompleteColumn(),
            console=console,
            transient=True,
        ) as progress:
            task = progress.add_task("Checking NPC status...", total=len(valid_clients))

            def _check_one(name: str) -> tuple[str, str, str]:
                """Run SSH status check for a single client.

                Returns:
                    Tuple of (client_name, status, details).
                """
                cfg = configs[name]
                result = check_npc_status(ssh_host=cfg.ssh_host)
                if result.success:
                    s, d = _parse_npc_status_output(result.stdout or "")
                else:
                    s, d = "[red]Error[/red]", result.message
                return name, s, d

            with ThreadPoolExecutor(max_workers=min(8, len(valid_clients))) as executor:
                futures = {
                    executor.submit(_check_one, name): name for name in valid_clients
                }
                for future in as_completed(futures):
                    name, status, details = future.result()
                    results_map[name] = (status, details)
                    progress.advance(task)

        # Build rows in original order
        for client_name in valid_clients:
            cfg = configs[client_name]
            edges_str = ", ".join(cfg.edges) if cfg.edges else "—"
            status, details = results_map[client_name]
            rows.append((client_name, cfg.ssh_host, edges_str, status, details))
    else:
        # Sequential SSH checks
        for client_name in valid_clients:
            cfg = configs[client_name]
            edges_str = ", ".join(cfg.edges) if cfg.edges else "—"
            result = check_npc_status(ssh_host=cfg.ssh_host)

            if result.success:
                status, details = _parse_npc_status_output(result.stdout or "")
            else:
                status = "[red]Error[/red]"
                details = result.message

            rows.append((client_name, cfg.ssh_host, edges_str, status, details))

    # Build and display table
    table = Table(title="NPC Client Status")
    table.add_column("Client", style="cyan")
    table.add_column("SSH Host", style="blue")
    table.add_column("Edges", style="magenta")
    table.add_column("NPC Status", style="bold")
    table.add_column("Details")

    for client_name, ssh_host, edges_str, status, details in rows:
        table.add_row(client_name, ssh_host, edges_str, status, details)

    console.print(table)
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


def cmd_client_add(args: argparse.Namespace) -> int:
    """Interactively add a new client entry to clients.toml.

    Prompts the user step-by-step for client information. A vkey is
    auto-generated unless the user provides one during the prompt or
    via the --vkey flag.

    Args:
        args: Parsed command line arguments.

    Returns:
        Exit code (0 for success, 1 for failure).
    """
    import secrets
    import string
    from pathlib import Path

    import tomllib

    from .helpers import get_clients_config_path

    # Resolve clients.toml path
    config_path = Path(args.config)
    clients_path = get_clients_config_path(config_path)

    # Load existing clients to check for duplicates
    existing_names: set[str] = set()
    existing_clients: list[dict] = []
    if clients_path.exists():
        with open(clients_path, "rb") as f:
            data = tomllib.load(f)
        existing_clients = data.get("clients", [])
        existing_names = {c["name"] for c in existing_clients}

    # Load edges config to show available edge names
    with open(config_path, "rb") as f:
        edges_data = tomllib.load(f)
    available_edges = [e["name"] for e in edges_data.get("edges", [])]

    # --- Step 1: Client name ---
    name = args.name
    if not name:
        console.print("\n[bold cyan]Step 1/5: Client name[/bold cyan]")
        console.print(
            "  A unique identifier for this client (e.g., 'cloud.usa7', 'homelab.router')."
        )
        if existing_names:
            console.print(f"  Existing clients: {', '.join(sorted(existing_names))}")
        name = input("  Name: ").strip()
        if not name:
            console.print("[red]Error: Client name cannot be empty.[/red]")
            return 1

    if name in existing_names:
        console.print(
            f"[red]Error: Client '{name}' already exists in clients.toml.[/red]"
        )
        return 1

    # --- Step 2: SSH host ---
    ssh_host = getattr(args, "ssh_host", None)
    if not ssh_host:
        console.print("\n[bold cyan]Step 2/5: SSH host[/bold cyan]")
        console.print(f"  SSH host alias or address for this client (default: {name}).")
        ssh_host_input = input(f"  SSH host [{name}]: ").strip()
        ssh_host = ssh_host_input if ssh_host_input else name

    # --- Step 3: Edges ---
    edges = args.edges
    if not edges:
        console.print("\n[bold cyan]Step 3/5: Edge nodes[/bold cyan]")
        console.print(f"  Available edges: {', '.join(available_edges)}")
        console.print("  Enter edge names separated by spaces, or 'all' for all edges.")
        edges_input = input("  Edges [all]: ").strip()
        if not edges_input or edges_input.lower() == "all":
            edges = available_edges[:]
        else:
            edges = edges_input.split()
            # Validate edge names
            invalid = [e for e in edges if e not in available_edges]
            if invalid:
                console.print(
                    f"[red]Error: Unknown edge(s): {', '.join(invalid)}. "
                    f"Available: {', '.join(available_edges)}[/red]"
                )
                return 1

    # --- Step 4: VKey ---
    vkey = args.vkey
    if not vkey:
        # Generate a 16-char lowercase alphanumeric vkey
        alphabet = string.ascii_lowercase + string.digits
        generated_vkey = "".join(secrets.choice(alphabet) for _ in range(16))

        console.print("\n[bold cyan]Step 4/5: Verify key (vkey)[/bold cyan]")
        console.print(f"  Auto-generated vkey: [green]{generated_vkey}[/green]")
        console.print("  Press Enter to accept, or type a custom vkey.")
        vkey_input = input(f"  VKey [{generated_vkey}]: ").strip()
        vkey = vkey_input if vkey_input else generated_vkey

    # --- Step 5: Connection type ---
    conn_type = getattr(args, "conn_type", None)
    if not conn_type:
        console.print("\n[bold cyan]Step 5/5: Connection type[/bold cyan]")
        console.print("  Options: tls (default), tcp, kcp")
        conn_type_input = input("  Connection type [tls]: ").strip().lower()
        conn_type = (
            conn_type_input if conn_type_input in ("tls", "tcp", "kcp") else "tls"
        )

    # --- Confirmation ---
    console.print("\n[bold]New client entry:[/bold]")
    console.print(f"  Name:       [green]{name}[/green]")
    console.print(f"  SSH host:   [green]{ssh_host}[/green]")
    console.print(f"  Edges:      [green]{', '.join(edges)}[/green]")
    console.print(f"  VKey:       [green]{vkey}[/green]")
    console.print(f"  Conn type:  [green]{conn_type}[/green]")

    if not getattr(args, "yes", False):
        response = input("\nAdd this client? [y/N] ").strip()
        if response.lower() != "y":
            console.print("Aborted.")
            return 0

    # Build new entry
    new_entry = {
        "name": name,
        "ssh_host": ssh_host,
        "edges": edges,
        "vkey": vkey,
    }
    if conn_type != "tls":
        new_entry["conn_type"] = conn_type

    # Append to clients.toml
    existing_clients.append(new_entry)
    toml_content = _generate_clients_toml(existing_clients)

    with open(clients_path, "w") as f:
        f.write(toml_content)

    console.print(
        f"\n[bold green]✓ Added client '{name}' to {clients_path}[/bold green]"
    )
    return 0


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
    if not nps:
        console.print(f"[red]Error:[/red] Could not connect to edge '{edge_name}'")
        return

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


def handle_client_push(args, cluster: NPSCluster) -> None:
    """Push client configurations from clients.toml to NPS edges via API.

    For each client in clients.toml, ensure it exists on all configured
    edges by calling the NPS API to add missing clients.

    Args:
        args: Parsed command line arguments.
        cluster: NPSCluster instance.
    """
    from .. import client_mgmt

    dry_run = getattr(args, "dry_run", False)
    yes = getattr(args, "yes", False)
    update = getattr(args, "update", False)
    target_client = getattr(args, "client", None)
    target_edge = getattr(args, "edge", None)

    # Get target clients
    if target_client:
        npc_config = cluster.get_npc_client(target_client)
        if not npc_config:
            console.print(
                f"[red]Error:[/red] Client '{target_client}' not found in clients.toml. "
                f"Available: {', '.join(cluster.npc_client_names)}"
            )
            return
        npc_clients = [npc_config]
    else:
        npc_clients = [
            c
            for name in cluster.npc_client_names
            if (c := cluster.get_npc_client(name)) is not None
        ]

    if not npc_clients:
        console.print("[yellow]No clients configured in clients.toml.[/yellow]")
        return

    # Show plan
    console.print("\n[bold]Client Push Plan:[/bold]")
    plan_table = Table(title="Clients to push")
    plan_table.add_column("Client", style="green")
    plan_table.add_column("Remark", style="cyan")
    plan_table.add_column("VKey", style="yellow")
    plan_table.add_column("Target Edges", style="blue")

    for npc in npc_clients:
        edges = npc.edges
        if target_edge:
            edges = [e for e in edges if e == target_edge]
        vkey_display = (
            npc.vkey[:16] + "..." if len(npc.vkey) > 16 else (npc.vkey or "(auto)")
        )
        plan_table.add_row(
            npc.name,
            npc.remark,
            vkey_display,
            ", ".join(edges) if edges else "[red]none[/red]",
        )

    console.print(plan_table)

    if update:
        console.print(
            "[bold cyan]Update mode:[/bold cyan] Existing clients will be updated "
            "with local vkey."
        )

    if dry_run:
        console.print("\n[yellow]Dry run mode - no changes will be made.[/yellow]")
        return

    if not yes:
        confirm = input("\nProceed with push? [y/N] ").strip().lower()
        if confirm not in ("y", "yes"):
            console.print("[yellow]Aborted.[/yellow]")
            return

    # Calculate total operations for progress bar
    total_ops = sum(
        len([e for e in npc.edges if not target_edge or e == target_edge])
        for npc in npc_clients
    )

    # Execute push
    results_table = Table(title="Push Results")
    results_table.add_column("Client", style="green")
    results_table.add_column("Edge", style="blue")
    results_table.add_column("Result", style="bold")

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Pushing clients...", total=total_ops)

        for npc in npc_clients:
            edges = npc.edges
            if target_edge:
                edges = [e for e in edges if e == target_edge]

            for edge_name in edges:
                progress.update(task, description=f"Pushing {npc.name} → {edge_name}")

                if edge_name not in cluster.edge_names:
                    results_table.add_row(
                        npc.name, edge_name, "[red]Edge not found[/red]"
                    )
                    progress.advance(task)
                    continue

                nps = cluster.get_client(edge_name)
                if not nps:
                    results_table.add_row(
                        npc.name, edge_name, "[red]Edge client not found[/red]"
                    )
                    progress.advance(task)
                    continue

                try:
                    existing = client_mgmt.list_clients(nps)
                    # Check if client already exists by remark
                    matched_client = None
                    for ec in existing:
                        if ec.get("Remark", "") == npc.remark:
                            matched_client = ec
                            break

                    if matched_client:
                        if update:
                            # Update existing client with local vkey
                            client_id = matched_client.get("Id", 0)
                            remote_vkey = matched_client.get("VerifyKey", "")
                            if remote_vkey == npc.vkey:
                                results_table.add_row(
                                    npc.name,
                                    edge_name,
                                    "[cyan]Already up-to-date (skipped)[/cyan]",
                                )
                            else:
                                success = client_mgmt.edit_client(
                                    nps,
                                    client_id=client_id,
                                    remark=npc.remark,
                                    vkey=npc.vkey,
                                )
                                if success:
                                    results_table.add_row(
                                        npc.name,
                                        edge_name,
                                        "[yellow]Updated (vkey synced)[/yellow]",
                                    )
                                else:
                                    results_table.add_row(
                                        npc.name,
                                        edge_name,
                                        "[red]Failed to update[/red]",
                                    )
                        else:
                            results_table.add_row(
                                npc.name,
                                edge_name,
                                "[cyan]Already exists (skipped)[/cyan]",
                            )
                    else:
                        success = client_mgmt.add_client(
                            nps, remark=npc.remark, vkey=npc.vkey
                        )
                        if success:
                            results_table.add_row(
                                npc.name, edge_name, "[green]Added[/green]"
                            )
                        else:
                            results_table.add_row(
                                npc.name, edge_name, "[red]Failed to add[/red]"
                            )
                except Exception as e:
                    results_table.add_row(npc.name, edge_name, f"[red]Error: {e}[/red]")

                progress.advance(task)

    console.print()
    console.print(results_table)
