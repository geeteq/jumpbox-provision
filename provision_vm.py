#!/usr/bin/env python3
"""Provision a RHEL9 jumpbox VM on OpenStack with cloud-init."""

import argparse
import os
import socket
import sys
import time
from pathlib import Path

import openstack
import yaml

SCRIPT_DIR = Path(__file__).parent
SSH_WAIT_TIMEOUT = 120
SSH_POLL_INTERVAL = 5


def load_config(path: str = "config.yaml") -> dict:
    with open(SCRIPT_DIR / path) as f:
        return yaml.safe_load(f)


def build_cloud_init(cfg: dict) -> str:
    ssh_cfg = cfg.get("ssh", {})
    user = ssh_cfg.get("baremetal_user", "baremetal")

    pub_key = os.environ.get("SSH_PUBLIC_KEY", "").strip()

    if not pub_key:
        pub_key = ssh_cfg.get("public_key", "").strip()

    if not pub_key:
        pub_key_file = ssh_cfg.get("public_key_file", "")
        if pub_key_file:
            pub_key = Path(pub_key_file).expanduser().read_text().strip()

    if not pub_key:
        print("WARNING: no SSH public key configured — VM will be inaccessible via SSH", file=sys.stderr)

    packages = cfg.get("packages", ["mtr"])

    cloud_config = {
        "users": [
            {
                "name": user,
                "groups": ["wheel"],
                "sudo": "ALL=(ALL) NOPASSWD:ALL",
                "shell": "/bin/bash",
                "lock_passwd": True,
                "ssh_authorized_keys": [pub_key] if pub_key else [],
            }
        ],
        "package_update": True,
        "package_upgrade": False,
        "packages": packages,
        "runcmd": [
            "echo 'Jumpbox provisioned by jumpbox-provision' > /etc/motd",
        ],
    }

    return "#cloud-config\n" + yaml.dump(cloud_config, default_flow_style=False)


def connect(cfg: dict, clouds_file: str = None) -> openstack.connection.Connection:
    cloud_name = cfg.get("cloud", "")
    if not cloud_name:
        print("ERROR: 'cloud' key missing from config.yaml", file=sys.stderr)
        sys.exit(1)

    kwargs = {"cloud": cloud_name}
    if clouds_file:
        os.environ["OS_CLIENT_CONFIG_FILE"] = clouds_file

    return openstack.connect(**kwargs)


def resolve_floating_network(conn: openstack.connection.Connection, pool: str) -> str:
    network = conn.network.find_network(pool, ignore_missing=True)
    if not network:
        print(f"ERROR: floating_ip_pool '{pool}' not found", file=sys.stderr)
        sys.exit(1)
    return network.id


def get_server_ip(server) -> str:
    for net_addresses in server.addresses.values():
        for addr in net_addresses:
            return addr["addr"]
    return ""


def wait_for_ssh(host: str, timeout: int = SSH_WAIT_TIMEOUT, interval: int = SSH_POLL_INTERVAL):
    print(f"Waiting for SSH on {host}:22 (up to {timeout}s) ...")
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection((host, 22), timeout=5):
                print(f"SSH is ready on {host}.")
                return
        except OSError:
            time.sleep(interval)
    print(f"WARNING: SSH on {host}:22 not reachable after {timeout}s — cloud-init may still be running.", file=sys.stderr)


def provision(cfg: dict, conn: openstack.connection.Connection, dry_run: bool = False) -> None:
    vm_cfg = cfg.get("vm", {})
    vm_name = vm_cfg["name"]

    existing = conn.compute.find_server(vm_name)
    if existing:
        print(f"VM '{vm_name}' already exists (id: {existing.id}, status: {existing.status}) — skipping.")
        return

    image = conn.compute.find_image(vm_cfg["image"])
    if not image:
        print(f"ERROR: image '{vm_cfg['image']}' not found", file=sys.stderr)
        sys.exit(1)

    flavor = conn.compute.find_flavor(vm_cfg["flavor"])
    if not flavor:
        print(f"ERROR: flavor '{vm_cfg['flavor']}' not found", file=sys.stderr)
        sys.exit(1)

    network = conn.network.find_network(vm_cfg["network"])
    if not network:
        print(f"ERROR: network '{vm_cfg['network']}' not found", file=sys.stderr)
        sys.exit(1)

    user_data = build_cloud_init(cfg)

    metadata = {"provisioned_by": "jumpbox-provision", "managed": "true"}
    if os.environ.get("CI_PIPELINE_ID"):
        metadata["gitlab_pipeline_id"] = os.environ["CI_PIPELINE_ID"]
    if os.environ.get("CI_PROJECT_NAME"):
        metadata["gitlab_project"] = os.environ["CI_PROJECT_NAME"]

    print(f"VM name:    {vm_name}")
    print(f"Image:      {image.name} ({image.id})")
    print(f"Flavor:     {flavor.name} ({flavor.id})")
    print(f"Network:    {network.name} ({network.id})")
    print(f"Sec groups: {vm_cfg.get('security_groups', ['default'])}")
    print(f"Metadata:   {metadata}")
    print("--- cloud-init ---")
    print(user_data)
    print("------------------")

    if dry_run:
        print("Dry run complete — no VM was created.")
        return

    server_kwargs = {
        "name": vm_name,
        "image_id": image.id,
        "flavor_id": flavor.id,
        "networks": [{"uuid": network.id}],
        "security_groups": [{"name": sg} for sg in vm_cfg.get("security_groups", ["default"])],
        "user_data": user_data,
        "metadata": metadata,
    }

    if vm_cfg.get("availability_zone"):
        server_kwargs["availability_zone"] = vm_cfg["availability_zone"]

    print(f"Creating VM '{vm_name}' ...")
    server = conn.compute.create_server(**server_kwargs)

    print("Waiting for VM to become ACTIVE ...")
    server = conn.compute.wait_for_server(server, status="ACTIVE", wait=300)
    print(f"VM '{vm_name}' is ACTIVE (id: {server.id})")

    fip_pool = vm_cfg.get("floating_ip_pool", "")
    if fip_pool:
        print(f"Allocating floating IP from pool '{fip_pool}' ...")
        net_id = resolve_floating_network(conn, fip_pool)
        fip = conn.network.create_ip(floating_network_id=net_id)
        conn.compute.add_floating_ip_to_server(server, fip.floating_ip_address)
        ssh_host = fip.floating_ip_address
        print(f"Floating IP: {ssh_host}")
    else:
        ssh_host = get_server_ip(server)
        print(f"IP address:  {ssh_host}")

    if ssh_host:
        wait_for_ssh(ssh_host)
        ssh_user = cfg.get("ssh", {}).get("baremetal_user", "baremetal")
        print(f"\nConnect with: ssh {ssh_user}@{ssh_host}")

    print("Provisioning complete.")


def main():
    parser = argparse.ArgumentParser(description="Provision a RHEL9 jumpbox on OpenStack")
    parser.add_argument("--config", default="config.yaml", help="Path to config file")
    parser.add_argument("--clouds", default=None, help="Path to clouds.yaml (overrides default search)")
    parser.add_argument("--dry-run", action="store_true", help="Validate config and print plan without creating VM")
    args = parser.parse_args()

    cfg = load_config(args.config)
    conn = connect(cfg, clouds_file=args.clouds)
    provision(cfg, conn, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
