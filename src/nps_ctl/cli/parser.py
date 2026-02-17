"""Command-line argument parser for nps-ctl.

Defines the CLI structure with nested subcommands organized by resource type:
client, edge, tunnel, host, and util.
"""

import argparse


def create_parser() -> argparse.ArgumentParser:
    """Create the argument parser with nested subcommand groups.

    Returns:
        Configured ArgumentParser instance.
    """
    parser = argparse.ArgumentParser(
        prog="nps-ctl",
        description="NPS multi-edge cluster management tool",
    )

    # Global options
    parser.add_argument(
        "--config",
        "-c",
        help="Path to edges.toml config file",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose output",
    )
    parser.add_argument(
        "--proxy",
        help="HTTP proxy URL",
    )
    parser.add_argument(
        "--socks-proxy",
        help="SOCKS5 proxy URL",
    )
    parser.add_argument(
        "--auto-proxy",
        help="Auto-create SSH SOCKS proxy via specified host",
    )
    parser.add_argument(
        "--no-ssl-verify",
        action="store_true",
        help="Disable SSL certificate verification",
    )

    # Top-level subcommands
    subparsers = parser.add_subparsers(dest="command", help="Command group")

    # ========== client commands ==========
    _add_client_commands(subparsers)

    # ========== edge commands ==========
    _add_edge_commands(subparsers)

    # ========== tunnel commands ==========
    _add_tunnel_commands(subparsers)

    # ========== host commands ==========
    _add_host_commands(subparsers)

    # ========== util commands ==========
    _add_util_commands(subparsers)

    return parser


def _add_client_commands(subparsers) -> None:
    """Add client subcommands (NPC management).

    Args:
        subparsers: Parent subparsers object.
    """
    client_parser = subparsers.add_parser(
        "client",
        help="NPC client management",
        description="Manage NPC clients: list, push, install, uninstall, status, restart.",
    )
    client_sub = client_parser.add_subparsers(dest="subcommand", help="Client action")

    # client list (原 npc-list + clients)
    list_parser = client_sub.add_parser(
        "list",
        help="List clients from NPS API and optionally update clients.toml",
        description=(
            "Fetch client list from a specific edge's NPS API and optionally "
            "update the clients.toml configuration file."
        ),
    )
    list_parser.add_argument(
        "-e",
        "--edge",
        help="Edge name to query clients from (required for updating clients.toml)",
    )
    list_parser.add_argument(
        "-a",
        "--all",
        action="store_true",
        help="Show clients from all edges",
    )
    list_parser.add_argument(
        "--update",
        action="store_true",
        help="Update clients.toml with fetched client info",
    )
    list_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be written without modifying clients.toml",
    )
    list_parser.set_defaults(requires_config=True)

    # client push (新功能)
    push_parser = client_sub.add_parser(
        "push",
        help="Push client configs from clients.toml to edges",
        description=(
            "Read client configurations from clients.toml and ensure they "
            "exist on the corresponding edges via NPS API."
        ),
    )
    push_parser.add_argument(
        "-c",
        "--client",
        help="Specific client name to push (default: all clients)",
    )
    push_parser.add_argument(
        "-e",
        "--edge",
        help="Specific edge to push to (default: all edges in client config)",
    )
    push_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be pushed without making changes",
    )
    push_parser.add_argument(
        "--update",
        action="store_true",
        help="Update existing clients on edges (sync vkey from clients.toml)",
    )
    push_parser.add_argument(
        "-y",
        "--yes",
        action="store_true",
        help="Skip confirmation prompts",
    )
    push_parser.set_defaults(requires_config=True)

    # client add (新功能 - interactive add)
    add_parser = client_sub.add_parser(
        "add",
        help="Interactively add a new client entry to clients.toml",
        description=(
            "Add a new NPC client entry to clients.toml via interactive prompts. "
            "A vkey is auto-generated unless provided by the user."
        ),
    )
    add_parser.add_argument(
        "--name",
        help="Client name (skip interactive prompt for this field)",
    )
    add_parser.add_argument(
        "--ssh-host",
        help="SSH host (skip interactive prompt for this field)",
    )
    add_parser.add_argument(
        "--edges",
        nargs="+",
        help="Edge names (skip interactive prompt for this field)",
    )
    add_parser.add_argument(
        "--vkey",
        help="Verify key (auto-generated if not provided)",
    )
    add_parser.add_argument(
        "--conn-type",
        choices=["tls", "tcp", "kcp"],
        help="Connection type (default: tls)",
    )
    add_parser.add_argument(
        "-y",
        "--yes",
        action="store_true",
        help="Skip confirmation prompts",
    )
    add_parser.set_defaults(requires_config=True)

    # client install (原 npc-install)
    install_parser = client_sub.add_parser(
        "install",
        help="Install NPC on client machines via SSH",
        description="Install NPC (NPS client) on remote machines via SSH.",
    )
    install_parser.add_argument(
        "-c",
        "--client",
        help="Client name to install (default: all clients)",
    )
    install_parser.add_argument(
        "--version",
        help="NPC version to install",
    )
    install_parser.add_argument(
        "--release-url",
        help="Custom release URL for NPC binary",
    )
    install_parser.add_argument(
        "--force-reinstall",
        action="store_true",
        help="Force reinstall even if already installed",
    )
    install_parser.add_argument(
        "-y",
        "--yes",
        action="store_true",
        help="Skip confirmation prompts",
    )
    install_parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        dest="deploy_verbose",
        help="Show detailed deployment output",
    )
    install_parser.set_defaults(requires_config=True)

    # client uninstall (原 npc-uninstall)
    uninstall_parser = client_sub.add_parser(
        "uninstall",
        help="Uninstall NPC from client machines via SSH",
        description="Uninstall NPC from remote machines via SSH.",
    )
    uninstall_parser.add_argument(
        "-c",
        "--client",
        help="Client name to uninstall (default: all clients)",
    )
    uninstall_parser.add_argument(
        "-y",
        "--yes",
        action="store_true",
        help="Skip confirmation prompts",
    )
    uninstall_parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        dest="deploy_verbose",
        help="Show detailed deployment output",
    )
    uninstall_parser.set_defaults(requires_config=True)

    # client status (原 npc-status)
    status_parser = client_sub.add_parser(
        "status",
        help="Check NPC status on client machines",
        description="Check the status of NPC service on remote machines via SSH.",
    )
    status_parser.add_argument(
        "-c",
        "--client",
        help="Client name to check (default: all clients)",
    )
    status_parser.add_argument(
        "--parallel",
        action="store_true",
        help="Check all clients in parallel via SSH",
    )
    status_parser.set_defaults(requires_config=True)

    # client restart (原 npc-restart)
    restart_parser = client_sub.add_parser(
        "restart",
        help="Restart NPC service on client machines",
        description="Restart the NPC service on remote machines via SSH.",
    )
    restart_parser.add_argument(
        "-c",
        "--client",
        help="Client name to restart (default: all clients)",
    )
    restart_parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        dest="deploy_verbose",
        help="Show detailed output",
    )
    restart_parser.set_defaults(requires_config=True)


def _add_edge_commands(subparsers) -> None:
    """Add edge subcommands (NPS server management).

    Args:
        subparsers: Parent subparsers object.
    """
    edge_parser = subparsers.add_parser(
        "edge",
        help="NPS edge node management",
        description="Manage NPS edge nodes: status, install, uninstall, sync, export.",
    )
    edge_sub = edge_parser.add_subparsers(dest="subcommand", help="Edge action")

    # edge status (原 status)
    status_parser = edge_sub.add_parser(
        "status",
        help="Show status of all edge nodes",
        description="Display the status of all configured NPS edge nodes.",
    )
    status_parser.set_defaults(requires_config=True)

    # edge install (原 install)
    install_parser = edge_sub.add_parser(
        "install",
        help="Install NPS on edge nodes via SSH",
        description="Install NPS server on remote edge nodes via SSH.",
    )
    install_parser.add_argument(
        "-e",
        "--edge",
        help="Edge name to install (default: all edges)",
    )
    install_parser.add_argument(
        "-t",
        "--template",
        help="Path to NPS config template",
    )
    install_parser.add_argument(
        "--version",
        help="NPS version to install",
    )
    install_parser.add_argument(
        "--release-url",
        help="Custom release URL for NPS binary",
    )
    install_parser.add_argument(
        "--force-reinstall",
        action="store_true",
        help="Force reinstall even if already installed",
    )
    install_parser.add_argument(
        "-y",
        "--yes",
        action="store_true",
        help="Skip confirmation prompts",
    )
    install_parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        dest="deploy_verbose",
        help="Show detailed deployment output",
    )
    install_parser.set_defaults(requires_config=True)

    # edge uninstall (原 uninstall)
    uninstall_parser = edge_sub.add_parser(
        "uninstall",
        help="Uninstall NPS from edge nodes via SSH",
        description="Uninstall NPS server from remote edge nodes via SSH.",
    )
    uninstall_parser.add_argument(
        "-e",
        "--edge",
        help="Edge name to uninstall (default: all edges)",
    )
    uninstall_parser.add_argument(
        "-y",
        "--yes",
        action="store_true",
        help="Skip confirmation prompts",
    )
    uninstall_parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        dest="deploy_verbose",
        help="Show detailed deployment output",
    )
    uninstall_parser.set_defaults(requires_config=True)

    # edge sync (原 sync)
    sync_parser = edge_sub.add_parser(
        "sync",
        help="Sync configuration from one edge to others",
        description=(
            "Synchronize client, tunnel, and host configurations "
            "from a source edge to target edges."
        ),
    )
    sync_parser.add_argument(
        "-f",
        "--from",
        required=True,
        dest="source",
        help="Source edge name to sync from",
    )
    sync_parser.add_argument(
        "--to",
        "-e",
        "--edge",
        dest="target",
        nargs="+",
        help="Target edge name(s) to sync to (default: all other edges)",
    )
    sync_parser.add_argument(
        "-t",
        "--type",
        choices=["all", "clients", "tunnels", "hosts"],
        default="all",
        help="Type of configuration to sync (default: all)",
    )
    sync_parser.add_argument(
        "-y",
        "--yes",
        action="store_true",
        help="Skip confirmation prompts",
    )
    sync_parser.add_argument(
        "--parallel",
        action="store_true",
        help="Sync to targets in parallel",
    )
    sync_parser.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        help="Suppress detailed output",
    )
    sync_parser.add_argument(
        "-w",
        "--workers",
        type=int,
        help="Number of parallel workers",
    )
    sync_parser.set_defaults(requires_config=True)

    # edge export (原 export)
    export_parser = edge_sub.add_parser(
        "export",
        help="Export configuration",
        description="Export edge configuration to a file.",
    )
    export_parser.add_argument(
        "-e",
        "--edge",
        help="Edge name to export (default: all edges)",
    )
    export_parser.add_argument(
        "-o",
        "--output",
        help="Output file path",
    )
    export_parser.set_defaults(requires_config=True)


def _add_tunnel_commands(subparsers) -> None:
    """Add tunnel subcommands.

    Args:
        subparsers: Parent subparsers object.
    """
    tunnel_parser = subparsers.add_parser(
        "tunnel",
        help="Tunnel management",
        description="Manage tunnels: list, add.",
    )
    tunnel_sub = tunnel_parser.add_subparsers(dest="subcommand", help="Tunnel action")

    # tunnel list (原 tunnels)
    list_parser = tunnel_sub.add_parser(
        "list",
        help="List tunnels",
        description="List all tunnels on edge nodes.",
    )
    list_parser.add_argument(
        "-e",
        "--edge",
        help="Edge name to query (default: first edge)",
    )
    list_parser.add_argument(
        "-t",
        "--type",
        choices=["tcp", "udp", "socks5", "httpProxy", "secret", "p2p", "file"],
        help="Filter by tunnel type",
    )
    list_parser.add_argument(
        "-a",
        "--all",
        action="store_true",
        help="Show tunnels from all edges",
    )
    list_parser.set_defaults(requires_config=True)

    # tunnel add (原 add-tunnel)
    add_parser = tunnel_sub.add_parser(
        "add",
        help="Add a tunnel",
        description="Add a new tunnel to edge nodes.",
    )
    add_parser.add_argument(
        "-c",
        "--client",
        required=True,
        help="Client remark or ID",
    )
    add_parser.add_argument(
        "-t",
        "--type",
        choices=["tcp", "udp", "socks5", "httpProxy"],
        default="tcp",
        help="Tunnel type (default: tcp)",
    )
    add_parser.add_argument(
        "-p",
        "--port",
        type=int,
        help="Server port",
    )
    add_parser.add_argument(
        "--target",
        help="Target address (host:port)",
    )
    add_parser.add_argument(
        "-e",
        "--edge",
        help="Edge name to add tunnel to (default: all edges)",
    )
    add_parser.add_argument(
        "-r",
        "--remark",
        help="Tunnel remark",
    )
    add_parser.add_argument(
        "-y",
        "--yes",
        action="store_true",
        help="Skip confirmation prompts",
    )
    add_parser.set_defaults(requires_config=True)


def _add_host_commands(subparsers) -> None:
    """Add host subcommands.

    Args:
        subparsers: Parent subparsers object.
    """
    host_parser = subparsers.add_parser(
        "host",
        help="Host mapping management",
        description="Manage host mappings: list, add.",
    )
    host_sub = host_parser.add_subparsers(dest="subcommand", help="Host action")

    # host list (原 hosts)
    list_parser = host_sub.add_parser(
        "list",
        help="List host mappings",
        description="List all host mappings on edge nodes.",
    )
    list_parser.add_argument(
        "-e",
        "--edge",
        help="Edge name to query (default: first edge)",
    )
    list_parser.add_argument(
        "-a",
        "--all",
        action="store_true",
        help="Show host mappings from all edges",
    )
    list_parser.set_defaults(requires_config=True)

    # host add (原 add-host)
    add_parser = host_sub.add_parser(
        "add",
        help="Add a host mapping",
        description="Add a new host mapping to edge nodes.",
    )
    add_parser.add_argument(
        "-d",
        "--domain",
        required=True,
        help="Domain name",
    )
    add_parser.add_argument(
        "-c",
        "--client",
        required=True,
        help="Client remark or ID",
    )
    add_parser.add_argument(
        "-t",
        "--target",
        required=True,
        help="Target address (host:port)",
    )
    add_parser.add_argument(
        "-e",
        "--edge",
        help="Edge name to add host mapping to (default: all edges)",
    )
    add_parser.add_argument(
        "-r",
        "--remark",
        help="Host mapping remark",
    )
    add_parser.add_argument(
        "-y",
        "--yes",
        action="store_true",
        help="Skip confirmation prompts",
    )
    add_parser.set_defaults(requires_config=True)


def _add_util_commands(subparsers) -> None:
    """Add utility subcommands.

    Args:
        subparsers: Parent subparsers object.
    """
    util_parser = subparsers.add_parser(
        "util",
        help="Utility commands",
        description="Utility commands: generate-auth-key.",
    )
    util_sub = util_parser.add_subparsers(dest="subcommand", help="Utility action")

    # util generate-auth-key (原 generate-auth-key)
    gen_key_parser = util_sub.add_parser(
        "generate-auth-key",
        help="Generate a random auth key",
        description="Generate a random authentication key for NPS.",
    )
    gen_key_parser.add_argument(
        "length",
        nargs="?",
        type=int,
        default=43,
        help="Key length (default: 43)",
    )
    gen_key_parser.set_defaults(requires_config=False)
