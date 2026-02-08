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

from ..logging import configure_logging
from .helpers import get_default_config_path
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

    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
