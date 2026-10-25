"""Command-line argument parser for nps-ctl.

Defines the CLI structure with nested subcommands organized by resource type:
client, edge, tunnel, host, and util.
"""

import argparse

from .. import __version__
from .helpers import (
    add_all_argument,
    add_client_argument,
    add_edge_argument,
    add_output_arguments,
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
        "--json",
        action="store_true",
        help="Emit machine-readable JSON instead of tables",
    )
    parser.add_argument(
        "--no-color",
        action="store_true",
        help="Disable colored output",
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

    # ========== check commands ==========
    _add_check_commands(subparsers)

    # ========== util commands ==========
    _add_util_commands(subparsers)

    # ========== web dashboard ==========
    _add_web_command(subparsers)

    return parser


STRESS_PROFILES = ("smoke", "ladder", "slow", "churn", "soak")


def _add_session_arguments(parser: argparse.ArgumentParser) -> None:
    """Add the arguments shared by the checks that open a probe session.

    Args:
        parser: The leaf parser to add the arguments to.
    """
    add_edge_argument(parser, required=True, help_text="Edge whose tunnel to test")
    add_client_argument(
        parser, required=True, help_text="NPC client name from clients.toml"
    )
    parser.add_argument(
        "--http-proxy-port",
        type=int,
        default=None,
        help="NPS HTTP proxy port on the edge (default: read from nps.conf, else 30080)",
    )
    parser.add_argument(
        "--fail-on",
        choices=["warn", "error"],
        default="error",
        help="Lowest finding level that makes the exit code 1 (default: error)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be created and exit without touching anything",
    )
    add_yes_argument(parser)
    add_output_arguments(parser)
    parser.set_defaults(requires_config=True)


def _add_check_commands(subparsers) -> None:
    """Add the ``check`` command group.

    Args:
        subparsers: Parent subparsers object.
    """
    check_parser = subparsers.add_parser(
        "check",
        help="Health and integrity checks for NPS/NPC deployments",
        description=(
            "Check NPS/NPC deployments. 'links' only reads sockets and logs. "
            "'probe' and 'stress' push self-verifying traffic through a tunnel and "
            "temporarily add a host mapping on one edge, which they remove again."
        ),
    )
    check_sub = check_parser.add_subparsers(dest="subcommand", help="Check action")

    # check links
    links_parser = check_sub.add_parser(
        "links",
        help="Report bridge-link health from NPC sockets and logs",
        description=(
            "For each NPC client, read its established bridge sockets and the "
            "tail of its log over SSH, then report outages per edge: how often "
            "the link dropped, for how long, and whether the drops recur at a "
            "fixed interval. Generates no tunnel traffic."
        ),
    )
    add_client_argument(
        links_parser, help_text="Client name from clients.toml (default: all)"
    )
    links_parser.add_argument(
        "--since",
        default="6h",
        help="Window to examine, e.g. 90m, 6h, 2d (default: 6h)",
    )
    links_parser.add_argument(
        "--log-path",
        default="/var/log/npc.log",
        help="NPC log path on the client hosts (default: /var/log/npc.log)",
    )
    links_parser.add_argument(
        "--tail-bytes",
        type=int,
        default=4 * 1024 * 1024,
        help="How much of each log's end to read (default: 4 MiB)",
    )
    links_parser.add_argument(
        "--fail-on",
        choices=["warn", "error"],
        default="warn",
        help="Lowest finding level that makes the exit code 1 (default: warn)",
    )
    add_output_arguments(links_parser)
    links_parser.set_defaults(requires_config=True)

    # check probe
    probe_parser = check_sub.add_parser(
        "probe",
        help="Send self-verifying requests through an edge's tunnel",
        description=(
            "Start a temporary hash-echo service on an NPC client, map a throwaway "
            "domain to it on one NPS edge, and send request bodies that differ from "
            "request to request through NPS. Each answer is compared with what was "
            "sent, so truncation, damage and bytes from another request are "
            "detected. A client-local run without the tunnel is the baseline. The "
            "mapping and the echo service are removed afterwards."
        ),
    )
    _add_session_arguments(probe_parser)
    probe_parser.add_argument(
        "--size", default="256K", help="Body size, e.g. 64K, 1M (default: 256K)"
    )
    probe_parser.add_argument(
        "--count", type=int, default=30, help="Requests (default: 30)"
    )
    probe_parser.add_argument(
        "--concurrency", type=int, default=4, help="Parallel requests (default: 4)"
    )
    probe_parser.add_argument(
        "--mode",
        choices=["normal", "slow"],
        default="normal",
        help="slow sends the body in small chunks with gaps (default: normal)",
    )
    probe_parser.add_argument(
        "--chunk-kb",
        type=float,
        default=16.0,
        help="Chunk size for slow mode (default: 16)",
    )
    probe_parser.add_argument(
        "--gap-ms",
        type=float,
        default=20.0,
        help="Gap between chunks for slow mode (default: 20)",
    )
    probe_parser.add_argument(
        "--timeout",
        type=float,
        default=30.0,
        help="Per-request timeout in seconds (default: 30)",
    )

    # check stress
    stress_parser = check_sub.add_parser(
        "stress",
        help="Run a named stress profile through an edge's tunnel",
        description=(
            "Like 'probe', but runs a profile of load steps: smoke (quick sanity), "
            "ladder (concurrency x body size), slow (slow uploaders), churn (many "
            "small connections) or soak (steady load for --duration). Failures are "
            "matched against the link outages in the client's NPC log."
        ),
    )
    _add_session_arguments(stress_parser)
    stress_parser.add_argument(
        "--profile",
        choices=sorted(STRESS_PROFILES),
        default="smoke",
        help="Load profile (default: smoke)",
    )
    stress_parser.add_argument(
        "--duration",
        default="10m",
        help="Soak length, e.g. 30m, 2h (default: 10m; only used by soak)",
    )


def _add_web_command(subparsers) -> None:
    """Add the top-level web dashboard command.

    Args:
        subparsers: Parent subparsers object.
    """
    web_parser = subparsers.add_parser(
        "web",
        help="Run the cluster dashboard (read-only unless --allow-writes)",
        description=(
            "Serve a web dashboard for all configured edges (read-only unless "
            "--allow-writes). "
            "Binds to loopback by default; set --username/--password before "
            "exposing it."
        ),
    )
    web_parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Bind address (default: 127.0.0.1)",
    )
    web_parser.add_argument(
        "--port",
        type=int,
        default=8080,
        help="Bind port (default: 8080; 0 chooses an ephemeral port)",
    )
    web_parser.add_argument(
        "--username",
        help="HTTP Basic Auth username",
    )
    web_parser.add_argument(
        "--password",
        help="HTTP Basic Auth password (or set NPS_WEB_PASSWORD)",
    )
    web_parser.add_argument(
        "--users-file",
        help=(
            "TOML file with [[users]] name/password_hash/role entries; "
            "roles are 'operator' (writes) or 'viewer' (read-only)"
        ),
    )
    web_parser.add_argument(
        "--insecure",
        action="store_true",
        help="Allow a non-loopback bind without authentication",
    )
    web_parser.add_argument(
        "--allow-writes",
        action="store_true",
        help=(
            "Enable add/sync actions in the dashboard "
            "(requires auth on non-loopback binds)"
        ),
    )
    web_parser.set_defaults(requires_config=True, leaf_command=True)


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
        help_text=("Edge name to query (default: all edges; required for --update)"),
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
    add_output_arguments(list_parser)
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
    add_parser.add_argument(
        "--push",
        action="store_true",
        help="Also create the client on its edges via the NPS API",
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
        help_text=("Edge name (required with --id; otherwise use this or -a/--all)"),
    )
    add_all_argument(
        del_parser,
        help_text="Delete the named client from every configured edge",
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

    # edge list
    edge_list_parser = edge_sub.add_parser(
        "list",
        help="List configured edges (offline)",
        description=(
            "List every edge configured in edges.toml without contacting it. "
            "Use this to discover the full edge set."
        ),
    )
    add_output_arguments(edge_list_parser)
    edge_list_parser.set_defaults(requires_config=True)

    # edge status
    status_parser = edge_sub.add_parser(
        "status",
        help="Show edge status and resource inventory",
        description=(
            "Display reachability, client liveness, host/tunnel counts, and "
            "port inventories for all or selected NPS edge nodes."
        ),
    )
    add_edge_argument(
        status_parser,
        help_text="Edge name to query (default: all edges)",
    )
    add_all_argument(
        status_parser,
        help_text="Show status for every configured edge",
    )
    add_output_arguments(status_parser)
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
        dest="source",
        help=(
            "Source edge name to sync from "
            "(default: the primary edge set in edges.toml)"
        ),
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
        "--prune",
        action="store_true",
        help=(
            "Delete resources on target edges that are absent from the source "
            "(requires confirmation; aborts if source data cannot be read)"
        ),
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

    # edge primary
    primary_parser = edge_sub.add_parser(
        "primary",
        help="Show or set the primary edge",
        description=(
            "Show the primary edge, or set it in edges.toml. The primary is "
            "the default source for 'edge sync'."
        ),
    )
    primary_parser.add_argument(
        "name",
        nargs="?",
        help="Edge to mark as primary (omit to show the current primary)",
    )
    add_output_arguments(primary_parser)
    primary_parser.set_defaults(requires_config=True)

    # edge add
    edge_add_parser = edge_sub.add_parser(
        "add",
        help="Add an edge entry to edges.toml",
        description=(
            "Append a new edge to edges.toml. The API auth key is read from "
            "NPS_EDGE_AUTH_KEY or prompted for; it is never taken on the "
            "command line."
        ),
    )
    edge_add_parser.add_argument("name", help="New edge name")
    edge_add_parser.add_argument(
        "--api-url", required=True, help="Edge API URL (https://...)"
    )
    edge_add_parser.add_argument("--region", help="Display region")
    edge_add_parser.add_argument("--ssh-host", help="SSH host alias")
    edge_add_parser.add_argument(
        "--no-auth-key",
        action="store_true",
        help="Do not prompt for an auth key (modern-auth or unauthenticated edges)",
    )
    add_yes_argument(edge_add_parser)
    edge_add_parser.set_defaults(requires_config=True)

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
        description="Manage tunnels: list, status, add, edit, del, start, stop.",
    )
    tunnel_sub = tunnel_parser.add_subparsers(dest="subcommand", help="Tunnel action")

    # tunnel status
    status_parser = tunnel_sub.add_parser(
        "status",
        help="Show client liveness and tunnel inventory per edge",
        description=(
            "Show per-edge reachability, online/total clients, tunnel counts, "
            "running state, and distinct server ports."
        ),
    )
    add_edge_argument(
        status_parser,
        help_text="Edge name to query (default: all edges)",
    )
    add_all_argument(
        status_parser,
        help_text="Show status for every configured edge",
    )
    add_output_arguments(status_parser)
    status_parser.set_defaults(requires_config=True)

    # tunnel list
    list_parser = tunnel_sub.add_parser(
        "list",
        help="List tunnels",
        description="List all tunnels on edge nodes.",
    )
    add_edge_argument(
        list_parser,
        help_text="Edge name to query (default: all edges)",
    )
    list_parser.add_argument(
        "-t",
        "--type",
        choices=[
            "tcp",
            "udp",
            "socks5",
            "httpProxy",
            "mixProxy",
            "secret",
            "p2p",
            "file",
        ],
        help="Filter by tunnel type",
    )
    list_parser.add_argument(
        "-a",
        "--all",
        action="store_true",
        help="Show tunnels from all edges",
    )
    add_output_arguments(list_parser)
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
        help_text="Edge name to add tunnel to (or use -a/--all)",
    )
    add_all_argument(
        add_parser,
        help_text="Add the tunnel to every configured edge",
    )
    add_parser.add_argument(
        "-r",
        "--remark",
        help="Tunnel remark",
    )
    add_parser.add_argument(
        "--auth",
        help=(
            "HTTP Basic Auth credentials "
            '(e.g. "user=pass" or "user1=pass1,user2=pass2"; '
            "use newlines if a password contains a comma)"
        ),
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
        choices=["tcp", "udp", "socks5", "httpProxy", "mixProxy"],
        help="Tunnel type (use with -p/--port to locate tunnel across edges)",
    )
    add_edge_argument(
        tunnel_del_parser,
        help_text="Edge name (required with --id; otherwise use this or -a/--all)",
    )
    add_all_argument(
        tunnel_del_parser,
        help_text="Delete the matching tunnel from every configured edge",
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
        choices=["tcp", "udp", "socks5", "httpProxy", "mixProxy"],
        help="Tunnel type to locate (use with -p/--port across edges)",
    )
    add_edge_argument(
        tunnel_edit_parser,
        help_text="Edge name (required with --id; otherwise use this or -a/--all)",
    )
    add_all_argument(
        tunnel_edit_parser,
        help_text="Edit the matching tunnel on every configured edge",
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
    tunnel_edit_parser.add_argument(
        "--auth",
        help=('Set HTTP Basic Auth credentials (e.g. "user=pass"; pass "" to clear)'),
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
        description="Manage host mappings: list, status, add, edit, del.",
    )
    host_sub = host_parser.add_subparsers(dest="subcommand", help="Host action")

    # host status
    status_parser = host_sub.add_parser(
        "status",
        help="Show client liveness and host inventory per edge",
        description=(
            "Show per-edge reachability, online/total clients, host mappings, "
            "and distinct target ports."
        ),
    )
    add_edge_argument(
        status_parser,
        help_text="Edge name to query (default: all edges)",
    )
    add_all_argument(
        status_parser,
        help_text="Query every configured edge",
    )
    add_output_arguments(status_parser)
    status_parser.set_defaults(requires_config=True)

    # host list
    list_parser = host_sub.add_parser(
        "list",
        help="List host mappings",
        description="List all host mappings on edge nodes.",
    )
    add_edge_argument(
        list_parser,
        help_text="Edge name to query (default: all edges)",
    )
    list_parser.add_argument(
        "-a",
        "--all",
        action="store_true",
        help="Show host mappings from all edges",
    )
    list_parser.add_argument(
        "--matrix",
        action="store_true",
        help="Show a domain-by-edge presence matrix",
    )
    add_output_arguments(list_parser)
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
        help_text="Edge name to add host mapping to (or use -a/--all)",
    )
    add_all_argument(
        add_parser,
        help_text="Add the host mapping to every configured edge",
    )
    add_parser.add_argument(
        "-r",
        "--remark",
        help="Host mapping remark",
    )
    add_parser.add_argument(
        "--auth",
        help=(
            'HTTP Basic Auth (format: "user=pass" or "user1=pass1,user2=pass2"; '
            "use newlines if a password contains a comma)"
        ),
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
        help_text="Edge name (required with --id; otherwise use this or -a/--all)",
    )
    add_all_argument(
        host_del_parser,
        help_text="Delete the matching host mapping from every configured edge",
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
        help_text="Edge name (required with --id; otherwise use this or -a/--all)",
    )
    add_all_argument(
        host_edit_parser,
        help_text="Edit the matching host mapping on every configured edge",
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
    host_edit_parser.add_argument(
        "--auth",
        help='HTTP Basic Auth (format: "user=pass" or "user1=pass1,user2=pass2", empty string to clear)',
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

    # util hash-password
    hash_parser = util_sub.add_parser(
        "hash-password",
        help="Hash a dashboard password for a users file",
        description=(
            "Prompt for a password (or read NPS_WEB_PASSWORD) and print a "
            "PBKDF2 hash for use in nps-ctl web --users-file. The password "
            "itself is never printed."
        ),
    )
    hash_parser.add_argument(
        "--iterations",
        type=int,
        default=None,
        help="PBKDF2 iteration count (default: 260000)",
    )
    hash_parser.set_defaults(requires_config=False)
