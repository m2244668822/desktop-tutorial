#!/usr/bin/env bash
set -euo pipefail

# OCI SSH 連線測試（加固版）

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEFAULT_ENV_FILE="$SCRIPT_DIR/.env.oci"
OCI_ENV_FILE="${OCI_ENV_FILE:-$DEFAULT_ENV_FILE}"

usage() {
    cat <<'EOF'
用法:
  ./test_oci_connection.sh [--from-env] [--help]

選項:
  --from-env  從 .env.oci / OCI_ENV_FILE 載入 OCI_USER/OCI_IP/OCI_KEY_PATH
EOF
}

load_env_file() {
    local env_file="$1"
    if [ -f "$env_file" ]; then
        set -a
        # shellcheck disable=SC1090
        source "$env_file"
        set +a
    fi
}

FROM_ENV=0
for arg in "$@"; do
    case "$arg" in
        --from-env)
            FROM_ENV=1
            ;;
        --help|-h)
            usage
            exit 0
            ;;
        *)
            echo "未知參數: $arg"
            usage
            exit 2
            ;;
    esac
done

if [ "$FROM_ENV" -eq 1 ]; then
    load_env_file "$OCI_ENV_FILE"
fi

OCI_IP="${OCI_IP:-}"
OCI_KEY="${OCI_KEY_PATH:-}"
OCI_USER="${OCI_USER:-opc}"
SSH_STRICT="${OCI_SSH_STRICT_HOST_KEY_CHECKING:-accept-new}"
KNOWN_HOSTS_FILE="${OCI_SSH_USER_KNOWN_HOSTS_FILE:-$HOME/.ssh/known_hosts}"

if [ -z "$OCI_IP" ]; then
    read -r -p "請輸入 OCI 伺服器 IP: " OCI_IP
fi
if [ -z "$OCI_KEY" ]; then
    read -r -p "請輸入私鑰路徑 (例如 ~/.ssh/oci.key): " OCI_KEY
fi
if [ -z "${OCI_USER:-}" ]; then
    read -r -p "請輸入用戶名 (預設 opc): " OCI_USER
    OCI_USER="${OCI_USER:-opc}"
fi

echo "------------------------------------------------"
echo "正在測試連線到 $OCI_USER@$OCI_IP ..."
echo "------------------------------------------------"

if [ ! -f "$OCI_KEY" ]; then
    echo "連線失敗：找不到私鑰檔案 $OCI_KEY"
    exit 1
fi

set +e
ssh \
    -i "$OCI_KEY" \
    -o IdentitiesOnly=yes \
    -o BatchMode=yes \
    -o ConnectTimeout=8 \
    -o "StrictHostKeyChecking=$SSH_STRICT" \
    -o "UserKnownHostsFile=$KNOWN_HOSTS_FILE" \
    "$OCI_USER@$OCI_IP" \
    "echo CONNECTED && uname -a && uptime"
rc=$?
set -e

if [ "$rc" -eq 0 ]; then
    echo "------------------------------------------------"
    echo "連線成功：OCI SSH 已就緒。"
    echo "下一步可執行：./deploy_to_oci.sh --preflight-only"
else
    echo "------------------------------------------------"
    echo "連線失敗（exit=$rc），請檢查："
    echo "1. OCI_USER / OCI_IP / 私鑰是否正確"
    echo "2. 安全性清單是否開啟 22/TCP"
    echo "3. 若在 Cloud Shell，私鑰需先上傳到 ~/.ssh/"
    exit "$rc"
fi
