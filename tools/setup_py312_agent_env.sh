#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROFILE="${1:-ci}"
VENV_DIR="${TREVOR_VENV_DIR:-$ROOT_DIR/.venv312}"

case "$PROFILE" in
  ci)
    REQUIREMENTS="$ROOT_DIR/requirements-ci.lock"
    ;;
  runtime)
    REQUIREMENTS="$ROOT_DIR/requirements.txt"
    ;;
  *)
    echo "usage: $0 [ci|runtime]" >&2
    exit 2
    ;;
esac

if ! command -v uv >/dev/null 2>&1; then
  echo "uv is required: https://docs.astral.sh/uv/" >&2
  exit 1
fi

uv python find 3.12 >/dev/null 2>&1 || uv python install 3.12
uv venv --python 3.12 --clear "$VENV_DIR"
uv pip sync --python "$VENV_DIR/bin/python" "$REQUIREMENTS"
"$VENV_DIR/bin/python" --version
