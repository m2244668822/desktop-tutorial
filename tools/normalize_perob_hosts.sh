#!/usr/bin/env bash
set -euo pipefail

HOSTS_FILE="/etc/hosts"
TMP_FILE="$(mktemp)"
trap 'rm -f "$TMP_FILE"' EXIT

awk '
  {
    keep = 1
    for (i = 2; i <= NF; i++) {
      if ($i == "perob.com") {
        keep = 0
      }
    }
    if (keep) {
      print
    }
  }
  END {
    print "127.0.0.1 perob.com"
  }
' "$HOSTS_FILE" > "$TMP_FILE"

if cmp -s "$HOSTS_FILE" "$TMP_FILE"; then
  echo "[ok] /etc/hosts already normalized"
  exit 0
fi

if sudo -n cp "$TMP_FILE" "$HOSTS_FILE" 2>/dev/null; then
  echo "[ok] normalized /etc/hosts: 127.0.0.1 perob.com"
  exit 0
fi

echo "[action required] run this once in Terminal:"
echo "  sudo cp '$TMP_FILE' '$HOSTS_FILE'"
echo
echo "Or apply the intended result manually:"
echo "  remove duplicate perob.com lines"
echo "  add: 127.0.0.1 perob.com"
trap - EXIT
echo "[info] prepared file preserved at: $TMP_FILE"
exit 2
