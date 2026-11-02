#!/usr/bin/env bash
# Run from Acer WSL/Git Bash or another Linux machine:
#   bash scripts/deploy-to-core.sh user@192.168.0.100
# Deploys only to /1tbdisk/muzikfed on CORE .100 via SSH.
# Does not copy SSH keys, TLS certificates, passwords or WireGuard credentials.
set -Eeuo pipefail
if [[ $# -ne 1 || -z "$1" || "$1" == -* ]]; then
  echo 'Usage: bash scripts/deploy-to-core.sh USER@CORE_WIREGUARD_IP' >&2
  exit 2
fi
TARGET="$1"
ssh -o StrictHostKeyChecking=ask -- "$TARGET" 'bash -s' <<'REMOTE'
set -Eeuo pipefail
REPO='https://github.com/musikfed/muzikfed.git'
DEST="/1tbdisk/muzikfed"
# Never create /1tbdisk silently: the disk must already be mounted.
if [[ ! -d "/1tbdisk" ]]; then
  echo "ERROR: /1tbdisk does not exist. Check the 2 TB disk mount before deploying." >&2
  exit 1
fi
if command -v findmnt >/dev/null; then
  MOUNT_TARGET="$(findmnt -n -o TARGET -T /1tbdisk || true)"
  if [[ -z "$MOUNT_TARGET" || "$MOUNT_TARGET" == "/" ]]; then
    echo "ERROR: /1tbdisk appears to be on the root filesystem; check that the 2 TB disk is mounted." >&2
    exit 1
  fi
  echo "Destination filesystem mounted at: $MOUNT_TARGET"
fi
if [[ ! -w "/1tbdisk" && ! -w "$DEST" ]]; then
  echo "ERROR: user cannot write to /1tbdisk or $DEST. Check ownership/permissions." >&2
  echo "If $DEST does not exist, run ON CORE as your normal SSH user:" >&2
  echo '  sudo install -d -o "$(id -un)" -g "$(id -gn)" -m 755 /1tbdisk/muzikfed' >&2
  echo 'Do not chown/chmod the whole /1tbdisk or use sudo git clone.' >&2
  exit 1
fi
command -v git >/dev/null || { echo 'Please install git first: sudo apt install git'; exit 1; }
if [[ -e "$DEST" && ! -d "$DEST" ]]; then
  echo "ERROR: $DEST exists but is not a directory. Refusing to overwrite." >&2
  exit 1
fi
if [[ -d "$DEST/.git" ]]; then
  if [[ -n "$(git -C "$DEST" status --porcelain --untracked-files=normal)" ]]; then
    echo 'ERROR: uncommitted changes on server. Refusing to overwrite.' >&2
    exit 1
  fi
  REMOTE="$(git -C "$DEST" remote get-url origin || true)"
  case "$REMOTE" in
    "$REPO"|"https://github.com/musikfed/muzikfed"|"git@github.com:musikfed/muzikfed.git") ;;
    *) echo "ERROR: unexpected origin $REMOTE. Refusing to update another repository." >&2; exit 1 ;;
  esac
  git -C "$DEST" pull --ff-only origin main
elif [[ ! -e "$DEST" ]] || [[ -d "$DEST" && -z "$(find "$DEST" -mindepth 1 -maxdepth 1 -print -quit)" ]]; then
  # git clone safely accepts a pre-existing EMPTY destination directory.
  git clone --branch main "$REPO" "$DEST"
else
  echo "ERROR: $DEST exists and contains non-Git files. Refusing to overwrite them." >&2
  echo "Inspect: ls -la $DEST ; back up/organize those files before cloning." >&2
  exit 1
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
