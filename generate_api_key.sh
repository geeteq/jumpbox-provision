#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ -f "${SCRIPT_DIR}/.env" ]]; then
  set -a
  source "${SCRIPT_DIR}/.env"
  set +a
fi

: "${OS_AUTH_URL:?OS_AUTH_URL is required}"
: "${OS_USERNAME:?OS_USERNAME is required}"
: "${OS_PASSWORD:?OS_PASSWORD is required}"
: "${OS_PROJECT_NAME:?OS_PROJECT_NAME is required}"

CRED_NAME="${1:-jumpbox-provision-cred}"
CRED_DESCRIPTION="Application credential for jumpbox VM provisioning"

if ! command -v openstack &>/dev/null; then
  echo "ERROR: openstack CLI not found. Install with: pip install python-openstackclient" >&2
  exit 1
fi

export OS_AUTH_URL OS_USERNAME OS_PASSWORD OS_PROJECT_NAME
export OS_PROJECT_DOMAIN_NAME="${OS_PROJECT_DOMAIN_NAME:-Default}"
export OS_IDENTITY_API_VERSION=3
unset OS_USER_DOMAIN_NAME OS_REGION_NAME OS_APPLICATION_CREDENTIAL_ID OS_APPLICATION_CREDENTIAL_SECRET

echo "Authenticating to OpenStack at ${OS_AUTH_URL} ..."

# Verify credentials before attempting credential creation
if ! openstack token issue -f value -c id > /dev/null 2>&1; then
  echo ""
  echo "ERROR: Authentication failed. Check the following in your .env:"
  echo "  OS_AUTH_URL    = ${OS_AUTH_URL}"
  echo "  OS_USERNAME    = ${OS_USERNAME}"
  echo "  OS_PROJECT_NAME= ${OS_PROJECT_NAME}"
  echo ""
  echo "Try running manually to see the full error:"
  echo "  openstack --os-auth-url ${OS_AUTH_URL} --os-username ${OS_USERNAME} --os-project-name ${OS_PROJECT_NAME} token issue"
  exit 1
fi

echo "Authentication successful."
echo "Creating application credential: ${CRED_NAME}"

OUTPUT=$(openstack application credential create \
  --description "${CRED_DESCRIPTION}" \
  --format json \
  "${CRED_NAME}")

APP_CRED_ID=$(echo "${OUTPUT}" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['id'])")
APP_CRED_SECRET=$(echo "${OUTPUT}" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['secret'])")

echo ""
echo "Application credential created successfully."
echo "  ID:     ${APP_CRED_ID}"
echo "  Secret: ${APP_CRED_SECRET}"
echo ""
echo "Add the following to your .env or CI/CD variables:"
echo "  OS_APPLICATION_CREDENTIAL_ID=${APP_CRED_ID}"
echo "  OS_APPLICATION_CREDENTIAL_SECRET=${APP_CRED_SECRET}"

if [[ -f "${SCRIPT_DIR}/.env" ]]; then
  if ! grep -q "OS_APPLICATION_CREDENTIAL_ID=" "${SCRIPT_DIR}/.env" || grep -q "OS_APPLICATION_CREDENTIAL_ID=$" "${SCRIPT_DIR}/.env"; then
    sed -i '' '/^OS_APPLICATION_CREDENTIAL_ID=/d' "${SCRIPT_DIR}/.env"
    sed -i '' '/^OS_APPLICATION_CREDENTIAL_SECRET=/d' "${SCRIPT_DIR}/.env"
    printf '\nOS_APPLICATION_CREDENTIAL_ID=%s\nOS_APPLICATION_CREDENTIAL_SECRET=%s\n' \
      "${APP_CRED_ID}" "${APP_CRED_SECRET}" >> "${SCRIPT_DIR}/.env"
    echo "Saved to .env"
  else
    echo "NOTE: OS_APPLICATION_CREDENTIAL_ID already in .env — not overwriting."
  fi
fi
