"""CLI command: web - run the read-only cluster dashboard."""

from __future__ import annotations

import argparse
import getpass
import os

from ..cluster import NPSCluster
from ..web import create_server
from .helpers import console, print_error


def cmd_web(args: argparse.Namespace) -> int:
    """Run the web dashboard (read-only unless --allow-writes).

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
    if password and not username:
        print_error("Password provided without --username")
        return 2
    if username and not password:
        try:
            password = getpass.getpass(f"Password for {username}: ")
        except EOFError:
            print_error(
                "No password provided and no TTY available; "
                "set NPS_WEB_PASSWORD or pass --password"
            )
            return 2
        if not password:
            print_error("Password cannot be empty")
            return 2

    try:
        server = create_server(
            cluster,
            host=args.host,
            port=args.port,
            username=username,
            password=password,
            allow_insecure=getattr(args, "insecure", False),
            allow_writes=getattr(args, "allow_writes", False),
        )
    except ValueError as e:
        print_error(str(e))
        return 2

    host = str(server.server_address[0])
    port = server.server_address[1]
    display_host = f"[{host}]" if ":" in host else host
    console.print(f"Dashboard: [bold]http://{display_host}:{port}/[/bold]")
    if not username:
        if host in {"127.0.0.1", "::1", "localhost"}:
            console.print("[yellow]Authentication disabled (loopback only).[/yellow]")
        else:
            console.print(
                "[bold red]Authentication disabled; the dashboard is "
                "reachable on the network.[/bold red]"
            )
    if server.allow_writes:
        console.print(
            "[bold yellow]Writes enabled: the dashboard can add clients, "
            "tunnels, hosts and sync edges.[/bold yellow]"
        )
    else:
        console.print("[dim]Read-only (pass --allow-writes to enable actions).[/dim]")
    console.print("[dim]Press Ctrl+C to stop.[/dim]")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        console.print("\nStopping dashboard.")
    finally:
        server.server_close()
    return 0
