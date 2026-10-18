"""CLI command: status - Show status of all edge nodes."""

import argparse
from contextlib import nullcontext
from typing import TypedDict

from rich.live import Live
from rich.spinner import Spinner

from .. import client_mgmt
from ..cluster import NPSCluster
from ..exceptions import NPSError
from .helpers import console, create_table, print_error, print_json


class _StatusRow(TypedDict):
    """One edge status result."""

    edge: str
    region: str
    api_url: str
    online: bool


def cmd_edge_list(args: argparse.Namespace) -> int:
    """List configured edges without contacting them."""
    json_mode = getattr(args, "json", False)
    try:
        cluster = NPSCluster(args.config)
    except FileNotFoundError as e:
        if json_mode:
            print_json({"error": str(e)})
        else:
            print_error(str(e))
        return 1

    edges = []
    for name in cluster.edge_names:
        edge = cluster.get_edge(name)
        if not edge:
            continue
        edges.append(
            {
                "edge": name,
                "region": edge.region,
                "api_url": edge.api_url,
                "ssh_host": edge.ssh_host,
            }
        )

    if json_mode:
        print_json({"edges": edges, "summary": {"configured": len(edges)}})
        return 0

    table = create_table(title="NPS Edges")
    table.add_column("Edge", style="bold")
    table.add_column("Region")
    table.add_column("API URL", style="dim", overflow="fold")
    table.add_column("SSH Host")

    for entry in edges:
        table.add_row(
            entry["edge"], entry["region"], entry["api_url"], entry["ssh_host"] or "-"
        )

    console.print(table)
    console.print(f"[dim]{len(edges)} edges configured[/dim]")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    """Show status of all edge nodes."""
    json_mode = getattr(args, "json", False)
    try:
        cluster = NPSCluster(args.config)
    except FileNotFoundError as e:
        if json_mode:
            print_json({"error": str(e)})
        else:
            print_error(str(e))
        return 1

    if not cluster.edge_names:
        if json_mode:
            print_json({"error": "No edges configured"})
        else:
            print_error("No edges configured")
        return 1

    rows: list[_StatusRow] = []
    online = 0
    live_ctx = (
        Live(
            Spinner("dots", text="Checking edge status..."),
            console=console,
            transient=True,
        )
        if console.is_terminal and not json_mode
        else nullcontext()
    )

    with live_ctx:
        for name in cluster.edge_names:
            edge = cluster.get_edge(name)
            nps = cluster.get_client(name)
            if not edge or not nps:
                rows.append(
                    {"edge": name, "region": "", "api_url": "", "online": False}
                )
                continue

            try:
                # Try to get clients to verify connection
                client_mgmt.list_clients(nps, limit=1)
                is_online = True
                online += 1
            except NPSError:
                is_online = False

            rows.append(
                {
                    "edge": name,
                    "region": edge.region,
                    "api_url": edge.api_url,
                    "online": is_online,
                }
            )

    total = len(cluster.edge_names)
    if json_mode:
        print_json(
            {
                "edges": rows,
                "summary": {
                    "configured": total,
                    "online": online,
                    "offline": total - online,
                },
            }
        )
        return 0 if online == total else 1

    table = create_table(title="NPS Edge Status")
    table.add_column("Edge", style="bold")
    table.add_column("Region")
    table.add_column("API URL", style="dim", overflow="fold")
    table.add_column("Status")
    for row in rows:
        status = "[green]✓ Online[/green]" if row["online"] else "[red]✗ Offline[/red]"
        table.add_row(row["edge"], row["region"], row["api_url"], status)

    console.print(table)
    console.print(f"[dim]{online}/{total} edges online[/dim]")
    return 0 if online == total else 1
