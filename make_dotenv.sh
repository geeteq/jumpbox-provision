#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RC_FILE="${1:-}"

if [[ -z "${RC_FILE}" ]]; then
  echo "Usage: bash make_dotenv.sh <openstack-rc-file>"
  echo "Example: bash make_dotenv.sh ~/Downloads/my-project-openrc.sh"
  exit 1
fi

if [[ ! -f "${RC_FILE}" ]]; then
  echo "ERROR: file not found: ${RC_FILE}"
  exit 1
fi

ENV_FILE="${SCRIPT_DIR}/.env"

if [[ -f "${ENV_FILE}" ]]; then
  read -rp ".env already exists — overwrite? [y/N] " confirm
  [[ "${confirm}" =~ ^[Yy]$ ]] || { echo "Aborted."; exit 0; }
fi

echo "Parsing ${RC_FILE} ..."

# Extract export KEY=VALUE lines, strip the 'export ' prefix
PARSED=$(grep -E '^\s*export\s+OS_' "${RC_FILE}" \
  | sed 's/^\s*export\s*//' \
  | sed "s/['\"]//g")

# Prompt for password if it's a read command in the RC file
if grep -qE 'read\s+-sr?\s+OS_PASSWORD' "${RC_FILE}" 2>/dev/null; then
  read -rsp "OpenStack password: " OS_PASSWORD
  echo
  PARSED="${PARSED}"$'\n'"OS_PASSWORD=${OS_PASSWORD}"
fi

cat > "${ENV_FILE}" <<EOF
# Generated from $(basename "${RC_FILE}") on $(date +%Y-%m-%d)
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
