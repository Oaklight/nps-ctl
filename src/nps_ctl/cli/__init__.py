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
    cmd_utils: Utility commands (auth key generation)
"""

import sys

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


def main() -> int:
    """Main entry point."""
    parser = create_parser()
    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        return 0

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
        # npc-list uses a different dispatch pattern (needs cluster)
        if args.command == "npc-list":
            from ..cluster import NPSCluster

            from .cmd_npc import handle_npc_list

            cluster = NPSCluster(args.config)
            handle_npc_list(args, cluster)
            return 0
        return args.func(args)
    finally:
        # Clean up SSH proxy if we created one
        if ssh_proxy:
            ssh_proxy.stop()


if __name__ == "__main__":
    sys.exit(main())
