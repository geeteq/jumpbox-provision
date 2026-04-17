#!/usr/bin/env python3
"""Provision a RHEL9 jumpbox VM on OpenStack with cloud-init."""

import argparse
import os
import re
import sys
import time
from pathlib import Path

import openstack
import yaml

SCRIPT_DIR = Path(__file__).parent


def load_config(path: str = "config.yaml") -> dict:
    config_path = SCRIPT_DIR / path
    with open(config_path) as f:
        raw = f.read()

    # Expand ${VAR} and ${VAR:-default} placeholders from environment
    def replace_env(match):
        key, _, default = match.group(1).partition(":-")
        return os.environ.get(key, default)

    raw = re.sub(r"\$\{([^}]+)\}", replace_env, raw)
    return yaml.safe_load(raw)


def load_env(env_file: str = ".env"):
    env_path = SCRIPT_DIR / env_file
    if env_path.exists():
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, value = line.partition("=")
                    os.environ.setdefault(key.strip(), value.strip())


def build_cloud_init(cfg: dict) -> str:
    ssh_cfg = cfg.get("ssh", {})
    user = ssh_cfg.get("baremetal_user", "baremetal")
    pub_key = ssh_cfg.get("public_key", "")
    pub_key_file = ssh_cfg.get("public_key_file", "")

    if pub_key_file and not pub_key:
        key_path = Path(pub_key_file).expanduser()
        pub_key = key_path.read_text().strip()

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
            f"echo 'Jumpbox provisioned by jumpbox-provision' > /etc/motd",
        ],
    }

    return "#cloud-config\n" + yaml.dump(cloud_config, default_flow_style=False)


def connect(cfg: dict) -> openstack.connection.Connection:
    os_cfg = cfg.get("openstack", {})

    # Prefer application credentials if set
    app_cred_id = os.environ.get("OS_APPLICATION_CREDENTIAL_ID")
    app_cred_secret = os.environ.get("OS_APPLICATION_CREDENTIAL_SECRET")

    if app_cred_id and app_cred_secret:
        auth = {
            "auth_url": os_cfg["auth_url"],
            "application_credential_id": app_cred_id,
            "application_credential_secret": app_cred_secret,
        }
        auth_type = "v3applicationcredential"
    else:
        auth = {
            "auth_url": os_cfg["auth_url"],
            "username": os_cfg["username"],
            "password": os_cfg["password"],
            "project_name": os_cfg["project_name"],
            "project_domain_name": os_cfg.get("project_domain_name", "Default"),
            "user_domain_name": os_cfg.get("user_domain_name", "Default"),
        }
        auth_type = "password"

    return openstack.connect(
        auth=auth,
        auth_type=auth_type,
        region_name=os_cfg.get("region_name", "RegionOne"),
    )


def provision(cfg: dict, conn: openstack.connection.Connection) -> None:
    vm_cfg = cfg.get("vm", {})
    vm_name = vm_cfg["name"]

    # Resolve image
    image = conn.compute.find_image(vm_cfg["image"])
    if not image:
        print(f"ERROR: image '{vm_cfg['image']}' not found", file=sys.stderr)
        sys.exit(1)

    # Resolve flavor
    flavor = conn.compute.find_flavor(vm_cfg["flavor"])
    if not flavor:
        print(f"ERROR: flavor '{vm_cfg['flavor']}' not found", file=sys.stderr)
        sys.exit(1)

    # Resolve network
    network = conn.network.find_network(vm_cfg["network"])
    if not network:
        print(f"ERROR: network '{vm_cfg['network']}' not found", file=sys.stderr)
        sys.exit(1)

    user_data = build_cloud_init(cfg)

    server_kwargs = {
        "name": vm_name,
        "image_id": image.id,
        "flavor_id": flavor.id,
        "networks": [{"uuid": network.id}],
        "security_groups": [{"name": sg} for sg in vm_cfg.get("security_groups", ["default"])],
        "user_data": user_data,
    }

    if vm_cfg.get("availability_zone"):
        server_kwargs["availability_zone"] = vm_cfg["availability_zone"]

    print(f"Creating VM '{vm_name}' ...")
    print(f"  Image:   {image.name} ({image.id})")
    print(f"  Flavor:  {flavor.name} ({flavor.id})")
    print(f"  Network: {network.name} ({network.id})")

    server = conn.compute.create_server(**server_kwargs)

    print("Waiting for VM to become ACTIVE ...")
    server = conn.compute.wait_for_server(server, status="ACTIVE", wait=300)
    print(f"VM '{vm_name}' is ACTIVE (id: {server.id})")

    # Assign floating IP if pool configured
    fip_pool = vm_cfg.get("floating_ip_pool", "")
    if fip_pool:
        print(f"Allocating floating IP from pool '{fip_pool}' ...")
        fip = conn.network.create_ip(floating_network_id=fip_pool)
        conn.compute.add_floating_ip_to_server(server, fip.floating_ip_address)
        print(f"Floating IP assigned: {fip.floating_ip_address}")
    else:
        addresses = server.addresses
        print(f"Addresses: {addresses}")

    print("Provisioning complete.")


def main():
    parser = argparse.ArgumentParser(description="Provision a RHEL9 jumpbox on OpenStack")
    parser.add_argument("--config", default="config.yaml", help="Path to config file")
    parser.add_argument("--env", default=".env", help="Path to .env file")
    args = parser.parse_args()

    load_env(args.env)
    cfg = load_config(args.config)
    conn = connect(cfg)
    provision(cfg, conn)


if __name__ == "__main__":
    main()
