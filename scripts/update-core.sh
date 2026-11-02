#!/usr/bin/env bash
# Run on CORE .100 after a new GitHub commit. Refuses local uncommitted modifications.
set -Eeuo pipefail
PROJECT_DIR="/1tbdisk/muzikfed"
if [[ ! -d "$PROJECT_DIR/.git" ]]; then
  echo "ERROR: no Git checkout at $PROJECT_DIR. First deploy using scripts/deploy-to-core.sh." >&2
  exit 1
fi
cd "$PROJECT_DIR"
if [[ -n "$(git status --porcelain --untracked-files=normal)" ]]; then
  echo 'ERROR: local changes detected; commit/stash them before updating.' >&2
  exit 1
fi
echo "== Pocket Orchestra: downloading latest main from GitHub =="
git pull --ff-only origin main
echo "== Installing dependencies, running checks and restarting user service =="
bash scripts/install-core.sh
echo "== Current installed git revision =="
git log -1 --oneline
echo "== Pocket Orchestra service =="
systemctl --user is-active pocket-orchestra.service || true
echo "== Web dashboard: http://192.168.0.100:9095 =="

