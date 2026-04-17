#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLOUDS_FILE="${1:-}"

if [[ -z "${CLOUDS_FILE}" ]]; then
  echo "Usage: bash make_dotenv.sh <clouds.yaml>"
  echo "Example: bash make_dotenv.sh ~/Downloads/clouds.yaml"
  exit 1
fi

if [[ ! -f "${CLOUDS_FILE}" ]]; then
  echo "ERROR: file not found: ${CLOUDS_FILE}"
  exit 1
fi

ENV_FILE="${SCRIPT_DIR}/.env"

if [[ -f "${ENV_FILE}" ]]; then
  read -rp ".env already exists — overwrite? [y/N] " confirm
  [[ "${confirm}" =~ ^[Yy]$ ]] || { echo "Aborted."; exit 0; }
fi

if ! command -v python3 &>/dev/null; then
  echo "ERROR: python3 is required"
  exit 1
fi

echo "Parsing ${CLOUDS_FILE} ..."

PARSED=$(python3 - "${CLOUDS_FILE}" <<'PYEOF'
import sys
import yaml

with open(sys.argv[1]) as f:
    data = yaml.safe_load(f)

clouds = data.get("clouds", {})

if not clouds:
    print("ERROR: no clouds found in file", file=sys.stderr)
    sys.exit(1)

# If multiple clouds, pick the first one
cloud_name = list(clouds.keys())[0]
if len(clouds) > 1:
    print(f"Multiple clouds found: {list(clouds.keys())} — using '{cloud_name}'", file=sys.stderr)

cloud = clouds[cloud_name]
auth = cloud.get("auth", {})

fields = {
    "OS_AUTH_URL":             auth.get("auth_url", ""),
    "OS_USERNAME":             auth.get("username", ""),
    "OS_PASSWORD":             auth.get("password", ""),
    "OS_PROJECT_NAME":         auth.get("project_name", ""),
    "OS_PROJECT_ID":           auth.get("project_id", ""),
    "OS_PROJECT_DOMAIN_NAME":  auth.get("project_domain_name", ""),
    "OS_PROJECT_DOMAIN_ID":    auth.get("project_domain_id", ""),
    "OS_USER_DOMAIN_NAME":     auth.get("user_domain_name", ""),
}

for key, val in fields.items():
    if val:
        print(f"{key}={val}")
PYEOF
)

# Prompt for password if not present in the yaml
if ! echo "${PARSED}" | grep -q "^OS_PASSWORD=."; then
  read -rsp "OpenStack password (not found in clouds.yaml): " OS_PASSWORD
  echo
  PARSED="${PARSED}"$'\n'"OS_PASSWORD=${OS_PASSWORD}"
fi

cat > "${ENV_FILE}" <<EOF
# Generated from $(basename "${CLOUDS_FILE}") on $(date +%Y-%m-%d)
${PARSED}

# OpenStack application credential (preferred over username/password in CI)
OS_APPLICATION_CREDENTIAL_ID=
OS_APPLICATION_CREDENTIAL_SECRET=

# SSH public key injected into the baremetal user on the VM
SSH_PUBLIC_KEY=

# GitHub token
GITHUB_TOKEN=
EOF

echo ".env written to ${ENV_FILE}"
echo ""
echo "Next steps:"
echo "  1. Fill in OS_APPLICATION_CREDENTIAL_ID / SECRET (run: bash generate_api_key.sh)"
echo "  2. Add your SSH_PUBLIC_KEY"
echo "  3. Never commit .env to git"
