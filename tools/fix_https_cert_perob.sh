#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "[1/6] stop perob stack"
bash tools/manage_perob_stack.sh stop || true

echo "[2/6] remove old perob.com certs from login keychain"
for _ in 1 2 3 4 5; do
  security delete-certificate -c perob.com "$HOME/Library/Keychains/login.keychain-db" >/dev/null 2>&1 || true
done

mkdir -p certs
cat > certs/openssl_perob.cnf <<'EOF'
[ req ]
default_bits       = 2048
prompt             = no
default_md         = sha256
x509_extensions    = v3_req
distinguished_name = dn

[ dn ]
CN = perob.com

[ v3_req ]
subjectAltName = @alt_names
basicConstraints = critical,CA:false
keyUsage = critical,digitalSignature,keyEncipherment
extendedKeyUsage = serverAuth

[ alt_names ]
DNS.1 = perob.com
DNS.2 = localhost
IP.1 = 127.0.0.1
IP.2 = 172.20.10.2
EOF

echo "[3/6] regenerate local-https certificate"
openssl req -x509 -nodes -days 825 -newkey rsa:2048 \
  -keyout certs/local-https.key \
  -out certs/local-https.crt \
  -config certs/openssl_perob.cnf

echo "[4/6] trust certificate in macOS login keychain (may prompt for password)"
security add-trusted-cert -d -r trustRoot \
  -k "$HOME/Library/Keychains/login.keychain-db" \
  certs/local-https.crt

echo "[5/6] start perob stack"
bash tools/manage_perob_stack.sh start

echo "[6/6] verify"
openssl x509 -in certs/local-https.crt -noout -subject -issuer -ext subjectAltName
curl -sS --connect-timeout 5 --resolve perob.com:5443:127.0.0.1 https://perob.com:5443/status || true

echo "done. open https://perob.com:5443/Perob in Chrome and re-check trust state"
