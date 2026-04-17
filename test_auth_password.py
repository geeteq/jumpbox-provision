#!/usr/bin/env python3
"""Test OpenStack authentication using username/password from clouds.yaml."""

import argparse
import getpass
import sys
import traceback
from pathlib import Path

import openstack
import yaml


def load_cloud_config(clouds_file: str, cloud_name: str) -> dict:
    path = Path(clouds_file).expanduser() if clouds_file else Path.home() / ".config/openstack/clouds.yaml"
    if not path.exists():
        print(f"ERROR: clouds.yaml not found at {path}", file=sys.stderr)
        sys.exit(1)
    with open(path) as f:
        data = yaml.safe_load(f)
    clouds = data.get("clouds", {})
    if cloud_name not in clouds:
        print(f"ERROR: cloud '{cloud_name}' not found. Available: {list(clouds.keys())}", file=sys.stderr)
        sys.exit(1)
    return clouds[cloud_name]


def main():
    parser = argparse.ArgumentParser(description="Test OpenStack password auth from clouds.yaml")
    parser.add_argument("--clouds", default=None, help="Path to clouds.yaml")
    parser.add_argument("--cloud", default="openstack", help="Cloud name (default: openstack)")
    args = parser.parse_args()

    cloud = load_cloud_config(args.clouds, args.cloud)
    auth = cloud.get("auth", {})

    print(f"cloud name:  {args.cloud}")
    print(f"auth_url:    {auth.get('auth_url', '')}")
    print(f"username:    {auth.get('username', '')}")
    print(f"project:     {auth.get('project_name', auth.get('project_id', ''))}")
    print(f"user_domain: {auth.get('user_domain_name', '')}")
    print()

    auth["password"] = getpass.getpass("Password: ")

    if auth.get("project_name") and auth.get("project_id"):
        del auth["project_id"]

    conn_kwargs = {
        "auth": auth,
        "auth_type": "password",
        "identity_api_version": cloud.get("identity_api_version", 3),
        "verify": False,
    }
    if cloud.get("region_name"):
        conn_kwargs["region_name"] = cloud["region_name"]
    if cloud.get("interface"):
        conn_kwargs["interface"] = cloud["interface"]

    print("\nAuthenticating ...")
    try:
        conn = openstack.connect(**conn_kwargs)
        token = conn.auth_token
        print(f"Authentication successful.")
        print(f"Token:   {token[:20]}...")
        user = conn.identity.get_user(conn.current_user_id)
        project = conn.identity.get_project(conn.current_project_id)
        print(f"User:    {user.name}")
        print(f"Project: {project.name}")
    except Exception as e:
        print(f"\nAuthentication failed: {e}", file=sys.stderr)
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
