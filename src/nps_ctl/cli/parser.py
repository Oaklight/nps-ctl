"""Command-line argument parser for nps-ctl.

Defines the CLI structure with nested subcommands organized by resource type:
client, edge, tunnel, host, and util.
"""

import argparse

from .. import __version__
from .helpers import (
    add_client_argument,
    add_edge_argument,
    add_verbose_argument,
    add_yes_argument,
)


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
        "--version",
        "-V",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    parser.add_argument(
        "--config",
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

    # client list
    list_parser = client_sub.add_parser(
        "list",
        help="List clients from NPS API and optionally update clients.toml",
        description=(
            "Fetch client list from a specific edge's NPS API and optionally "
            "update the clients.toml configuration file."
        ),
    )
    add_edge_argument(
        list_parser,
        help_text="Edge name to query clients from (required for updating clients.toml)",
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

    # client push
    push_parser = client_sub.add_parser(
        "push",
        help="Push client configs from clients.toml to edges",
        description=(
            "Read client configurations from clients.toml and ensure they "
            "exist on the corresponding edges via NPS API."
        ),
    )
    add_client_argument(
        push_parser,
        help_text="Specific client name to push (default: all clients)",
    )
    add_edge_argument(
        push_parser,
        help_text="Specific edge to push to (default: all edges in client config)",
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
    add_yes_argument(push_parser)
    push_parser.set_defaults(requires_config=True)

    # client add (interactive)
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
    add_yes_argument(add_parser)
    add_parser.set_defaults(requires_config=True)

    # client install
    install_parser = client_sub.add_parser(
        "install",
        help="Install NPC on client machines via SSH",
        description="Install NPC (NPS client) on remote machines via SSH.",
    )
    add_client_argument(
        install_parser,
        help_text="Client name to install (default: all clients)",
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
        help="(Deprecated: use 'client upgrade') Force reinstall",
    )
    add_yes_argument(install_parser)
    add_verbose_argument(install_parser)
    install_parser.set_defaults(requires_config=True)

    # client upgrade
    upgrade_parser = client_sub.add_parser(
        "upgrade",
        help="Upgrade NPC binary and reconfigure on client machines",
        description=(
            "Download a new NPC binary, uninstall the existing one, and "
            "reinstall with current configuration from edges.toml/clients.toml."
        ),
    )
    add_client_argument(
        upgrade_parser,
        help_text="Client name to upgrade (default: all clients)",
    )
    upgrade_parser.add_argument(
        "--version",
        help="NPC version to install",
    )
    upgrade_parser.add_argument(
        "--release-url",
        help="Custom release URL for NPC binary",
    )
    add_yes_argument(upgrade_parser)
    add_verbose_argument(upgrade_parser)
    upgrade_parser.set_defaults(requires_config=True)

    # client reconfig
    reconfig_parser = client_sub.add_parser(
        "reconfig",
        help="Reconfigure NPC with updated server addresses (no binary download)",
        description=(
            "Update NPC configuration (server addresses, vkey) from "
            "edges.toml/clients.toml without re-downloading the binary. "
            "Much faster than reinstall when only config changes."
        ),
    )
    add_client_argument(
        reconfig_parser,
        help_text="Client name to reconfigure (default: all clients)",
    )
    add_yes_argument(reconfig_parser)
    add_verbose_argument(reconfig_parser)
    reconfig_parser.set_defaults(requires_config=True)

    # client uninstall
    uninstall_parser = client_sub.add_parser(
        "uninstall",
        help="Uninstall NPC from client machines via SSH",
        description="Uninstall NPC from remote machines via SSH.",
    )
    add_client_argument(
        uninstall_parser,
        help_text="Client name to uninstall (default: all clients)",
    )
    add_yes_argument(uninstall_parser)
    add_verbose_argument(uninstall_parser)
    uninstall_parser.set_defaults(requires_config=True)

    # client status
    status_parser = client_sub.add_parser(
        "status",
        help="Check NPC status on client machines",
        description="Check the status of NPC service on remote machines via SSH.",
    )
    add_client_argument(
        status_parser,
        help_text="Client name to check (default: all clients)",
    )
    status_parser.add_argument(
        "--parallel",
        action="store_true",
        help="Check all clients in parallel via SSH",
    )
    status_parser.set_defaults(requires_config=True)

    # client restart
    restart_parser = client_sub.add_parser(
        "restart",
        help="Restart NPC service on client machines",
        description="Restart the NPC service on remote machines via SSH.",
    )
    add_client_argument(
        restart_parser,
        help_text="Client name to restart (default: all clients)",
    )
    add_verbose_argument(restart_parser)
    restart_parser.set_defaults(requires_config=True)

    # client del
    del_parser = client_sub.add_parser(
        "del",
        help="Delete a client from edge(s)",
        description="Delete a client from one or all edge nodes via NPS API.",
    )
    del_id_group = del_parser.add_mutually_exclusive_group(required=True)
    del_id_group.add_argument(
        "--id",
        type=int,
        help="Client ID (edge-specific, requires -e)",
    )
    del_id_group.add_argument(
        "-r",
        "--remark",
        help="Client remark name (can operate across all edges)",
    )
    del_id_group.add_argument(
        "--name",
        dest="remark",
        help=argparse.SUPPRESS,  # hidden backward-compat alias
    )
    add_edge_argument(
        del_parser,
        help_text="Edge name (required when using --id, default: all edges for --remark)",
    )
    add_yes_argument(del_parser)
    del_parser.set_defaults(requires_config=True)


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

    # edge status
    status_parser = edge_sub.add_parser(
        "status",
        help="Show status of all edge nodes",
        description="Display the status of all configured NPS edge nodes.",
    )
    status_parser.set_defaults(requires_config=True)

    # edge install
    install_parser = edge_sub.add_parser(
        "install",
        help="Install NPS on edge nodes via SSH",
        description="Install NPS server on remote edge nodes via SSH.",
    )
    add_edge_argument(
        install_parser,
        help_text="Edge name to install (default: all edges)",
    )
    install_parser.add_argument(
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
        help="(Deprecated: use 'edge upgrade') Force reinstall",
    )
    add_yes_argument(install_parser)
    add_verbose_argument(install_parser)
    install_parser.set_defaults(requires_config=True)

    # edge upgrade
    edge_upgrade_parser = edge_sub.add_parser(
        "upgrade",
        help="Upgrade NPS binary on edge nodes (preserves data)",
        description=(
            "Download a new NPS binary and replace the existing one in-place. "
            "Data files (clients, hosts, tunnels) are backed up and preserved."
        ),
    )
    add_edge_argument(
        edge_upgrade_parser,
        help_text="Edge name to upgrade (default: all edges)",
    )
    edge_upgrade_parser.add_argument(
        "--template",
        help="Path to NPS config template",
    )
    edge_upgrade_parser.add_argument(
        "--version",
        help="NPS version to install",
    )
    edge_upgrade_parser.add_argument(
        "--release-url",
        help="Custom release URL for NPS binary",
    )
    add_yes_argument(edge_upgrade_parser)
    add_verbose_argument(edge_upgrade_parser)
    edge_upgrade_parser.set_defaults(requires_config=True)

    # edge reconfig
    edge_reconfig_parser = edge_sub.add_parser(
        "reconfig",
        help="Reconfigure NPS with updated config (no binary download)",
        description=(
            "Update NPS configuration from template and edges.toml "
            "without re-downloading the binary. Restarts the service."
        ),
    )
    add_edge_argument(
        edge_reconfig_parser,
        help_text="Edge name to reconfigure (default: all edges)",
    )
    edge_reconfig_parser.add_argument(
        "--template",
        help="Path to NPS config template",
    )
    add_yes_argument(edge_reconfig_parser)
    add_verbose_argument(edge_reconfig_parser)
    edge_reconfig_parser.set_defaults(requires_config=True)

    # edge uninstall
    uninstall_parser = edge_sub.add_parser(
        "uninstall",
        help="Uninstall NPS from edge nodes via SSH",
        description="Uninstall NPS server from remote edge nodes via SSH.",
    )
    add_edge_argument(
        uninstall_parser,
        help_text="Edge name to uninstall (default: all edges)",
    )
    add_yes_argument(uninstall_parser)
    add_verbose_argument(uninstall_parser)
    uninstall_parser.set_defaults(requires_config=True)

    # edge sync
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
    # edge sync uses --to as an alias alongside -e/--edge
    sync_parser.add_argument(
        "-e",
        "--edge",
        "--to",
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
    add_yes_argument(sync_parser)
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

    # edge export
    export_parser = edge_sub.add_parser(
        "export",
        help="Export configuration",
        description="Export edge configuration to a file.",
    )
    add_edge_argument(
        export_parser,
        help_text="Edge name to export (default: all edges)",
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
        description="Manage tunnels: list, add, edit, del, start, stop.",
    )
    tunnel_sub = tunnel_parser.add_subparsers(dest="subcommand", help="Tunnel action")

    # tunnel list
    list_parser = tunnel_sub.add_parser(
        "list",
        help="List tunnels",
        description="List all tunnels on edge nodes.",
    )
    add_edge_argument(
        list_parser,
        help_text="Edge name to query (default: first edge)",
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

    # tunnel add
    add_parser = tunnel_sub.add_parser(
        "add",
        help="Add a tunnel",
        description="Add a new tunnel to edge nodes.",
    )
    add_client_argument(add_parser, required=True)
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
        "-T",
        "--target",
        help="Target address (host:port)",
    )
    add_edge_argument(
        add_parser,
        help_text="Edge name to add tunnel to (default: all edges)",
    )
    add_parser.add_argument(
        "-r",
        "--remark",
        help="Tunnel remark",
    )
    add_yes_argument(add_parser)
    add_parser.set_defaults(requires_config=True)

    # tunnel del
    tunnel_del_parser = tunnel_sub.add_parser(
        "del",
        help="Delete a tunnel",
        description=(
            "Delete a tunnel from edge node(s) via NPS API. "
            "Locate by --id (single edge), -r/--remark, or -p/--port + -t/--type."
        ),
    )
    tunnel_del_id_group = tunnel_del_parser.add_mutually_exclusive_group()
    tunnel_del_id_group.add_argument(
        "--id",
        type=int,
        help="Tunnel ID (edge-specific, requires -e)",
    )
    tunnel_del_id_group.add_argument(
        "-r",
        "--remark",
        help="Tunnel remark (can operate across all edges)",
    )
    tunnel_del_parser.add_argument(
        "-p",
        "--port",
        type=int,
        help="Server port (use with -t/--type to locate tunnel across edges)",
    )
    tunnel_del_parser.add_argument(
        "-t",
        "--type",
        choices=["tcp", "udp", "socks5", "httpProxy"],
        help="Tunnel type (use with -p/--port to locate tunnel across edges)",
    )
    add_edge_argument(
        tunnel_del_parser,
        help_text="Edge name (required for --id, optional for --remark/--port+--type)",
    )
    add_yes_argument(tunnel_del_parser)
    tunnel_del_parser.set_defaults(requires_config=True)

    # tunnel edit
    tunnel_edit_parser = tunnel_sub.add_parser(
        "edit",
        help="Edit a tunnel",
        description=(
            "Edit an existing tunnel on edge node(s). "
            "Locate by --id (single edge), -r/--remark, or -p/--port + -t/--type."
        ),
    )
    # -- Locator arguments (mutually exclusive) --
    tunnel_edit_id_group = tunnel_edit_parser.add_mutually_exclusive_group()
    tunnel_edit_id_group.add_argument(
        "--id",
        type=int,
        help="Tunnel ID to edit (edge-specific, requires -e)",
    )
    tunnel_edit_id_group.add_argument(
        "-r",
        "--remark",
        help="Tunnel remark to locate (can operate across all edges)",
    )
    tunnel_edit_parser.add_argument(
        "-p",
        "--port",
        type=int,
        help="Server port to locate (use with -t/--type across edges)",
    )
    tunnel_edit_parser.add_argument(
        "-t",
        "--type",
        choices=["tcp", "udp", "socks5", "httpProxy"],
        help="Tunnel type to locate (use with -p/--port across edges)",
    )
    add_edge_argument(
        tunnel_edit_parser,
        help_text="Edge name (required for --id, optional for --remark/--port+--type)",
    )
    # -- Value arguments (what to change) --
    tunnel_edit_parser.add_argument(
        "--new-target",
        help="New target address (host:port)",
    )
    tunnel_edit_parser.add_argument(
        "--new-port",
        type=int,
        help="New server port",
    )
    tunnel_edit_parser.add_argument(
        "--new-remark",
        help="New tunnel remark",
    )
    add_yes_argument(tunnel_edit_parser)
    tunnel_edit_parser.set_defaults(requires_config=True)

    # tunnel start
    tunnel_start_parser = tunnel_sub.add_parser(
        "start",
        help="Start a tunnel",
        description="Start a stopped tunnel on an edge node.",
    )
    tunnel_start_parser.add_argument(
        "--id",
        type=int,
        required=True,
        help="Tunnel ID to start",
    )
    add_edge_argument(tunnel_start_parser, required=True)
    tunnel_start_parser.set_defaults(requires_config=True)

    # tunnel stop
    tunnel_stop_parser = tunnel_sub.add_parser(
        "stop",
        help="Stop a tunnel",
        description="Stop a running tunnel on an edge node.",
    )
    tunnel_stop_parser.add_argument(
        "--id",
        type=int,
        required=True,
        help="Tunnel ID to stop",
    )
    add_edge_argument(tunnel_stop_parser, required=True)
    tunnel_stop_parser.set_defaults(requires_config=True)


def _add_host_commands(subparsers) -> None:
    """Add host subcommands.

    Args:
        subparsers: Parent subparsers object.
    """
    host_parser = subparsers.add_parser(
        "host",
        help="Host mapping management",
        description="Manage host mappings: list, add, edit, del.",
    )
    host_sub = host_parser.add_subparsers(dest="subcommand", help="Host action")

    # host list
    list_parser = host_sub.add_parser(
        "list",
        help="List host mappings",
        description="List all host mappings on edge nodes.",
    )
    add_edge_argument(
        list_parser,
        help_text="Edge name to query (default: first edge)",
    )
    list_parser.add_argument(
        "-a",
        "--all",
        action="store_true",
        help="Show host mappings from all edges",
    )
    list_parser.set_defaults(requires_config=True)

    # host add
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
    add_client_argument(add_parser, required=True)
    add_parser.add_argument(
        "-T",
        "--target",
        required=True,
        help="Target address (host:port)",
    )
    add_edge_argument(
        add_parser,
        help_text="Edge name to add host mapping to (default: all edges)",
    )
    add_parser.add_argument(
        "-r",
        "--remark",
        help="Host mapping remark",
    )
    add_yes_argument(add_parser)
    add_parser.set_defaults(requires_config=True)

    # host del
    host_del_parser = host_sub.add_parser(
        "del",
        help="Delete a host mapping",
        description=(
            "Delete a host mapping from edge node(s) via NPS API. "
            "Locate by --id (single edge), -d/--domain, or -r/--remark."
        ),
    )
    host_del_id_group = host_del_parser.add_mutually_exclusive_group(required=True)
    host_del_id_group.add_argument(
        "--id",
        type=int,
        help="Host ID (edge-specific, requires -e)",
    )
    host_del_id_group.add_argument(
        "-d",
        "--domain",
        help="Host domain name (can operate across all edges)",
    )
    host_del_id_group.add_argument(
        "-r",
        "--remark",
        help="Host remark (can operate across all edges)",
    )
    add_edge_argument(
        host_del_parser,
        help_text="Edge name (required for --id, optional for --domain/--remark)",
    )
    add_yes_argument(host_del_parser)
    host_del_parser.set_defaults(requires_config=True)

    # host edit
    host_edit_parser = host_sub.add_parser(
        "edit",
        help="Edit a host mapping",
        description=(
            "Edit an existing host mapping on edge node(s). "
            "Locate by --id (single edge), -d/--domain, or -r/--remark."
        ),
    )
    # -- Locator arguments (mutually exclusive) --
    host_edit_id_group = host_edit_parser.add_mutually_exclusive_group()
    host_edit_id_group.add_argument(
        "--id",
        type=int,
        help="Host ID to edit (edge-specific, requires -e)",
    )
    host_edit_id_group.add_argument(
        "-d",
        "--domain",
        help="Host domain to locate (can operate across all edges)",
    )
    host_edit_id_group.add_argument(
        "-r",
        "--remark",
        help="Host remark to locate (can operate across all edges)",
    )
    add_edge_argument(
        host_edit_parser,
        help_text="Edge name (required for --id, optional for --domain/--remark)",
    )
    # -- Value arguments (what to change) --
    host_edit_parser.add_argument(
        "--new-domain",
        help="New domain name",
    )
    host_edit_parser.add_argument(
        "--new-target",
        help="New target address (host:port)",
    )
    host_edit_parser.add_argument(
        "--new-remark",
        help="New host remark",
    )
    add_yes_argument(host_edit_parser)
    host_edit_parser.set_defaults(requires_config=True)


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

    # util generate-auth-key
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
