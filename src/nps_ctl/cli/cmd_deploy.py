"""CLI commands: install, uninstall - Deploy NPS to edge nodes."""

import argparse
import sys
from pathlib import Path

from ..cluster import NPSCluster
from ..deploy import (
    DEFAULT_NPS_VERSION,
    install_nps,
    load_template,
    render_template,
    uninstall_nps,
)
from .helpers import get_template_path


def cmd_install(args: argparse.Namespace) -> int:
    """Install NPS on edge nodes via SSH."""
    import tomllib

    try:
        cluster = NPSCluster(args.config)
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    # Load full config to get web credentials and auth_crypt_key
    config_path = Path(args.config)
    with open(config_path, "rb") as f:
        full_config = tomllib.load(f)

    web_config = full_config.get("web", {})
    web_username = web_config.get("username", "admin")
    web_password = web_config.get("password", "")
    auth_crypt_key = full_config.get("auth_crypt_key", "")
    public_vkey = full_config.get("public_vkey", "")

    # Port configuration with defaults
    ports_config = full_config.get("ports", {})
    http_proxy_port = ports_config.get("http_proxy", 30080)
    bridge_port = ports_config.get("bridge", 51234)
    web_port = ports_config.get("web", 25412)

    # Load template
    template_path = args.template
    if template_path:
        template_path = Path(template_path)
    else:
        template_path = get_template_path() / "nps.conf.template"

    try:
        template = load_template(template_path)
    except FileNotFoundError:
        print(f"Warning: Template not found at {template_path}, using default")
        template = None

    # Determine target edges
    if args.edge:
        if args.edge not in cluster.edge_names:
            print(f"Error: Edge '{args.edge}' not found", file=sys.stderr)
            return 1
        target_edges = [args.edge]
    else:
        target_edges = cluster.edge_names

    # Get version
    version = args.version or DEFAULT_NPS_VERSION

    # Check for force reinstall
    force_reinstall = getattr(args, "force_reinstall", False)

    # Confirm
    if not args.yes:
        print(f"Will install NPS {version} on: {', '.join(target_edges)}")
        if force_reinstall:
            print("This will (force reinstall):")
            print("  - Uninstall existing NPS first")
        else:
            print("This will:")
        print("  - Download NPS from mirrors (jsdelivr CDN, GitHub)")
        print("  - Install to /etc/nps/ using nps install")
        print("  - Configure and start NPS")
        response = input("Continue? [y/N] ")
        if response.lower() != "y":
            print("Aborted.")
            return 0

    success_count = 0
    fail_count = 0

    for edge_name in target_edges:
        edge = cluster.get_edge(edge_name)
        if not edge or not edge.ssh_host:
            print(f"✗ {edge_name}: No SSH host configured")
            fail_count += 1
            continue

        # Force reinstall: uninstall first
        if force_reinstall:
            print(f"\nUninstalling NPS from {edge_name} ({edge.ssh_host})...")
            uninstall_result = uninstall_nps(ssh_host=edge.ssh_host)
            if uninstall_result.success:
                print("  ✓ Uninstalled successfully")
                if args.verbose and uninstall_result.stdout:
                    for line in uninstall_result.stdout.strip().split("\n"):
                        print(f"    {line}")
            else:
                # Uninstall failure is not fatal - NPS might not be installed
                print(f"  ⚠ Uninstall: {uninstall_result.message}")
                if args.verbose and uninstall_result.stderr:
                    for line in uninstall_result.stderr.strip().split("\n"):
                        print(f"    {line}")

        print(f"\nInstalling NPS on {edge_name} ({edge.ssh_host})...")

        # Generate config for this edge
        variables = {
            "web_username": web_username,
            "web_password": web_password,
            "auth_key": edge.auth_key,
            "auth_crypt_key": auth_crypt_key,
            "public_vkey": public_vkey,
            "http_proxy_port": http_proxy_port,
            "bridge_port": bridge_port,
            "web_port": web_port,
        }

        if template:
            nps_conf = render_template(template, variables)
        else:
            # Fallback to inline template
            nps_conf = _get_default_template().format(**variables)

        result = install_nps(
            ssh_host=edge.ssh_host,
            nps_conf=nps_conf,
            version=args.version or DEFAULT_NPS_VERSION,
            release_url=args.release_url,
        )

        if result.success:
            print(f"✓ {edge_name}: Installed successfully")
            if args.verbose and result.stdout:
                for line in result.stdout.strip().split("\n"):
                    print(f"  {line}")
            success_count += 1
        else:
            print(f"✗ {edge_name}: {result.message}")
            if result.stderr:
                for line in result.stderr.strip().split("\n"):
                    print(f"  {line}")
            if result.stdout:
                for line in result.stdout.strip().split("\n"):
                    print(f"  {line}")
            fail_count += 1

    print(f"\nSummary: {success_count} succeeded, {fail_count} failed")
    return 0 if fail_count == 0 else 1


def cmd_uninstall(args: argparse.Namespace) -> int:
    """Uninstall NPS from edge nodes via SSH."""
    try:
        cluster = NPSCluster(args.config)
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    # Determine target edges
    if args.edge:
        if args.edge not in cluster.edge_names:
            print(f"Error: Edge '{args.edge}' not found", file=sys.stderr)
            return 1
        target_edges = [args.edge]
    else:
        target_edges = cluster.edge_names

    # Confirm
    if not args.yes:
        print(f"Will uninstall NPS from: {', '.join(target_edges)}")
        print("This will:")
        print("  - Stop and disable Nps.service")
        print("  - Remove /usr/bin/nps")
        print("  - Remove /etc/nps/")
        response = input("Continue? [y/N] ")
        if response.lower() != "y":
            print("Aborted.")
            return 0

    success_count = 0
    fail_count = 0

    for edge_name in target_edges:
        edge = cluster.get_edge(edge_name)
        if not edge or not edge.ssh_host:
            print(f"✗ {edge_name}: No SSH host configured")
            fail_count += 1
            continue

        print(f"\nUninstalling NPS from {edge_name} ({edge.ssh_host})...")

        result = uninstall_nps(ssh_host=edge.ssh_host)

        if result.success:
            print(f"✓ {edge_name}: Uninstalled successfully")
            if args.verbose and result.stdout:
                for line in result.stdout.strip().split("\n"):
                    print(f"  {line}")
            success_count += 1
        else:
            print(f"✗ {edge_name}: {result.message}")
            if result.stderr:
                for line in result.stderr.strip().split("\n"):
                    print(f"  {line}")
            fail_count += 1

    print(f"\nSummary: {success_count} succeeded, {fail_count} failed")
    return 0 if fail_count == 0 else 1


def _get_default_template() -> str:
    """Get the default NPS configuration template."""
    return """#############################################
# NPS Edge Node Configuration
#############################################

appname=nps
runmode=pro
dns_server=1.1.1.1

#############################################
# HTTP Proxy Settings
#############################################
http_proxy_ip=0.0.0.0
http_proxy_port={http_proxy_port}

http_add_origin_header=true
allow_x_real_ip=true
trusted_proxy_ips=127.0.0.1

#############################################
# Client Connection Settings
#############################################
bridge_ip=0.0.0.0
bridge_port={bridge_port}

public_vkey={public_vkey}
disconnect_timeout=60

#############################################
# Web Management Settings
#############################################
web_username={web_username}
web_password={web_password}
open_captcha=true

web_ip=127.0.0.1
web_port={web_port}
web_open_ssl=false

allow_user_login=false
allow_user_register=false
allow_user_change_username=false

#############################################
# API Security Settings
#############################################
auth_key={auth_key}
auth_crypt_key={auth_crypt_key}

#############################################
# Extended Features
#############################################
flow_store_interval=1
allow_flow_limit=true
allow_rate_limit=true
allow_time_limit=true
allow_tunnel_num_limit=true
allow_local_proxy=false
allow_connection_num_limit=true
allow_multi_ip=true
system_info_display=true

#############################################
# Logging
#############################################
log_level=4
log_path=/var/log/nps.log
log_max_files=10
log_max_days=7
log_max_size=2
"""
