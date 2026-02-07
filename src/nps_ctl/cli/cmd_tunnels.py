"""CLI command: tunnels - List and manage tunnels."""

import argparse
import sys
from typing import Any

from .. import client_mgmt, tunnel
from ..cluster import NPSCluster
from ..exceptions import NPSError
from .helpers import format_table


def cmd_tunnels(args: argparse.Namespace) -> int:
    """List tunnels on edge nodes."""
    try:
        cluster = NPSCluster(args.config)
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    tunnel_type = getattr(args, "type", "") or ""

    if args.all:
        all_tunnels = cluster.get_all_tunnels()
        for edge_name, tunnels in all_tunnels.items():
            edge = cluster.get_edge(edge_name)
            region = edge.region if edge else ""
            print(f"\n=== {edge_name} ({region}) ===")
            _print_tunnels(tunnels)
    else:
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
            tunnels = tunnel.list_tunnels(nps, tunnel_type=tunnel_type)
            _print_tunnels(tunnels)
        except NPSError as e:
            print(f"Error: {e}", file=sys.stderr)
            return 1

    return 0


def cmd_add_tunnel(args: argparse.Namespace) -> int:
    """Add a tunnel to an edge."""
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

    # Confirm
    if not args.yes:
        print(f"Will add {args.type} tunnel on {edge_name}")
        print(
            f"Client: {args.client}, Port: {args.port}, Target: {args.target or 'N/A'}"
        )
        response = input("Continue? [y/N] ")
        if response.lower() != "y":
            print("Aborted.")
            return 0

    try:
        # Find client
        clients = client_mgmt.list_clients(nps, search=args.client)
        matching = [c for c in clients if c.get("Remark") == args.client]
        if not matching:
            print(f"Error: Client '{args.client}' not found", file=sys.stderr)
            return 1

        client_id = matching[0]["Id"]
        success = tunnel.add_tunnel(
            nps,
            client_id=client_id,
            tunnel_type=args.type,
            port=args.port,
            target=args.target or "",
            remark=args.remark or "",
        )
        if success:
            print(f"✓ Added tunnel to {edge_name}")
        else:
            print("✗ Failed to add tunnel")
            return 1
    except NPSError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    return 0


def _print_tunnels(tunnels: list[dict[str, Any]]) -> None:
    """Print tunnel list as table."""
    headers = ["ID", "Type", "Port", "Target", "Client", "Status"]
    rows = []
    for t in tunnels:
        client_info = t.get("Client", {})
        client_name = client_info.get("Remark", "") if client_info else ""
        status = "Running" if t.get("RunStatus") else "Stopped"
        target = t.get("Target", {})
        target_addr = target.get("TargetStr", "") if target else t.get("TargetAddr", "")

        rows.append(
            [
                str(t.get("Id", "")),
                t.get("Mode", ""),
                str(t.get("Port", "")),
                target_addr,
                client_name,
                status,
            ]
        )
    print(format_table(headers, rows))
