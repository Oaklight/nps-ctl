"""CLI commands: npc-install, npc-uninstall, npc-status, npc-restart.

Deploy and manage NPC clients on remote servers.
"""

import argparse
import sys

from ..cluster import NPSCluster
from ..deploy import (
    DEFAULT_NPC_VERSION,
    check_npc_status,
    install_npc,
    restart_npc,
    uninstall_npc,
)


def cmd_npc_install(args: argparse.Namespace) -> int:
    """Install NPC on client machines via SSH."""
    try:
        cluster = NPSCluster(args.config)
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    # Determine target clients
    if args.client:
        if args.client not in cluster.npc_client_names:
            print(f"Error: NPC client '{args.client}' not found", file=sys.stderr)
            return 1
        target_clients = [args.client]
    else:
        target_clients = cluster.npc_client_names

    if not target_clients:
        print("Error: No NPC clients configured in edges.toml", file=sys.stderr)
        return 1

    # Get version
    version = args.version or DEFAULT_NPC_VERSION

    # Check for force reinstall
    force_reinstall = getattr(args, "force_reinstall", False)

    # Confirm
    if not args.yes:
        print(f"Will install NPC {version} on: {', '.join(target_clients)}")
        if force_reinstall:
            print("This will (force reinstall):")
            print("  - Uninstall existing NPC first")
        else:
            print("This will:")
        print("  - Download NPC from mirrors (jsdelivr CDN, GitHub)")
        print("  - Install using npc install (no-config mode)")
        print("  - Configure and start NPC service")
        response = input("Continue? [y/N] ")
        if response.lower() != "y":
            print("Aborted.")
            return 0

    success_count = 0
    fail_count = 0

    for client_name in target_clients:
        npc_config = cluster.get_npc_client(client_name)
        if not npc_config:
            print(f"✗ {client_name}: Configuration not found")
            fail_count += 1
            continue

        print(f"\nProcessing {client_name} ({npc_config.ssh_host})...")

        # Get vkey
        vkey = cluster.get_vkey_for_npc(npc_config)
        if not vkey:
            print(f"✗ {client_name}: Could not obtain vkey")
            print(
                f"  Hint: Either configure vkey in edges.toml or ensure client "
                f"'{npc_config.remark}' exists in NPS"
            )
            fail_count += 1
            continue

        # Get server addresses
        server_addrs = cluster.get_server_addrs_for_npc(npc_config)
        if not server_addrs:
            print(f"✗ {client_name}: No valid server addresses")
            fail_count += 1
            continue

        print(f"  Server addresses: {server_addrs}")
        print(f"  Connection type: {npc_config.conn_type}")

        # Force reinstall: uninstall first
        if force_reinstall:
            print("  Uninstalling existing NPC...")
            uninstall_result = uninstall_npc(ssh_host=npc_config.ssh_host)
            if uninstall_result.success:
                print("  ✓ Uninstalled successfully")
            else:
                print(f"  ⚠ Uninstall: {uninstall_result.message}")

        # Install NPC
        print("  Installing NPC...")
        result = install_npc(
            ssh_host=npc_config.ssh_host,
            server_addrs=server_addrs,
            vkey=vkey,
            tls_enable=(npc_config.conn_type == "tls"),
            version=version,
            release_url=args.release_url,
        )

        if result.success:
            print(f"✓ {client_name}: Installed successfully")
            if args.verbose and result.stdout:
                for line in result.stdout.strip().split("\n"):
                    print(f"  {line}")
            success_count += 1
        else:
            print(f"✗ {client_name}: {result.message}")
            if result.stderr:
                for line in result.stderr.strip().split("\n"):
                    print(f"  {line}")
            if result.stdout:
                for line in result.stdout.strip().split("\n"):
                    print(f"  {line}")
            fail_count += 1

    print(f"\nSummary: {success_count} succeeded, {fail_count} failed")
    return 0 if fail_count == 0 else 1


def cmd_npc_uninstall(args: argparse.Namespace) -> int:
    """Uninstall NPC from client machines via SSH."""
    try:
        cluster = NPSCluster(args.config)
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    # Determine target clients
    if args.client:
        if args.client not in cluster.npc_client_names:
            print(f"Error: NPC client '{args.client}' not found", file=sys.stderr)
            return 1
        target_clients = [args.client]
    else:
        target_clients = cluster.npc_client_names

    if not target_clients:
        print("Error: No NPC clients configured", file=sys.stderr)
        return 1

    # Confirm
    if not args.yes:
        print(f"Will uninstall NPC from: {', '.join(target_clients)}")
        print("This will:")
        print("  - Stop NPC service")
        print("  - Uninstall NPC")
        print("  - Remove NPC binary")
        response = input("Continue? [y/N] ")
        if response.lower() != "y":
            print("Aborted.")
            return 0

    success_count = 0
    fail_count = 0

    for client_name in target_clients:
        npc_config = cluster.get_npc_client(client_name)
        if not npc_config:
            print(f"✗ {client_name}: Configuration not found")
            fail_count += 1
            continue

        print(f"\nUninstalling NPC from {client_name} ({npc_config.ssh_host})...")

        result = uninstall_npc(ssh_host=npc_config.ssh_host)

        if result.success:
            print(f"✓ {client_name}: Uninstalled successfully")
            if args.verbose and result.stdout:
                for line in result.stdout.strip().split("\n"):
                    print(f"  {line}")
            success_count += 1
        else:
            print(f"✗ {client_name}: {result.message}")
            if result.stderr:
                for line in result.stderr.strip().split("\n"):
                    print(f"  {line}")
            fail_count += 1

    print(f"\nSummary: {success_count} succeeded, {fail_count} failed")
    return 0 if fail_count == 0 else 1


def cmd_npc_status(args: argparse.Namespace) -> int:
    """Check NPC status on client machines."""
    try:
        cluster = NPSCluster(args.config)
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    # Determine target clients
    if args.client:
        if args.client not in cluster.npc_client_names:
            print(f"Error: NPC client '{args.client}' not found", file=sys.stderr)
            return 1
        target_clients = [args.client]
    else:
        target_clients = cluster.npc_client_names

    if not target_clients:
        print("Error: No NPC clients configured", file=sys.stderr)
        return 1

    for client_name in target_clients:
        npc_config = cluster.get_npc_client(client_name)
        if not npc_config:
            print(f"✗ {client_name}: Configuration not found")
            continue

        print(f"\n=== {client_name} ({npc_config.ssh_host}) ===")

        result = check_npc_status(ssh_host=npc_config.ssh_host)

        if result.success:
            if result.stdout:
                print(result.stdout.strip())
        else:
            print(f"Error: {result.message}")
            if result.stderr:
                print(result.stderr.strip())

    return 0


def cmd_npc_restart(args: argparse.Namespace) -> int:
    """Restart NPC service on client machines."""
    try:
        cluster = NPSCluster(args.config)
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    # Determine target clients
    if args.client:
        if args.client not in cluster.npc_client_names:
            print(f"Error: NPC client '{args.client}' not found", file=sys.stderr)
            return 1
        target_clients = [args.client]
    else:
        target_clients = cluster.npc_client_names

    if not target_clients:
        print("Error: No NPC clients configured", file=sys.stderr)
        return 1

    success_count = 0
    fail_count = 0

    for client_name in target_clients:
        npc_config = cluster.get_npc_client(client_name)
        if not npc_config:
            print(f"✗ {client_name}: Configuration not found")
            fail_count += 1
            continue

        print(f"Restarting NPC on {client_name} ({npc_config.ssh_host})...")

        result = restart_npc(ssh_host=npc_config.ssh_host)

        if result.success:
            print(f"✓ {client_name}: Restarted successfully")
            if args.verbose and result.stdout:
                for line in result.stdout.strip().split("\n"):
                    print(f"  {line}")
            success_count += 1
        else:
            print(f"✗ {client_name}: {result.message}")
            if result.stderr:
                for line in result.stderr.strip().split("\n"):
                    print(f"  {line}")
            fail_count += 1

    print(f"\nSummary: {success_count} succeeded, {fail_count} failed")
    return 0 if fail_count == 0 else 1
