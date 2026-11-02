#!/usr/bin/env bash
# Install/update Pocket Orchestra as an unprivileged systemd --user service on Ubuntu 24.04.
# Run from the repository root: bash scripts/install-core.sh
set -Eeuo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SERVICE_NAME=pocket-orchestra.service
UV_BIN="$(command -v uv || true)"

if [[ "$(id -u)" == 0 ]]; then
  echo 'ERROR: do not run this script as root; use your regular SSH user.' >&2
  exit 1
fi
if [[ -z "$UV_BIN" ]]; then
  echo 'ERROR: uv is not installed. Install uv from https://docs.astral.sh/uv/ then retry.' >&2
  exit 1
fi
if [[ ! -f "$PROJECT_DIR/pyproject.toml" ]]; then
  echo 'ERROR: missing pyproject.toml; run from a checked-out Pocket Orchestra repository.' >&2
  exit 1
fi

# Apt packages are optional: FastAPI works without them, but preview.wav does not.
if command -v apt-get >/dev/null && ! command -v fluidsynth >/dev/null; then
  echo 'FluidSynth is not installed. For an audio preview run:'
  echo '  sudo apt update && sudo apt install -y fluidsynth fluid-soundfont-gm'
fi

cd "$PROJECT_DIR"
"$UV_BIN" sync --extra dev --python 3.12
"$UV_BIN" run pytest -q
mkdir -p outputs
chmod 700 outputs

USER_SYSTEMD_DIR="$HOME/.config/systemd/user"
mkdir -p "$USER_SYSTEMD_DIR"
cat > "$USER_SYSTEMD_DIR/$SERVICE_NAME" <<UNIT
[Unit]
Description=Pocket Orchestra local composition server
After=network.target

[Service]
Type=simple
WorkingDirectory=$PROJECT_DIR
ExecStart=$UV_BIN run --project $PROJECT_DIR pocket-orchestra
Environment=POCKET_ORCHESTRA_HOST=127.0.0.1
Environment=POCKET_ORCHESTRA_PORT=8765
UMask=0077
NoNewPrivileges=true
PrivateTmp=true
Restart=on-failure
RestartSec=5

[Install]
WantedBy=default.target
UNIT

if systemctl --user daemon-reload && systemctl --user enable --now "$SERVICE_NAME"; then
  systemctl --user restart "$SERVICE_NAME"
  echo 'Pocket Orchestra service installed: systemctl --user status pocket-orchestra'
else
  echo 'WARNING: systemd --user is unavailable in this session.' >&2
  echo 'Manual launch: uv run pocket-orchestra' >&2
fi
cat <<'TXT'

NEXT: On the Acer Windows PowerShell, create a private SSH tunnel:
  ssh -N -L 8765:127.0.0.1:8765 USER@CORE_WIREGUARD_IP
Open http://127.0.0.1:8765 in the Acer browser.
Do NOT expose port 8765 on the public internet; no authentication in v0.1.
TXT
