"""Argument parser definition for nps-ctl CLI.

This module defines all subcommands and their arguments.
"""

import argparse

from ..deploy import DEFAULT_NPS_VERSION
from .cmd_clients import cmd_clients
from .cmd_deploy import cmd_install, cmd_uninstall
from .cmd_hosts import cmd_add_host, cmd_hosts
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

    return parser
