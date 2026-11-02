#!/usr/bin/env bash
# Install/update Pocket Orchestra as an unprivileged systemd --user service on Ubuntu 24.04.
# The only supported project location on CORE .100: /1tbdisk/muzikfed
# Run: cd /1tbdisk/muzikfed && bash scripts/install-core.sh
set -Eeuo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
EXPECTED_DIR="/1tbdisk/muzikfed"
# Refuse to install from an old checkout in $HOME or a random folder.
if [[ "$PROJECT_DIR" != "$EXPECTED_DIR" ]]; then
  echo "ERROR: install only from $EXPECTED_DIR (currently $PROJECT_DIR)." >&2
  exit 1
fi
SERVICE_NAME=pocket-orchestra.service
UV_BIN="$(command -v uv || true)"
# SSH non-interactive shells may not have ~/.local/bin on PATH.
if [[ -z "$UV_BIN" && -x "$HOME/.local/bin/uv" ]]; then UV_BIN="$HOME/.local/bin/uv"; fi
if [[ -z "$UV_BIN" && -x "$HOME/.cargo/bin/uv" ]]; then UV_BIN="$HOME/.cargo/bin/uv"; fi

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

if command -v ip >/dev/null && ! ip -o -4 addr show | awk '{print $4}' | cut -d/ -f1 | grep -Fxq "192.168.0.100"; then
  echo "WARNING: 192.168.0.100 is not assigned to a local interface; the web service cannot bind until it is." >&2
fi

## uv normally places .venv in the project; explicitly keep both venv and uv cache on the 2 TB disk.
export UV_PROJECT_ENVIRONMENT="$PROJECT_DIR/.venv"
export UV_CACHE_DIR="$PROJECT_DIR/.cache/uv"
mkdir -p "$UV_CACHE_DIR" "$PROJECT_DIR/outputs"
chmod 700 "$PROJECT_DIR/outputs" "$PROJECT_DIR/.cache"

cd "$PROJECT_DIR"
"$UV_BIN" sync --extra dev --python 3.12
"$UV_BIN" run pytest -q

# Generate a strong per-installation secret for the web Stop button.
# The token is never logged, committed to Git, or served by the API.
CONTROL_TOKEN_FILE="$PROJECT_DIR/.cache/admin-token"
if [[ -L "$CONTROL_TOKEN_FILE" ]]; then
  echo "ERROR: control token file is a symlink; refusing for safety." >&2
  exit 1
fi
if [[ ! -e "$CONTROL_TOKEN_FILE" ]]; then
  python3 - "$CONTROL_TOKEN_FILE" <<'PY'
import os
import pathlib
import secrets
import sys

path = pathlib.Path(sys.argv[1])
fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
with os.fdopen(fd, "w", encoding="utf-8") as out:
    out.write(secrets.token_urlsafe(32))
PY
  echo "Created a private web-control token: $CONTROL_TOKEN_FILE"
else
  [[ -f "$CONTROL_TOKEN_FILE" ]] || { echo "ERROR: invalid control token file." >&2; exit 1; }
  chmod 600 "$CONTROL_TOKEN_FILE"
  echo "Reusing existing private web-control token."
fi
USER_SYSTEMD_DIR="$HOME/.config/systemd/user"
mkdir -p "$USER_SYSTEMD_DIR"
cat > "$USER_SYSTEMD_DIR/$SERVICE_NAME" <<UNIT
[Unit]
Description=Pocket Orchestra on /1tbdisk/muzikfed
After=network.target

[Service]
Type=simple
WorkingDirectory=$PROJECT_DIR
ExecStart=$UV_BIN run --project $PROJECT_DIR pocket-orchestra
Environment=UV_PROJECT_ENVIRONMENT=$PROJECT_DIR/.venv
Environment=UV_CACHE_DIR=$PROJECT_DIR/.cache/uv
Environment=POCKET_ORCHESTRA_OUTPUT=$PROJECT_DIR/outputs
Environment=POCKET_ORCHESTRA_CONTROL_TOKEN_FILE=$PROJECT_DIR/.cache/admin-token
Environment=POCKET_ORCHESTRA_HOST=192.168.0.100
Environment=POCKET_ORCHESTRA_PORT=9095
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

Project, venv, uv cache and outputs: /1tbdisk/muzikfed
The user systemd service descriptor is stored under ~/.config/systemd/user/.
Web Stop button token: bash /1tbdisk/muzikfed/scripts/show-control-token.sh
Start/stop manually: bash scripts/start-core.sh / bash scripts/stop-core.sh
NEXT: Open http://192.168.0.100:9095 in the Acer browser over your existing VPN.
Health check on CORE: curl -fsS http://192.168.0.100:9095/api/health
Do NOT forward port 9095 to the public internet: v0.1 has no authentication.
TXT
