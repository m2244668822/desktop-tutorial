#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

ENV_FILE="$TMP_DIR/oci.env"
KEY_FILE="$TMP_DIR/test.key"
touch "$KEY_FILE"
chmod 600 "$KEY_FILE"

cat > "$ENV_FILE" <<EOF
OCI_USER=opc
OCI_IP=203.0.113.10
OCI_KEY_PATH=$KEY_FILE
OCI_REMOTE_DIR=/home/opc/agent_system
OCI_LOCAL_DIR=$TMP_DIR/project/
EOF

mkdir -p "$TMP_DIR/project"

output="$(OCI_ENV_FILE="$ENV_FILE" bash "$ROOT_DIR/deploy_to_oci.sh" --print-config)"

grep -q "OCI_USER=opc" <<< "$output"
grep -q "OCI_IP=203.0.113.10" <<< "$output"
grep -q "OCI_KEY_PATH=$KEY_FILE" <<< "$output"
grep -q "OCI_REMOTE_DIR=/home/opc/agent_system" <<< "$output"
grep -q "OCI_LOCAL_DIR=$TMP_DIR/project/" <<< "$output"
grep -q "OCI_SSH_STRICT_HOST_KEY_CHECKING=accept-new" <<< "$output"
grep -q "OCI_VERIFY_AFTER_SYNC=1" <<< "$output"
