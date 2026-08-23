#!/bin/sh
set -eu

SERVICE="${AI_HORDE_KEYCHAIN_SERVICE:-perob.ai-horde}"
ACCOUNT="${AI_HORDE_KEYCHAIN_ACCOUNT:-api-key}"
SECURITY_BIN="/usr/bin/security"

if [ "$(uname -s)" != "Darwin" ] || [ ! -x "$SECURITY_BIN" ]; then
  printf '%s\n' "unsupported"
  exit 2
fi

case "${1:-status}" in
  set)
    if [ "$#" -ne 1 ]; then
      printf '%s\n' "usage: $0 set|status|delete" >&2
      exit 2
    fi
    "$SECURITY_BIN" add-generic-password -a "$ACCOUNT" -s "$SERVICE" -U -w
    printf '%s\n' "configured"
    ;;
  status)
    if [ "$#" -ne 1 ]; then
      printf '%s\n' "usage: $0 set|status|delete" >&2
      exit 2
    fi
    if "$SECURITY_BIN" find-generic-password -a "$ACCOUNT" -s "$SERVICE" >/dev/null 2>&1; then
      printf '%s\n' "configured"
    else
      printf '%s\n' "missing"
    fi
    ;;
  delete)
    if [ "$#" -ne 1 ]; then
      printf '%s\n' "usage: $0 set|status|delete" >&2
      exit 2
    fi
    printf '%s' "Delete the AI Horde credential? [y/N] " >&2
    IFS= read -r answer
    case "$answer" in
      y|Y|yes|YES)
        "$SECURITY_BIN" delete-generic-password -a "$ACCOUNT" -s "$SERVICE" >/dev/null
        printf '%s\n' "deleted"
        ;;
      *)
        printf '%s\n' "cancelled"
        ;;
    esac
    ;;
  *)
    printf '%s\n' "usage: $0 set|status|delete" >&2
    exit 2
    ;;
esac
