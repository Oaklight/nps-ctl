"""CLI commands: sync, export - Sync and export configuration."""

import argparse
import json
import sys

from .. import client_mgmt, host, tunnel
from ..cluster import NPSCluster
from ..exceptions import NPSError


def cmd_sync(args: argparse.Namespace) -> int:
    """Sync configuration from one edge to others."""
    try:
        cluster = NPSCluster(args.config)
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    source = args.source
    if source not in cluster.edge_names:
        print(f"Error: Source edge '{source}' not found", file=sys.stderr)
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
            print(f"Error: Unknown target edges: {', '.join(invalid)}", file=sys.stderr)
            return 1
        if source in target_edges:
            target_edges = [t for t in target_edges if t != source]
    else:
        target_edges = [n for n in cluster.edge_names if n != source]

    if not target_edges:
        print("Error: No target edges to sync to", file=sys.stderr)
        return 1

    # Confirm
    if not args.yes:
        print(f"Will sync from '{source}' to: {', '.join(target_edges)}")
        print(
            f"Sync: clients={sync_clients}, tunnels={sync_tunnels}, hosts={sync_hosts}"
        )
        response = input("Continue? [y/N] ")
        if response.lower() != "y":
            print("Aborted.")
            return 0

    try:
        results = cluster.sync_from(
            source,
            sync_clients=sync_clients,
            sync_tunnels=sync_tunnels,
            sync_hosts=sync_hosts,
            target_edges=target_edges,
            show_progress=True,
        )
        for target, ops in results.items():
            print(f"\n{target}:")
            for op, success in ops.items():
                status = "✓" if success else "✗"
                print(f"  {status} {op}")
    except NPSError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    return 0


def cmd_export(args: argparse.Namespace) -> int:
    """Export configuration from an edge."""
    try:
        cluster = NPSCluster(args.config)
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
