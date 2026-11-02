#!/usr/bin/env bash
# Run on CORE .100 after a new GitHub commit. Refuses local uncommitted modifications.
set -Eeuo pipefail
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR"
if [[ -n "$(git status --porcelain --untracked-files=normal)" ]]; then
  echo 'ERROR: local changes detected; commit/stash them before updating.' >&2
  exit 1
fi
git pull --ff-only origin main
bash scripts/install-core.sh
