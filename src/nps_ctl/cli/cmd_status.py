"""CLI command: status - Show status of all edge nodes."""

import argparse

from rich.markup import escape

from ..cluster import NPSCluster
from ..status import EdgeStatus, build_status_payload, collect_edge_status
from .helpers import (
    clients_cell,
    console,
    count_cell,
    create_table,
    print_error,
    print_json,
    print_status_errors,
    status_cell,
    status_spinner,
    sum_counts,
    validate_read_target,
)


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


def _hosts_cell(row: EdgeStatus) -> str:
    """Render host-mapping and host-target-port counts."""
    if row.hosts_total is None:
        return "-"
    return f"{row.hosts_total} ({count_cell(row.ports)} ports)"


def _tunnels_cell(row: EdgeStatus) -> str:
    """Render tunnel, running, and server-port counts."""
    if row.tunnels_total is None:
        return "-"
    return (
        f"{row.tunnels_total} ({count_cell(row.tunnels_running)} running, "
        f"{count_cell(row.tunnel_ports)} ports)"
    )


def cmd_status(args: argparse.Namespace) -> int:
    """Show status and inventory for all or selected edge nodes."""
    json_mode = getattr(args, "json", False)
    usage_error = validate_read_target(args)
    if usage_error:
        if json_mode:
            print_json({"error": usage_error})
        else:
            print_error(usage_error)
        return 2

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

    edge_name = getattr(args, "edge", None)
    if edge_name and cluster.get_edge(edge_name) is None:
        message = f"Edge '{edge_name}' not found"
        if json_mode:
            print_json({"error": message})
        else:
            print_error(message)
        return 1

    selected = [edge_name] if edge_name else None
    with status_spinner("Checking edge status...", json_mode=json_mode):
        rows = collect_edge_status(
            cluster,
            edge_names=selected,
            include_hosts=True,
            include_tunnels=True,
        )

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
    table.add_column("Tunnels", justify="right")
    for row in rows:
        table.add_row(
            escape(row.edge),
            escape(row.region or "-"),
            escape(row.api_url or "-"),
            status_cell(row),
            clients_cell(row),
            _hosts_cell(row),
            _tunnels_cell(row),
        )

    console.print(table, crop=False)

    online = sum(1 for row in rows if row.online)
    clients_online = sum_counts([row.clients_online for row in rows])
    clients_total = sum_counts([row.clients_total for row in rows])
    hosts_total = sum_counts([row.hosts_total for row in rows])
    host_ports = sum_counts([row.ports for row in rows])
    tunnels_total = sum_counts([row.tunnels_total for row in rows])
    tunnels_running = sum_counts([row.tunnels_running for row in rows])
    tunnel_ports = sum_counts([row.tunnel_ports for row in rows])
    clients_text = "-" if clients_total is None else f"{clients_online}/{clients_total}"
    hosts_text = (
        f"{hosts_total} host mappings ({count_cell(host_ports)} ports)"
        if hosts_total is not None
        else "- host mappings"
    )
    tunnels_text = (
        f"{tunnels_total} tunnels "
        f"({count_cell(tunnels_running)} running, "
        f"{count_cell(tunnel_ports)} ports)"
        if tunnels_total is not None
        else "- tunnels"
    )
    console.print(
        f"[dim]{online}/{len(rows)} edges online; clients {clients_text} online, "
        f"{hosts_text}, {tunnels_text}[/dim]"
    )
    print_status_errors(rows)
    return 0 if all(row.ok for row in rows) else 1
