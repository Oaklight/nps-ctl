"""CLI command: status - Show status of all edge nodes."""

import argparse
from contextlib import nullcontext

from rich.live import Live
from rich.markup import escape
from rich.spinner import Spinner

from ..cluster import NPSCluster
from ..status import (
    EdgeStatus,
    build_status_payload,
    collect_edge_status,
)
from .helpers import console, create_table, print_error, print_json


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

    console.print(table, crop=False)
    console.print(f"[dim]{len(edges)} edges configured[/dim]")
    return 0


def _status_cell(row: EdgeStatus) -> str:
    """Format the reachability cell for one edge."""
    if row.ok:
        return "[green]✓ Online[/green]"
    if row.partial:
        return "[yellow]⚠ Partial[/yellow]"
    return "[red]✗ Offline[/red]"


def _count_cell(value: int | None) -> str:
    """Render an unknown count as ``-``."""
    return "-" if value is None else str(value)


def _sum_or_none(values: list[int | None]) -> int | None:
    """Sum counts, or return None when any edge failed to report."""
    if any(value is None for value in values):
        return None
    return sum(value for value in values if value is not None)


def cmd_status(args: argparse.Namespace) -> int:
    """Show status and inventory for all edge nodes."""
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
        rows = collect_edge_status(cluster)

    if json_mode:
        print_json(build_status_payload(rows))
        return 0 if all(row.ok for row in rows) else 1

    table = create_table(title="NPS Edge Status")
    table.add_column("Edge", style="bold")
    table.add_column("Region")
    table.add_column("API URL", style="dim", overflow="fold")
    table.add_column("Status")
    table.add_column("Clients", justify="right")
    table.add_column("Hosts", justify="right")
    table.add_column("Ports", justify="right")
    for row in rows:
        clients = (
            "-"
            if row.clients_total is None
            else f"{row.clients_online}/{row.clients_total}"
        )
        table.add_row(
            escape(row.edge),
            escape(row.region or "-"),
            escape(row.api_url or "-"),
            _status_cell(row),
            clients,
            _count_cell(row.hosts_total),
            _count_cell(row.ports),
        )

    console.print(table, crop=False)

    online = sum(1 for row in rows if row.online)
    clients_online = _sum_or_none([row.clients_online for row in rows])
    clients_total = _sum_or_none([row.clients_total for row in rows])
    hosts_total = _sum_or_none([row.hosts_total for row in rows])
    ports = _sum_or_none([row.ports for row in rows])
    clients_text = "-" if clients_total is None else f"{clients_online}/{clients_total}"
    console.print(
        f"[dim]{online}/{len(rows)} edges online; clients {clients_text} online, "
        f"{_count_cell(hosts_total)} host mappings, "
        f"{_count_cell(ports)} target ports[/dim]"
    )

    for row in rows:
        if row.error:
            console.print(f"[red]{escape(row.edge)}: {escape(row.error)}[/red]")
    return 0 if all(row.ok for row in rows) else 1
