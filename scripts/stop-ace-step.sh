#!/usr/bin/env bash
set -Eeuo pipefail
if [[ "$(id -u)" -eq 0 ]]; then echo "Run as normal user" >&2; exit 1; fi
systemctl --user disable --now pocket-orchestra-ace.service
echo "ACE-Step stopped; Pocket Orchestra and saved scores untouched."
