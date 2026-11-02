#!/usr/bin/env bash
# Reveal the locally generated web Stop control token to the authenticated SSH user.
# Keep this token private. Never paste it in chat, logs, README or git commits.
set -Eeuo pipefail
TOKEN="/1tbdisk/muzikfed/.cache/admin-token"
if [[ ! -f "$TOKEN" ]]; then
  echo "Control token not found. Run: cd /1tbdisk/muzikfed && bash scripts/install-core.sh" >&2
  exit 1
fi
echo 'Token for Pocket Orchestra Stop button (keep private):'
cat "$TOKEN"
echo
