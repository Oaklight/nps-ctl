"""CLI command: clients - List and manage NPC clients."""

import argparse
import sys
from typing import Any

from nps_ctl import client_mgmt
from nps_ctl.cli.helpers import format_table
from nps_ctl.cluster import NPSCluster
from nps_ctl.exceptions import NPSError


def cmd_clients(args: argparse.Namespace) -> int:
    """List clients on edge nodes."""
    try:
        cluster = NPSCluster(args.config)
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    if args.all:
        # Show clients from all edges
        all_clients = cluster.get_all_clients()
        for edge_name, clients in all_clients.items():
            edge = cluster.get_edge(edge_name)
            region = edge.region if edge else ""
            print(f"\n=== {edge_name} ({region}) ===")
            _print_clients(clients)
    else:
        # Show clients from specific edge
        edge_name = args.edge
        if not edge_name:
            # Use first edge as default
            edge_name = cluster.edge_names[0] if cluster.edge_names else None
            if not edge_name:
                print("Error: No edges configured", file=sys.stderr)
                return 1

        nps = cluster.get_client(edge_name)
        if not nps:
            print(f"Error: Edge '{edge_name}' not found", file=sys.stderr)
            return 1

        try:
            clients = client_mgmt.list_clients(nps)
            _print_clients(clients)
        except NPSError as e:
            print(f"Error: {e}", file=sys.stderr)
            return 1

    return 0


def _print_clients(clients: list[dict[str, Any]]) -> None:
    """Print client list as table."""
    headers = ["ID", "Remark", "VKey", "Status", "Conn"]
    rows = []
    for c in clients:
        status = "Connected" if c.get("IsConnect") else "Disconnected"
        rows.append(
            [
                str(c.get("Id", "")),
                c.get("Remark", ""),
                c.get("VerifyKey", "")[:20] + "..."
                if len(c.get("VerifyKey", "")) > 20
                else c.get("VerifyKey", ""),
                status,
                str(c.get("NowConn", 0)),
            ]
        )
    print(format_table(headers, rows))
