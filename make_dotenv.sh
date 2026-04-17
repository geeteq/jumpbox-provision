#!/usr/bin/env bash
# Copies clouds.yaml to the standard OpenStack config location for local use.
set -euo pipefail

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

DEST="${HOME}/.config/openstack/clouds.yaml"
mkdir -p "$(dirname "${DEST}")"

if [[ -f "${DEST}" ]]; then
  read -rp "${DEST} already exists — overwrite? [y/N] " confirm
  [[ "${confirm}" =~ ^[Yy]$ ]] || { echo "Aborted."; exit 0; }
fi

cp "${CLOUDS_FILE}" "${DEST}"
echo "clouds.yaml installed to ${DEST}"
echo ""
echo "Available clouds:"
python3 -c "import yaml; d=yaml.safe_load(open('${DEST}')); [print(' -', k) for k in d.get('clouds', {})]"
echo ""
echo "Set the cloud name in config.yaml under the 'cloud:' key."
