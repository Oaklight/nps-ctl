"""Command-line interface for NPS management.

This package provides the `nps-ctl` command for managing NPS servers.

Submodules:
    parser: Argument parser definition
    helpers: Shared helper utilities (table formatting, config path)
    cmd_status: Status command
    cmd_clients: Client management commands
    cmd_tunnels: Tunnel management commands
    cmd_hosts: Host management commands
    cmd_sync: Sync and export commands
    cmd_deploy: Install and uninstall commands
    cmd_npc: NPC deployment commands
    cmd_utils: Utility commands (auth key generation)
"""

import sys
from collections.abc import Callable

from ..logging import configure_logging, flush_output
from ..ssh_proxy import SSHProxy
from .helpers import console, get_default_config_path
from .parser import create_parser


def setup_logging(verbose: bool = False, debug: bool = False) -> None:
    """Configure logging based on verbosity level.

    Log levels:
        - Default (no flags): NOTICE - shows key phase information
        - -v/--verbose: INFO - shows all request/response details
        - --debug: DEBUG - shows everything including internal details

    Args:
        verbose: Enable INFO level logging.
        debug: Enable DEBUG level logging (overrides verbose).
    """
    if debug:
        level = "DEBUG"
    elif verbose:
        level = "INFO"
    else:
        level = "NOTICE"  # Custom level (25) - shows key phases only

    configure_logging(level=level, use_colors=True)


def _dispatch_client_list(args) -> int:
    """Dispatch client list command with special handling.

    If --update or --dry-run is specified, fetches client info from NPS API
    and updates clients.toml. Otherwise, displays the API client list.

    Args:
        args: Parsed command line arguments.

    Returns:
        Exit code.
    """
    update = getattr(args, "update", False)
    dry_run = getattr(args, "dry_run", False)

    if update or dry_run:
        from ..cluster import NPSCluster

        from .cmd_npc import handle_npc_list

        cluster = NPSCluster(args.config)
        handle_npc_list(args, cluster)
        return 0
    else:
        from .cmd_clients import cmd_clients

        return cmd_clients(args)


def _dispatch_client_push(args) -> int:
    """Dispatch client push command.

    Args:
        args: Parsed command line arguments.

    Returns:
        Exit code.
    """
    from ..cluster import NPSCluster
    from .cmd_npc import handle_client_push

    cluster = NPSCluster(args.config)
    handle_client_push(args, cluster)
    return 0


def main() -> int:
    """Main entry point for nps-ctl CLI."""
    parser = create_parser()
    args = parser.parse_args()

    # No command specified -> print top-level help
    if args.command is None:
        parser.print_help()
        return 0

    # Command specified but no subcommand -> print command group help
    subcommand = getattr(args, "subcommand", None)
    if subcommand is None:
        # Re-parse to get the subparser and print its help
        parser.parse_args([args.command, "--help"])
        return 0  # pragma: no cover (--help exits)

    # Setup logging
    verbose = getattr(args, "verbose", False)
    debug = getattr(args, "debug", False)
    setup_logging(verbose=verbose, debug=debug)

    # Check if this command requires config
    requires_config = getattr(args, "requires_config", True)

    # Find config file if not specified and required
    if requires_config and args.config is None:
        try:
            args.config = get_default_config_path()
        except FileNotFoundError as e:
            print(f"Error: {e}", file=sys.stderr)
            return 1

    # Handle --auto-proxy option
    auto_proxy = getattr(args, "auto_proxy", None)
    ssh_proxy: SSHProxy | None = None

    if auto_proxy:
        # Create and start SSH SOCKS proxy
        try:
            console.print(f"[blue]Creating SSH SOCKS proxy via {auto_proxy}...[/blue]")
            flush_output()
            ssh_proxy = SSHProxy(ssh_host=auto_proxy)
            ssh_proxy.start()
            # Set socks_proxy for the command to use
            args.socks_proxy = ssh_proxy.address
            console.print(f"[green]✓ SSH proxy ready on {ssh_proxy.address}[/green]")
            flush_output()
        except Exception as e:
            console.print(f"[red]Failed to create SSH proxy: {e}[/red]")
            flush_output()
            return 1

    try:
        return _dispatch(args)
    finally:
        # Clean up SSH proxy if we created one
        if ssh_proxy:
            ssh_proxy.stop()


def _dispatch(args) -> int:
    """Dispatch to the appropriate handler based on (command, subcommand).

    Args:
        args: Parsed command line arguments with command and subcommand set.

    Returns:
        Exit code.
    """
    from .cmd_deploy import cmd_install, cmd_reconfig, cmd_uninstall, cmd_upgrade
    from .cmd_clients import cmd_client_del
    from .cmd_hosts import cmd_add_host, cmd_host_del, cmd_host_edit, cmd_hosts
    from .cmd_npc import (
        cmd_client_add,
        cmd_npc_install,
        cmd_npc_reconfig,
        cmd_npc_restart,
        cmd_npc_status,
        cmd_npc_uninstall,
        cmd_npc_upgrade,
    )
    from .cmd_status import cmd_status
    from .cmd_sync import cmd_export, cmd_sync
    from .cmd_tunnels import (
        cmd_add_tunnel,
        cmd_tunnel_del,
        cmd_tunnel_edit,
        cmd_tunnel_start,
        cmd_tunnel_stop,
        cmd_tunnels,
    )
    from .cmd_utils import cmd_generate_auth_key

    # Command dispatch table: (command, subcommand) -> handler
    dispatch_table: dict[tuple[str, str], Callable[..., int]] = {
        # client commands
        ("client", "list"): _dispatch_client_list,
        ("client", "add"): cmd_client_add,
        ("client", "push"): _dispatch_client_push,
        ("client", "del"): cmd_client_del,
        ("client", "install"): cmd_npc_install,
        ("client", "upgrade"): cmd_npc_upgrade,
        ("client", "reconfig"): cmd_npc_reconfig,
        ("client", "uninstall"): cmd_npc_uninstall,
        ("client", "status"): cmd_npc_status,
        ("client", "restart"): cmd_npc_restart,
        # edge commands
        ("edge", "status"): cmd_status,
        ("edge", "install"): cmd_install,
        ("edge", "upgrade"): cmd_upgrade,
        ("edge", "reconfig"): cmd_reconfig,
        ("edge", "uninstall"): cmd_uninstall,
        ("edge", "sync"): cmd_sync,
        ("edge", "export"): cmd_export,
        # tunnel commands
        ("tunnel", "list"): cmd_tunnels,
        ("tunnel", "add"): cmd_add_tunnel,
        ("tunnel", "del"): cmd_tunnel_del,
        ("tunnel", "edit"): cmd_tunnel_edit,
        ("tunnel", "start"): cmd_tunnel_start,
        ("tunnel", "stop"): cmd_tunnel_stop,
        # host commands
        ("host", "list"): cmd_hosts,
        ("host", "add"): cmd_add_host,
        ("host", "del"): cmd_host_del,
        ("host", "edit"): cmd_host_edit,
        # util commands
        ("util", "generate-auth-key"): cmd_generate_auth_key,
    }

    key = (args.command, args.subcommand)
    handler = dispatch_table.get(key)

    if handler is None:
        print(
            f"Error: Unknown command '{args.command} {args.subcommand}'",
            file=sys.stderr,
        )
        return 1

    return handler(args)


if __name__ == "__main__":
    sys.exit(main())
