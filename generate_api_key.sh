#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

CLOUDS_FILE="${1:-}"
CLOUD_NAME="${2:-}"
CRED_NAME="${3:-jumpbox-provision-cred}"

usage() {
  echo "Usage: bash generate_api_key.sh <clouds.yaml> <cloud-name> [credential-name]"
  echo "Example: bash generate_api_key.sh ~/Downloads/clouds.yaml mycloud jumpbox-provision-cred"
  exit 1
}

[[ -z "${CLOUDS_FILE}" ]] && usage
[[ -z "${CLOUD_NAME}" ]] && usage

if [[ ! -f "${CLOUDS_FILE}" ]]; then
  echo "ERROR: file not found: ${CLOUDS_FILE}"
  exit 1
fi

if ! command -v openstack &>/dev/null; then
  echo "ERROR: openstack CLI not found. Install with: pip install python-openstackclient" >&2
  exit 1
fi

export OS_CLIENT_CONFIG_FILE="${CLOUDS_FILE}"
export OS_CLOUD="${CLOUD_NAME}"

echo "Authenticating as cloud '${CLOUD_NAME}' from ${CLOUDS_FILE} ..."

if ! openstack token issue -f value -c id > /dev/null 2>&1; then
  echo ""
  echo "ERROR: Authentication failed."
  echo "  clouds.yaml: ${CLOUDS_FILE}"
  echo "  cloud name:  ${CLOUD_NAME}"
  echo ""
  echo "Check that '${CLOUD_NAME}' exists in the clouds.yaml and credentials are correct."
  echo "Run manually to see full error:"
  echo "  OS_CLIENT_CONFIG_FILE=${CLOUDS_FILE} OS_CLOUD=${CLOUD_NAME} openstack token issue"
  exit 1
fi

echo "Authentication successful."
echo "Creating application credential: ${CRED_NAME}"

OUTPUT=$(openstack application credential create \
  --description "Application credential for jumpbox VM provisioning" \
  --format json \
  "${CRED_NAME}")

APP_CRED_ID=$(echo "${OUTPUT}" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['id'])")
APP_CRED_SECRET=$(echo "${OUTPUT}" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['secret'])")

echo ""
echo "Application credential created successfully."
echo "  ID:     ${APP_CRED_ID}"
echo "  Secret: ${APP_CRED_SECRET}"
echo ""
echo "Add to your clouds.yaml under the cloud entry:"
cat <<EOF

    auth_type: v3applicationcredential
    auth:
      auth_url: <your-auth-url>
      application_credential_id: ${APP_CRED_ID}
      application_credential_secret: ${APP_CRED_SECRET}
EOF
