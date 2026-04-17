#!/usr/bin/env python3
"""Test OpenStack authentication from clouds.yaml."""

import sys
import os
import argparse
import getpass
from pathlib import Path

import openstack
import yaml


def get_username_from_clouds(clouds_file: str, cloud_name: str) -> str:
    path = clouds_file or os.path.expanduser("~/.config/openstack/clouds.yaml")
    try:
        with open(path) as f:
            data = yaml.safe_load(f)
        return data["clouds"][cloud_name]["auth"].get("username", "")
    except Exception:
        return ""


def test_auth(clouds_file: str, cloud_name: str):
    if clouds_file:
        os.environ["OS_CLIENT_CONFIG_FILE"] = clouds_file

    print(f"clouds.yaml: {clouds_file or '~/.config/openstack/clouds.yaml'}")
    print(f"cloud name:  {cloud_name}")

    username = get_username_from_clouds(clouds_file, cloud_name)
    if username:
        print(f"username:    {username}")

    password = getpass.getpass("Password: ")
    os.environ["OS_PASSWORD"] = password
    print()

    try:
        conn = openstack.connect(cloud=cloud_name)
        token = conn.auth_token
        print(f"Authentication successful.")
        print(f"Token: {token[:20]}...")

        user = conn.identity.get_user(conn.current_user_id)
        project = conn.identity.get_project(conn.current_project_id)
        print(f"User:    {user.name}")
        print(f"Project: {project.name}")

    except Exception as e:
        print(f"Authentication failed: {e}", file=sys.stderr)
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="Test OpenStack auth from clouds.yaml")
    parser.add_argument("--clouds", default=None, help="Path to clouds.yaml")
    parser.add_argument("--cloud", default="openstack", help="Cloud name (default: openstack)")
    args = parser.parse_args()

    test_auth(clouds_file=args.clouds, cloud_name=args.cloud)


if __name__ == "__main__":
    main()
