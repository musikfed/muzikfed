#!/usr/bin/env bash
# Diagnose actual GPU, installed weights and API without downloading anything.
set -Eeuo pipefail
BASE=/1tbdisk/muzikfed
ENGINE="$BASE/engines/ACE-Step-1.5"
UNIT=pocket-orchestra-ace.service
HEALTH=http://127.0.0.1:8001/health
[[ "$(id -u)" -ne 0 ]] || { echo "Run as regular user, not sudo." >&2; exit 1; }
command -v nvidia-smi >/dev/null || { echo "NVIDIA driver missing." >&2; exit 1; }
nvidia-smi --query-gpu=name,memory.total,memory.used,utilization.gpu --format=csv,noheader
if [[ ! -d "$ENGINE/.git" ]]; then
  echo "ACE-Step missing: bash $BASE/scripts/install-ace-step.sh"
  exit 2
fi
if [[ ! -f "$HOME/.config/systemd/user/$UNIT" ]]; then
  echo "ACE-Step checkout exists, but service missing: run the installer again."
  exit 2
fi
echo "Engine: $ENGINE"
echo "Latest upstream commit: $(git -C "$ENGINE" log -1 --format='%h %cs')"
if [[ -d "$ENGINE/checkpoints" ]]; then
  echo "Checkpoint data:"
  du -sh "$ENGINE/checkpoints" || true
else
  echo "No checkpoint directory detected: first install may be incomplete."
fi
if systemctl --user is-active --quiet "$UNIT"; then
  echo "ACE-Step systemd: ACTIVE"
  if curl --fail --silent --show-error --max-time 8 "$HEALTH"; then
    echo
    echo "LOCAL REST API READY: $HEALTH"
  else
    echo "Service started, but REST API is not ready yet. Read logs:" >&2
    echo "journalctl --user -u $UNIT -f" >&2
    exit 3
  fi
else
  echo "ACE-Step systemd: STOPPED (normal on-demand mode; RTX released)."
  echo "Start manually: bash $BASE/scripts/start-ace-step.sh"
fi
echo "Unit auto-boot: $(systemctl --user is-enabled "$UNIT" 2>/dev/null || true)"
echo "Web dashboard: http://192.168.0.100:9095"
