"""CLI command: status - Show status of all edge nodes."""

import argparse
import sys

from .. import client_mgmt
from ..cluster import NPSCluster
from ..exceptions import NPSError
from .helpers import format_table


def cmd_status(args: argparse.Namespace) -> int:
    """Show status of all edge nodes."""
    try:
        cluster = NPSCluster(args.config)
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    headers = ["Edge", "Region", "API URL", "Status"]
    rows = []

    for name in cluster.edge_names:
        edge = cluster.get_edge(name)
        nps = cluster.get_client(name)
        if not edge or not nps:
            continue

        try:
            # Try to get clients to verify connection
            client_mgmt.list_clients(nps, limit=1)
            status = "✓ Online"
        except NPSError:
            status = "✗ Offline"

        rows.append([name, edge.region, edge.api_url, status])

    print(format_table(headers, rows))
    return 0
