"""CLI commands: sync, export - Sync and export configuration."""

import argparse
import json
import sys

from rich.console import Console

from .. import client_mgmt, host, tunnel
from ..cluster import NPSCluster
from ..exceptions import NPSError

console = Console()


def cmd_sync(args: argparse.Namespace) -> int:
    """Sync configuration from one edge to others."""
    proxy = getattr(args, "proxy", None)
    quiet = getattr(args, "quiet", False)

    try:
        cluster = NPSCluster(args.config, proxy=proxy)
    except FileNotFoundError as e:
        console.print(f"[red]Error: {e}[/red]", file=sys.stderr)
        return 1

    source = args.source
    if source not in cluster.edge_names:
        console.print(
            f"[red]Error: Source edge '{source}' not found[/red]", file=sys.stderr
        )
        return 1

    # Determine what to sync
    sync_clients = args.type in ("all", "clients")
    sync_tunnels = args.type in ("all", "tunnels")
    sync_hosts = args.type in ("all", "hosts")

    # Determine target edges
    if args.target:
        target_edges = args.target
        # Validate target edges
        invalid = [t for t in target_edges if t not in cluster.edge_names]
        if invalid:
            console.print(
                f"[red]Error: Unknown target edges: {', '.join(invalid)}[/red]",
                file=sys.stderr,
            )
            return 1
        if source in target_edges:
            target_edges = [t for t in target_edges if t != source]
    else:
        target_edges = [n for n in cluster.edge_names if n != source]

    if not target_edges:
        console.print("[red]Error: No target edges to sync to[/red]", file=sys.stderr)
        return 1

    # Get options
    parallel = getattr(args, "parallel", False)
    workers = getattr(args, "workers", 4)

    # Confirm
    if not args.yes:
        mode = "parallel" if parallel else "sequential"
        console.print(
            f"Will sync from [bold]{source}[/bold] to: {', '.join(target_edges)}"
        )
        console.print(
            f"Sync: clients={sync_clients}, tunnels={sync_tunnels}, hosts={sync_hosts}"
        )
        console.print(f"Mode: {mode}, workers: {workers}")
        response = input("Continue? [y/N] ")
        if response.lower() != "y":
            console.print("Aborted.")
            return 0

    try:
        results = cluster.sync_from(
            source,
            sync_clients=sync_clients,
            sync_tunnels=sync_tunnels,
            sync_hosts=sync_hosts,
            target_edges=target_edges,
            show_progress=not quiet,
            max_workers=workers,
            parallel=parallel,
            quiet=quiet,
        )

        # Print detailed results only if not quiet and not already printed
        if not quiet and not parallel:
            # Sequential mode already prints per-edge results
            # Just print the final item-level details
            _print_detailed_results(results)

    except NPSError as e:
        console.print(f"[red]Error: {e}[/red]", file=sys.stderr)
        return 1

    return 0


def _print_detailed_results(results: dict[str, dict[str, bool]]) -> None:
    """Print detailed sync results per edge."""
    for target, ops in results.items():
        console.print(f"\n[bold]{target}:[/bold]")
        for op, success in sorted(ops.items()):
            if op == "_edge_failed":
                continue
            status = "[green]✓[/green]" if success else "[red]✗[/red]"
            console.print(f"  {status} {op}")


def cmd_export(args: argparse.Namespace) -> int:
    """Export configuration from an edge."""
    proxy = getattr(args, "proxy", None)
    try:
        cluster = NPSCluster(args.config, proxy=proxy)
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    edge_name = args.edge
    if not edge_name:
        edge_name = cluster.edge_names[0] if cluster.edge_names else None
        if not edge_name:
            print("Error: No edges configured", file=sys.stderr)
            return 1

    nps = cluster.get_client(edge_name)
    if not nps:
        print(f"Error: Edge '{edge_name}' not found", file=sys.stderr)
        return 1

    try:
        data = {
            "edge": edge_name,
            "clients": client_mgmt.list_clients(nps),
            "tunnels": tunnel.list_tunnels(nps),
            "hosts": host.list_hosts(nps),
        }

        output = args.output
        if output:
            with open(output, "w") as f:
                json.dump(data, f, indent=2)
            print(f"Exported to {output}")
        else:
            print(json.dumps(data, indent=2))

    except NPSError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    return 0
