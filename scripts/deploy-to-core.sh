#!/usr/bin/env bash
# Run from Acer WSL/Git Bash or another Linux machine:
#   bash scripts/deploy-to-core.sh user@192.168.0.100
# Deploys exclusively through SSH; no password, key, cert or VPN config is uploaded to GitHub.
set -Eeuo pipefail
if [[ $# -ne 1 || -z "$1" || "$1" == -* ]]; then
  echo 'Usage: bash scripts/deploy-to-core.sh USER@CORE_WIREGUARD_IP' >&2
  exit 2
fi
TARGET="$1"
ssh -o StrictHostKeyChecking=ask -- "$TARGET" 'bash -s' <<'REMOTE'
set -Eeuo pipefail
REPO='https://github.com/musikfed/muzikfed.git'
DEST="$HOME/pocket-orchestra"
command -v git >/dev/null || { echo 'Please install git first: sudo apt install git'; exit 1; }
if [[ -e "$DEST" && ! -d "$DEST/.git" ]]; then
  echo "ERROR: existing $DEST is not a git checkout; refusing to overwrite." >&2
  exit 1
fi
if [[ ! -d "$DEST/.git" ]]; then
  git clone --branch main "$REPO" "$DEST"
else
  if [[ -n "$(git -C "$DEST" status --porcelain --untracked-files=normal)" ]]; then
    echo 'ERROR: uncommitted changes on server. Refusing to overwrite.' >&2
    exit 1
  fi
  if [[ "$(git -C "$DEST" remote get-url origin)" != "$REPO" ]]; then
    echo 'ERROR: unexpected origin. Refusing to update another repository.' >&2
    exit 1
  fi
  git -C "$DEST" pull --ff-only origin main
fi
cd "$DEST"
bash scripts/install-core.sh
printf '\nDeployed commit: '
git rev-parse --short HEAD
echo 'Dashboard over LAN/WireGuard: http://192.168.0.100:9095'
if command -v curl >/dev/null; then
  if ! curl -fsS --max-time 5 http://192.168.0.100:9095/api/health; then
    echo 'WARNING: web service is not reachable yet; inspect systemctl --user status pocket-orchestra and journalctl --user -u pocket-orchestra.' >&2
  fi
fi
REMOTE
