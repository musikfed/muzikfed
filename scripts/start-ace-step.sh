#!/usr/bin/env bash
set -Eeuo pipefail
UNIT="pocket-orchestra-ace.service"
if [[ "$(id -u)" -eq 0 ]]; then echo "Run as normal user" >&2; exit 1; fi
[[ -f "$HOME/.config/systemd/user/$UNIT" ]] || {
  echo "First: bash /1tbdisk/muzikfed/scripts/install-ace-step.sh" >&2; exit 1;
}
systemctl --user disable "$UNIT" >/dev/null 2>&1 || true
systemctl --user start "$UNIT"
systemctl --user status "$UNIT" --no-pager || true
echo "ACE-Step starts only on demand, NOT at server boot; GPU is released after each completed job."
echo "ACE-Step startup (may download models): journalctl --user -u $UNIT -f"
echo "Local API only: curl http://127.0.0.1:8001/health"
