#!/usr/bin/env bash
set -Eeuo pipefail
if [[ "$(id -u)" -eq 0 ]]; then echo "Run as normal user" >&2; exit 1; fi
systemctl --user disable --now pocket-orchestra-ace.service
rm -f /1tbdisk/muzikfed/.cache/gpu-audio-active.json
echo "ACE-Step stopped and pending GPU lease cleared; Pocket Orchestra and saved scores untouched."
