"""CLI command: web - run the read-only cluster dashboard."""

from __future__ import annotations

import argparse
import getpass
import os

from ..cluster import NPSCluster
from ..web import create_server
from .helpers import console, print_error


def cmd_web(args: argparse.Namespace) -> int:
    """Run the read-only web dashboard.

    Args:
        args: Parsed command line arguments.

    Returns:
        Exit code.
    """
    try:
        cluster = NPSCluster(args.config)
    except FileNotFoundError as e:
        print_error(str(e))
        return 1

    username = getattr(args, "username", "") or ""
    password = getattr(args, "password", "") or os.environ.get("NPS_WEB_PASSWORD", "")
    if username and not password:
        password = getpass.getpass(f"Password for {username}: ")

    try:
        server = create_server(
            cluster,
            host=args.host,
            port=args.port,
            username=username,
            password=password,
            allow_insecure=getattr(args, "insecure", False),
        )
    except ValueError as e:
        print_error(str(e))
        return 2

    host = str(server.server_address[0])
    port = server.server_address[1]
    display_host = f"[{host}]" if ":" in host else host
    console.print(f"Dashboard: [bold]http://{display_host}:{port}/[/bold]")
    if not username:
        console.print("[yellow]Authentication disabled (loopback only).[/yellow]")
    console.print("[dim]Press Ctrl+C to stop.[/dim]")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        console.print("\nStopping dashboard.")
    finally:
        server.server_close()
    return 0
