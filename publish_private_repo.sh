#!/usr/bin/env bash
set -euo pipefail

# Usage:
#   ./publish_private_repo.sh git@github.com:<your-id>/<repo>.git
#   ./publish_private_repo.sh https://github.com/<your-id>/<repo>.git

REMOTE_URL="${1:-}"
if [ -z "$REMOTE_URL" ]; then
  echo "Usage: $0 <github-private-repo-url>"
  exit 1
fi

if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "Not a git repository"
  exit 1
fi

if git remote get-url origin >/dev/null 2>&1; then
  git remote set-url origin "$REMOTE_URL"
else
  git remote add origin "$REMOTE_URL"
fi

echo "Pushing main + collaboration branches..."
git push -u origin main
git push origin codex/backend-mainline codex/frontend-showcase codex/db-migration-postgres

echo "Done. Ensure this GitHub repository is PRIVATE."
