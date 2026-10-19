"""CLI commands: edge primary, edge add - Edit edges.toml."""

from __future__ import annotations

import argparse
import getpass
import os
from urllib.parse import urlsplit

from ..cluster import NPSCluster
from ..config_edit import append_edge, set_primary
from .helpers import console, print_error, print_json, print_success


def cmd_edge_primary(args: argparse.Namespace) -> int:
    """Show or set the primary edge in edges.toml.

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

    name = getattr(args, "name", None)
    if not name:
        configured = cluster.configured_primary
        if getattr(args, "json", False):
            print_json(
                {"primary": configured or None, "valid": bool(cluster.primary_edge)}
            )
            return 1 if configured and not cluster.primary_edge else 0
        if not configured:
            console.print("No primary edge set.")
        elif cluster.primary_edge:
            console.print(f"Primary edge: [bold]{configured}[/bold]")
        else:
            print_error(f"Primary edge '{configured}' is not a configured edge")
            return 1
        return 0

    if name not in cluster.edge_names:
        print_error(
            f"Edge '{name}' not found. Configured edges: "
            f"{', '.join(cluster.edge_names)}"
        )
        return 1

    try:
        set_primary(args.config, name)
    except ValueError as e:
        print_error(str(e))
        return 1
    print_success(f"Primary edge set to {name}")
    return 0


def cmd_edge_add(args: argparse.Namespace) -> int:
    """Append a new edge entry to edges.toml.

    The auth key is read from ``NPS_EDGE_AUTH_KEY`` or prompted for, so it
    never appears in shell history or the process list.

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

    name = args.name
    if name in cluster.edge_names:
        print_error(f"Edge '{name}' already exists")
        return 1

    api_url = args.api_url.rstrip("/")
    parts = urlsplit(api_url)
    if parts.scheme not in ("http", "https") or not parts.netloc:
        print_error("--api-url must be an http(s) URL, e.g. https://nps-x.example.com")
        return 2

    auth_key = os.environ.get("NPS_EDGE_AUTH_KEY", "")
    if not auth_key and not getattr(args, "no_auth_key", False):
        try:
            auth_key = getpass.getpass(f"API auth key for {name} (empty for none): ")
        except EOFError:
            print_error(
                "No TTY for the auth key prompt; set NPS_EDGE_AUTH_KEY "
                "or pass --no-auth-key"
            )
            return 2

    console.print("[bold]New edge entry:[/bold]")
    console.print(f"  Name:     {name}")
    console.print(f"  API URL:  {api_url}")
    console.print(f"  Region:   {args.region or '—'}")
    console.print(f"  SSH host: {args.ssh_host or '—'}")
    console.print(f"  Auth key: {'set' if auth_key else 'none'}")
    if not args.yes:
        try:
            response = input("Add this edge to edges.toml? [y/N] ")
        except EOFError:
            print_error(
                "No TTY for the confirmation prompt; pass -y to add without asking"
            )
            return 2
        if response.strip().lower() != "y":
            console.print("Aborted.")
            return 0

    try:
        append_edge(
            args.config,
            name=name,
            api_url=api_url,
            auth_key=auth_key,
            region=args.region or "",
            ssh_host=args.ssh_host or "",
        )
    except ValueError as e:
        print_error(str(e))
        return 1

    print_success(f"Added edge {name}")
    source = cluster.primary_edge
    hint = f"nps-ctl edge sync --to {name}"
    if not source:
        hint += " --from <source-edge>"
    console.print(f"[dim]To copy clients/tunnels/hosts onto it: {hint}[/dim]")
    return 0
