"""Command-line interface for NPS management.

This module provides the `nps-ctl` command for managing NPS servers.
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from nps_ctl.api import NPSCluster, NPSError
from nps_ctl.deploy import (
    DEFAULT_NPS_RELEASE_URL,
    install_nps,
    load_template,
    render_template,
    uninstall_nps,
)


def get_default_config_path() -> Path:
    """Get the default configuration file path.

    Searches in order:
    1. ./config/edges.toml
    2. ~/.config/nps-ctl/edges.toml
    3. /etc/nps-ctl/edges.toml

    Returns:
        Path to the configuration file.

    Raises:
        FileNotFoundError: If no configuration file is found.
    """
    paths = [
        Path("config/edges.toml"),
        Path.home() / ".config" / "nps-ctl" / "edges.toml",
        Path("/etc/nps-ctl/edges.toml"),
    ]
    for path in paths:
        if path.exists():
            return path
    raise FileNotFoundError(
        "No configuration file found. Create config/edges.toml or use --config."
    )


def format_table(
    headers: list[str], rows: list[list[str]], widths: list[int] | None = None
) -> str:
    """Format data as a simple ASCII table.

    Args:
        headers: Column headers.
        rows: Table rows.
        widths: Optional column widths (auto-calculated if not provided).

    Returns:
        Formatted table string.
    """
    if widths is None:
        widths = [len(h) for h in headers]
        for row in rows:
            for i, cell in enumerate(row):
                if i < len(widths):
                    widths[i] = max(widths[i], len(str(cell)))

    # Build format string
    fmt = "  ".join(f"{{:<{w}}}" for w in widths)
    lines = [fmt.format(*headers)]
    lines.append("  ".join("-" * w for w in widths))
    for row in rows:
        # Pad row if needed
        padded = list(row) + [""] * (len(headers) - len(row))
        lines.append(fmt.format(*[str(c)[:w] for c, w in zip(padded, widths)]))
    return "\n".join(lines)


def cmd_status(args: argparse.Namespace) -> int:
    """Show status of all edge nodes."""
    try:
        cluster = NPSCluster(args.config)
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    headers = ["Edge", "Region", "API URL", "Status"]
    rows = []

    for name in cluster.edge_names:
        edge = cluster.get_edge(name)
        client = cluster.get_client(name)
        if not edge or not client:
            continue

        try:
            # Try to get clients to verify connection
            client.list_clients(limit=1)
            status = "✓ Online"
        except NPSError:
            status = "✗ Offline"

        rows.append([name, edge.region, edge.api_url, status])

    print(format_table(headers, rows))
    return 0


def cmd_clients(args: argparse.Namespace) -> int:
    """List clients on edge nodes."""
    try:
        cluster = NPSCluster(args.config)
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    if args.all:
        # Show clients from all edges
        all_clients = cluster.get_all_clients()
        for edge_name, clients in all_clients.items():
            edge = cluster.get_edge(edge_name)
            region = edge.region if edge else ""
            print(f"\n=== {edge_name} ({region}) ===")
            _print_clients(clients)
    else:
        # Show clients from specific edge
        edge_name = args.edge
        if not edge_name:
            # Use first edge as default
            edge_name = cluster.edge_names[0] if cluster.edge_names else None
            if not edge_name:
                print("Error: No edges configured", file=sys.stderr)
                return 1

        client = cluster.get_client(edge_name)
        if not client:
            print(f"Error: Edge '{edge_name}' not found", file=sys.stderr)
            return 1

        try:
            clients = client.list_clients()
            _print_clients(clients)
        except NPSError as e:
            print(f"Error: {e}", file=sys.stderr)
            return 1

    return 0


def _print_clients(clients: list[dict[str, Any]]) -> None:
    """Print client list as table."""
    headers = ["ID", "Remark", "VKey", "Status", "Conn"]
    rows = []
    for c in clients:
        status = "Connected" if c.get("IsConnect") else "Disconnected"
        rows.append(
            [
                str(c.get("Id", "")),
                c.get("Remark", ""),
                c.get("VerifyKey", "")[:20] + "..."
                if len(c.get("VerifyKey", "")) > 20
                else c.get("VerifyKey", ""),
                status,
                str(c.get("NowConn", 0)),
            ]
        )
    print(format_table(headers, rows))


def cmd_tunnels(args: argparse.Namespace) -> int:
    """List tunnels on edge nodes."""
    try:
        cluster = NPSCluster(args.config)
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    if args.all:
        all_tunnels = cluster.get_all_tunnels()
        for edge_name, tunnels in all_tunnels.items():
            edge = cluster.get_edge(edge_name)
            region = edge.region if edge else ""
            print(f"\n=== {edge_name} ({region}) ===")
            _print_tunnels(tunnels)
    else:
        edge_name = args.edge
        if not edge_name:
            edge_name = cluster.edge_names[0] if cluster.edge_names else None
            if not edge_name:
                print("Error: No edges configured", file=sys.stderr)
                return 1

        client = cluster.get_client(edge_name)
        if not client:
            print(f"Error: Edge '{edge_name}' not found", file=sys.stderr)
            return 1

        try:
            tunnels = client.list_tunnels()
            _print_tunnels(tunnels)
        except NPSError as e:
            print(f"Error: {e}", file=sys.stderr)
            return 1

    return 0


def _print_tunnels(tunnels: list[dict[str, Any]]) -> None:
    """Print tunnel list as table."""
    headers = ["ID", "Type", "Port", "Target", "Client", "Status"]
    rows = []
    for t in tunnels:
        client_info = t.get("Client", {})
        client_name = client_info.get("Remark", "") if client_info else ""
        status = "Running" if t.get("RunStatus") else "Stopped"
        target = t.get("Target", {})
        target_addr = target.get("TargetStr", "") if target else t.get("TargetAddr", "")

        rows.append(
            [
                str(t.get("Id", "")),
                t.get("Mode", ""),
                str(t.get("Port", "")),
                target_addr,
                client_name,
                status,
            ]
        )
    print(format_table(headers, rows))


def cmd_hosts(args: argparse.Namespace) -> int:
    """List host mappings on edge nodes."""
    try:
        cluster = NPSCluster(args.config)
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    if args.all:
        all_hosts = cluster.get_all_hosts()
        for edge_name, hosts in all_hosts.items():
            edge = cluster.get_edge(edge_name)
            region = edge.region if edge else ""
            print(f"\n=== {edge_name} ({region}) ===")
            _print_hosts(hosts)
    else:
        edge_name = args.edge
        if not edge_name:
            edge_name = cluster.edge_names[0] if cluster.edge_names else None
            if not edge_name:
                print("Error: No edges configured", file=sys.stderr)
                return 1

        client = cluster.get_client(edge_name)
        if not client:
            print(f"Error: Edge '{edge_name}' not found", file=sys.stderr)
            return 1

        try:
            hosts = client.list_hosts()
            _print_hosts(hosts)
        except NPSError as e:
            print(f"Error: {e}", file=sys.stderr)
            return 1

    return 0


def _print_hosts(hosts: list[dict[str, Any]]) -> None:
    """Print host list as table."""
    headers = ["ID", "Host", "Target", "Client", "Scheme"]
    rows = []
    for h in hosts:
        client_info = h.get("Client", {})
        client_name = client_info.get("Remark", "") if client_info else ""
        target = h.get("Target", {})
        target_addr = target.get("TargetStr", "") if target else ""

        rows.append(
            [
                str(h.get("Id", "")),
                h.get("Host", ""),
                target_addr,
                client_name,
                h.get("Scheme", "all"),
            ]
        )
    print(format_table(headers, rows))


def cmd_sync(args: argparse.Namespace) -> int:
    """Sync configuration from one edge to others."""
    try:
        cluster = NPSCluster(args.config)
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    source = args.source
    if source not in cluster.edge_names:
        print(f"Error: Source edge '{source}' not found", file=sys.stderr)
        return 1

    # Determine what to sync
    sync_clients = args.type in ("all", "clients")
    sync_tunnels = args.type in ("all", "tunnels")
    sync_hosts = args.type in ("all", "hosts")

    # Confirm
    target_edges = [n for n in cluster.edge_names if n != source]
    if not args.yes:
        print(f"Will sync from '{source}' to: {', '.join(target_edges)}")
        print(
            f"Sync: clients={sync_clients}, tunnels={sync_tunnels}, hosts={sync_hosts}"
        )
        response = input("Continue? [y/N] ")
        if response.lower() != "y":
            print("Aborted.")
            return 0

    try:
        results = cluster.sync_from(
            source,
            sync_clients=sync_clients,
            sync_tunnels=sync_tunnels,
            sync_hosts=sync_hosts,
        )
        for target, ops in results.items():
            print(f"\n{target}:")
            for op, success in ops.items():
                status = "✓" if success else "✗"
                print(f"  {status} {op}")
    except NPSError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    return 0


def cmd_export(args: argparse.Namespace) -> int:
    """Export configuration from an edge."""
    try:
        cluster = NPSCluster(args.config)
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    edge_name = args.edge
    if not edge_name:
        edge_name = cluster.edge_names[0] if cluster.edge_names else None
        if not edge_name:
            print("Error: No edges configured", file=sys.stderr)
            return 1

    client = cluster.get_client(edge_name)
    if not client:
        print(f"Error: Edge '{edge_name}' not found", file=sys.stderr)
        return 1

    try:
        data = {
            "edge": edge_name,
            "clients": client.list_clients(),
            "tunnels": client.list_tunnels(),
            "hosts": client.list_hosts(),
        }

        output = args.output
        if output:
            with open(output, "w") as f:
                json.dump(data, f, indent=2)
            print(f"Exported to {output}")
        else:
            print(json.dumps(data, indent=2))

    except NPSError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    return 0


def cmd_add_host(args: argparse.Namespace) -> int:
    """Add a host mapping to edges."""
    try:
        cluster = NPSCluster(args.config)
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    # Confirm
    if not args.yes:
        if args.edge:
            targets = [args.edge]
        else:
            targets = cluster.edge_names
        print(
            f"Will add host '{args.domain}' -> '{args.target}' to: {', '.join(targets)}"
        )
        print(f"Client: {args.client}")
        response = input("Continue? [y/N] ")
        if response.lower() != "y":
            print("Aborted.")
            return 0

    if args.edge:
        # Single edge
        client = cluster.get_client(args.edge)
        if not client:
            print(f"Error: Edge '{args.edge}' not found", file=sys.stderr)
            return 1

        try:
            # Find client
            clients = client.list_clients(search=args.client)
            matching = [c for c in clients if c.get("Remark") == args.client]
            if not matching:
                print(
                    f"Error: Client '{args.client}' not found on {args.edge}",
                    file=sys.stderr,
                )
                return 1

            client_id = matching[0]["Id"]
            success = client.add_host(
                client_id=client_id,
                host=args.domain,
                target=args.target,
                remark=args.remark or "",
            )
            if success:
                print(f"✓ Added host to {args.edge}")
            else:
                print(f"✗ Failed to add host to {args.edge}")
                return 1
        except NPSError as e:
            print(f"Error: {e}", file=sys.stderr)
            return 1
    else:
        # All edges
        results = cluster.broadcast_host(
            client_remark=args.client,
            host=args.domain,
            target=args.target,
            remark=args.remark or "",
        )
        for edge, success in results.items():
            status = "✓" if success else "✗"
            print(f"{status} {edge}")

    return 0


def get_template_path() -> Path:
    """Get the path to the templates directory.

    Returns:
        Path to templates directory.
    """
    # Try package templates first (inside src/nps_ctl/templates)
    pkg_templates = Path(__file__).parent / "templates"
    if pkg_templates.exists():
        return pkg_templates

    # Try relative to config
    return Path("templates")


def cmd_install(args: argparse.Namespace) -> int:
    """Install NPS on edge nodes via SSH."""
    import tomllib

    try:
        cluster = NPSCluster(args.config)
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    # Load full config to get web credentials and auth_crypt_key
    config_path = Path(args.config)
    with open(config_path, "rb") as f:
        full_config = tomllib.load(f)

    web_config = full_config.get("web", {})
    web_username = web_config.get("username", "admin")
    web_password = web_config.get("password", "")
    auth_crypt_key = full_config.get("auth_crypt_key", "")
    public_vkey = full_config.get("public_vkey", "2*u@unrNdzyv6E!iB@fT")

    # Port configuration with defaults
    ports_config = full_config.get("ports", {})
    http_proxy_port = ports_config.get("http_proxy", 30080)
    bridge_port = ports_config.get("bridge", 51234)
    web_port = ports_config.get("web", 25412)

    # Load template
    template_path = args.template
    if template_path:
        template_path = Path(template_path)
    else:
        template_path = get_template_path() / "nps.conf.template"

    try:
        template = load_template(template_path)
    except FileNotFoundError:
        print(f"Warning: Template not found at {template_path}, using default")
        template = None

    # Determine target edges
    if args.edge:
        if args.edge not in cluster.edge_names:
            print(f"Error: Edge '{args.edge}' not found", file=sys.stderr)
            return 1
        target_edges = [args.edge]
    else:
        target_edges = cluster.edge_names

    # Confirm
    if not args.yes:
        print(f"Will install NPS on: {', '.join(target_edges)}")
        print("This will:")
        print("  - Download NPS from GitHub releases (djylb/nps)")
        print("  - Install to /etc/nps/ using nps install")
        print("  - Configure and start NPS")
        response = input("Continue? [y/N] ")
        if response.lower() != "y":
            print("Aborted.")
            return 0

    success_count = 0
    fail_count = 0

    for edge_name in target_edges:
        edge = cluster.get_edge(edge_name)
        if not edge or not edge.ssh_host:
            print(f"✗ {edge_name}: No SSH host configured")
            fail_count += 1
            continue

        print(f"\nInstalling NPS on {edge_name} ({edge.ssh_host})...")

        # Generate config for this edge
        variables = {
            "web_username": web_username,
            "web_password": web_password,
            "auth_key": edge.auth_key,
            "auth_crypt_key": auth_crypt_key,
            "public_vkey": public_vkey,
            "http_proxy_port": http_proxy_port,
            "bridge_port": bridge_port,
            "web_port": web_port,
        }

        if template:
            nps_conf = render_template(template, variables)
        else:
            # Fallback to inline template
            nps_conf = _get_default_template().format(**variables)

        result = install_nps(
            ssh_host=edge.ssh_host,
            nps_conf=nps_conf,
            release_url=args.release_url or DEFAULT_NPS_RELEASE_URL,
        )

        if result.success:
            print(f"✓ {edge_name}: Installed successfully")
            if args.verbose and result.stdout:
                for line in result.stdout.strip().split("\n"):
                    print(f"  {line}")
            success_count += 1
        else:
            print(f"✗ {edge_name}: {result.message}")
            if result.stderr:
                for line in result.stderr.strip().split("\n"):
                    print(f"  {line}")
            if result.stdout:
                for line in result.stdout.strip().split("\n"):
                    print(f"  {line}")
            fail_count += 1

    print(f"\nSummary: {success_count} succeeded, {fail_count} failed")
    return 0 if fail_count == 0 else 1


def _get_default_template() -> str:
    """Get the default NPS configuration template."""
    return """#############################################
# NPS Edge Node Configuration
#############################################

appname=nps
runmode=pro
dns_server=1.1.1.1

#############################################
# HTTP Proxy Settings
#############################################
http_proxy_ip=0.0.0.0
http_proxy_port={http_proxy_port}

http_add_origin_header=true
allow_x_real_ip=true
trusted_proxy_ips=127.0.0.1

#############################################
# Client Connection Settings
#############################################
bridge_ip=0.0.0.0
bridge_port={bridge_port}

public_vkey={public_vkey}
disconnect_timeout=60

#############################################
# Web Management Settings
#############################################
web_username={web_username}
web_password={web_password}
open_captcha=true

web_ip=127.0.0.1
web_port={web_port}
web_open_ssl=false

allow_user_login=false
allow_user_register=false
allow_user_change_username=false

#############################################
# API Security Settings
#############################################
auth_key={auth_key}
auth_crypt_key={auth_crypt_key}

#############################################
# Extended Features
#############################################
flow_store_interval=1
allow_flow_limit=true
allow_rate_limit=true
allow_time_limit=true
allow_tunnel_num_limit=true
allow_local_proxy=false
allow_connection_num_limit=true
allow_multi_ip=true
system_info_display=true

#############################################
# Logging
#############################################
log_level=4
log_path=/var/log/nps.log
log_max_files=10
log_max_days=7
log_max_size=2
"""


def cmd_uninstall(args: argparse.Namespace) -> int:
    """Uninstall NPS from edge nodes via SSH."""
    try:
        cluster = NPSCluster(args.config)
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    # Determine target edges
    if args.edge:
        if args.edge not in cluster.edge_names:
            print(f"Error: Edge '{args.edge}' not found", file=sys.stderr)
            return 1
        target_edges = [args.edge]
    else:
        target_edges = cluster.edge_names

    # Confirm
    if not args.yes:
        print(f"Will uninstall NPS from: {', '.join(target_edges)}")
        print("This will:")
        print("  - Stop and disable Nps.service")
        print("  - Remove /usr/bin/nps")
        print("  - Remove /etc/nps/")
        response = input("Continue? [y/N] ")
        if response.lower() != "y":
            print("Aborted.")
            return 0

    success_count = 0
    fail_count = 0

    for edge_name in target_edges:
        edge = cluster.get_edge(edge_name)
        if not edge or not edge.ssh_host:
            print(f"✗ {edge_name}: No SSH host configured")
            fail_count += 1
            continue

        print(f"\nUninstalling NPS from {edge_name} ({edge.ssh_host})...")

        result = uninstall_nps(ssh_host=edge.ssh_host)

        if result.success:
            print(f"✓ {edge_name}: Uninstalled successfully")
            if args.verbose and result.stdout:
                for line in result.stdout.strip().split("\n"):
                    print(f"  {line}")
            success_count += 1
        else:
            print(f"✗ {edge_name}: {result.message}")
            if result.stderr:
                for line in result.stderr.strip().split("\n"):
                    print(f"  {line}")
            fail_count += 1

    print(f"\nSummary: {success_count} succeeded, {fail_count} failed")
    return 0 if fail_count == 0 else 1


def cmd_add_tunnel(args: argparse.Namespace) -> int:
    """Add a tunnel to an edge."""
    try:
        cluster = NPSCluster(args.config)
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    edge_name = args.edge
    if not edge_name:
        edge_name = cluster.edge_names[0] if cluster.edge_names else None
        if not edge_name:
            print("Error: No edges configured", file=sys.stderr)
            return 1

    client = cluster.get_client(edge_name)
    if not client:
        print(f"Error: Edge '{edge_name}' not found", file=sys.stderr)
        return 1

    # Confirm
    if not args.yes:
        print(f"Will add {args.type} tunnel on {edge_name}")
        print(
            f"Client: {args.client}, Port: {args.port}, Target: {args.target or 'N/A'}"
        )
        response = input("Continue? [y/N] ")
        if response.lower() != "y":
            print("Aborted.")
            return 0

    try:
        # Find client
        clients = client.list_clients(search=args.client)
        matching = [c for c in clients if c.get("Remark") == args.client]
        if not matching:
            print(f"Error: Client '{args.client}' not found", file=sys.stderr)
            return 1

        client_id = matching[0]["Id"]
        success = client.add_tunnel(
            client_id=client_id,
            tunnel_type=args.type,
            port=args.port,
            target=args.target or "",
            remark=args.remark or "",
        )
        if success:
            print(f"✓ Added tunnel to {edge_name}")
        else:
            print("✗ Failed to add tunnel")
            return 1
    except NPSError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    return 0


def create_parser() -> argparse.ArgumentParser:
    """Create the argument parser."""
    parser = argparse.ArgumentParser(
        prog="nps-ctl",
        description="NPS multi-edge management tool",
    )
    parser.add_argument(
        "-c",
        "--config",
        default=None,
        help="Path to edges.toml configuration file",
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # status command
    status_parser = subparsers.add_parser(
        "status", help="Show status of all edge nodes"
    )
    status_parser.set_defaults(func=cmd_status)

    # clients command
    clients_parser = subparsers.add_parser("clients", help="List clients")
    clients_parser.add_argument("--edge", "-e", help="Edge name")
    clients_parser.add_argument(
        "--all", "-a", action="store_true", help="Show all edges"
    )
    clients_parser.set_defaults(func=cmd_clients)

    # tunnels command
    tunnels_parser = subparsers.add_parser("tunnels", help="List tunnels")
    tunnels_parser.add_argument("--edge", "-e", help="Edge name")
    tunnels_parser.add_argument(
        "--all", "-a", action="store_true", help="Show all edges"
    )
    tunnels_parser.set_defaults(func=cmd_tunnels)

    # hosts command
    hosts_parser = subparsers.add_parser("hosts", help="List host mappings")
    hosts_parser.add_argument("--edge", "-e", help="Edge name")
    hosts_parser.add_argument("--all", "-a", action="store_true", help="Show all edges")
    hosts_parser.set_defaults(func=cmd_hosts)

    # sync command
    sync_parser = subparsers.add_parser(
        "sync", help="Sync configuration from one edge to others"
    )
    sync_parser.add_argument(
        "--from", "-f", dest="source", required=True, help="Source edge name"
    )
    sync_parser.add_argument(
        "--type",
        "-t",
        choices=["all", "clients", "tunnels", "hosts"],
        default="all",
        help="What to sync",
    )
    sync_parser.add_argument(
        "--yes", "-y", action="store_true", help="Skip confirmation"
    )
    sync_parser.set_defaults(func=cmd_sync)

    # export command
    export_parser = subparsers.add_parser("export", help="Export configuration")
    export_parser.add_argument("--edge", "-e", help="Edge name")
    export_parser.add_argument("--output", "-o", help="Output file path")
    export_parser.set_defaults(func=cmd_export)

    # add-host command
    add_host_parser = subparsers.add_parser("add-host", help="Add a host mapping")
    add_host_parser.add_argument("--domain", "-d", required=True, help="Domain name")
    add_host_parser.add_argument("--client", "-c", required=True, help="Client remark")
    add_host_parser.add_argument(
        "--target", "-t", required=True, help="Target address (e.g., :8080)"
    )
    add_host_parser.add_argument(
        "--edge", "-e", help="Edge name (all edges if not specified)"
    )
    add_host_parser.add_argument("--remark", "-r", help="Remark")
    add_host_parser.add_argument(
        "--yes", "-y", action="store_true", help="Skip confirmation"
    )
    add_host_parser.set_defaults(func=cmd_add_host)

    # install command
    install_parser = subparsers.add_parser(
        "install", help="Install NPS on edge nodes via SSH"
    )
    install_parser.add_argument(
        "--edge", "-e", help="Edge name (all edges if not specified)"
    )
    install_parser.add_argument(
        "--template", "-t", help="Path to nps.conf template file"
    )
    install_parser.add_argument("--release-url", help="Custom NPS release URL")
    install_parser.add_argument(
        "--yes", "-y", action="store_true", help="Skip confirmation"
    )
    install_parser.add_argument(
        "--verbose", "-v", action="store_true", help="Show detailed output"
    )
    install_parser.set_defaults(func=cmd_install)

    # uninstall command
    uninstall_parser = subparsers.add_parser(
        "uninstall", help="Uninstall NPS from edge nodes via SSH"
    )
    uninstall_parser.add_argument(
        "--edge", "-e", help="Edge name (all edges if not specified)"
    )
    uninstall_parser.add_argument(
        "--yes", "-y", action="store_true", help="Skip confirmation"
    )
    uninstall_parser.add_argument(
        "--verbose", "-v", action="store_true", help="Show detailed output"
    )
    uninstall_parser.set_defaults(func=cmd_uninstall)

    # add-tunnel command
    add_tunnel_parser = subparsers.add_parser("add-tunnel", help="Add a tunnel")
    add_tunnel_parser.add_argument(
        "--client", "-c", required=True, help="Client remark"
    )
    add_tunnel_parser.add_argument(
        "--type",
        "-t",
        choices=["tcp", "udp", "socks5", "httpProxy"],
        default="tcp",
        help="Tunnel type",
    )
    add_tunnel_parser.add_argument(
        "--port", "-p", type=int, default=0, help="Server port"
    )
    add_tunnel_parser.add_argument("--target", help="Target address")
    add_tunnel_parser.add_argument("--edge", "-e", help="Edge name")
    add_tunnel_parser.add_argument("--remark", "-r", help="Remark")
    add_tunnel_parser.add_argument(
        "--yes", "-y", action="store_true", help="Skip confirmation"
    )
    add_tunnel_parser.set_defaults(func=cmd_add_tunnel)

    return parser


def main() -> int:
    """Main entry point."""
    parser = create_parser()
    args = parser.parse_args()

    # Find config file if not specified
    if args.config is None:
        try:
            args.config = get_default_config_path()
        except FileNotFoundError as e:
            print(f"Error: {e}", file=sys.stderr)
            return 1

    if args.command is None:
        parser.print_help()
        return 0

    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
