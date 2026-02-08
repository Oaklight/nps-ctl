"""Argument parser definition for nps-ctl CLI.

This module defines all subcommands and their arguments.
"""

import argparse

from ..deploy import DEFAULT_NPC_VERSION, DEFAULT_NPS_VERSION
from .cmd_clients import cmd_clients
from .cmd_deploy import cmd_install, cmd_uninstall
from .cmd_hosts import cmd_add_host, cmd_hosts
from .cmd_npc import cmd_npc_install, cmd_npc_restart, cmd_npc_status, cmd_npc_uninstall
from .cmd_status import cmd_status
from .cmd_sync import cmd_export, cmd_sync
from .cmd_tunnels import cmd_add_tunnel, cmd_tunnels
from .cmd_utils import cmd_generate_auth_key


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
    parser.add_argument(
        "--proxy",
        default=None,
        help="HTTP/HTTPS proxy URL (e.g., http://127.0.0.1:7890)",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable verbose output (INFO level logging)",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug output (DEBUG level logging)",
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
        "--type",
        "-t",
        choices=["tcp", "udp", "socks5", "httpProxy", "secret", "p2p", "file"],
        default="",
        help="Filter by tunnel type (default: show all types)",
    )
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
        "--to",
        "--edge",
        "-e",
        dest="target",
        nargs="+",
        help="Target edge names (default: all other edges)",
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
    sync_parser.add_argument(
        "--parallel",
        action="store_true",
        help="Sync to all edges in parallel (default: sequential)",
    )
    sync_parser.add_argument(
        "--quiet",
        "-q",
        action="store_true",
        help="Only show final summary",
    )
    sync_parser.add_argument(
        "--workers",
        "-w",
        type=int,
        default=1,
        help="Number of parallel workers for items within each edge (default: 1)",
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
    install_parser.add_argument(
        "--version", help=f"NPS version to install (default: {DEFAULT_NPS_VERSION})"
    )
    install_parser.add_argument(
        "--release-url", help="Custom NPS release URL (overrides mirrors)"
    )
    install_parser.add_argument(
        "--force-reinstall",
        action="store_true",
        help="Uninstall existing NPS before installing (clean reinstall)",
    )
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

    # generate-auth-key command (standalone, no config required)
    gen_key_parser = subparsers.add_parser(
        "generate-auth-key", help="Generate a random auth key"
    )
    gen_key_parser.add_argument(
        "length",
        type=int,
        nargs="?",
        default=43,
        help="Length of the auth key (default: 43, matching NPS default)",
    )
    gen_key_parser.set_defaults(func=cmd_generate_auth_key, requires_config=False)

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

    # ========== NPC Commands ==========

    # npc-install command
    npc_install_parser = subparsers.add_parser(
        "npc-install", help="Install NPC on client machines via SSH"
    )
    npc_install_parser.add_argument(
        "--client", "-c", help="Client name (all clients if not specified)"
    )
    npc_install_parser.add_argument(
        "--version",
        help=f"NPC version to install (default: {DEFAULT_NPC_VERSION})",
    )
    npc_install_parser.add_argument(
        "--release-url", help="Custom NPC release URL (overrides mirrors)"
    )
    npc_install_parser.add_argument(
        "--force-reinstall",
        action="store_true",
        help="Uninstall existing NPC before installing (clean reinstall)",
    )
    npc_install_parser.add_argument(
        "--yes", "-y", action="store_true", help="Skip confirmation"
    )
    npc_install_parser.add_argument(
        "--verbose", "-v", action="store_true", help="Show detailed output"
    )
    npc_install_parser.set_defaults(func=cmd_npc_install)

    # npc-uninstall command
    npc_uninstall_parser = subparsers.add_parser(
        "npc-uninstall", help="Uninstall NPC from client machines via SSH"
    )
    npc_uninstall_parser.add_argument(
        "--client", "-c", help="Client name (all clients if not specified)"
    )
    npc_uninstall_parser.add_argument(
        "--yes", "-y", action="store_true", help="Skip confirmation"
    )
    npc_uninstall_parser.add_argument(
        "--verbose", "-v", action="store_true", help="Show detailed output"
    )
    npc_uninstall_parser.set_defaults(func=cmd_npc_uninstall)

    # npc-status command
    npc_status_parser = subparsers.add_parser(
        "npc-status", help="Check NPC status on client machines"
    )
    npc_status_parser.add_argument(
        "--client", "-c", help="Client name (all clients if not specified)"
    )
    npc_status_parser.set_defaults(func=cmd_npc_status)

    # npc-restart command
    npc_restart_parser = subparsers.add_parser(
        "npc-restart", help="Restart NPC service on client machines"
    )
    npc_restart_parser.add_argument(
        "--client", "-c", help="Client name (all clients if not specified)"
    )
    npc_restart_parser.add_argument(
        "--verbose", "-v", action="store_true", help="Show detailed output"
    )
    npc_restart_parser.set_defaults(func=cmd_npc_restart)

    return parser
