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

# One-time cleanup of the old shutdown-token mechanism (removed).
# Only this known generated regular file is deleted; no other cache files.
LEGACY_CONTROL_FILE="$PROJECT_DIR/.cache/admin-token"
if [[ -f "$LEGACY_CONTROL_FILE" && ! -L "$LEGACY_CONTROL_FILE" ]]; then
  rm -- "$LEGACY_CONTROL_FILE"
  echo "Removed obsolete Pocket Orchestra control token."
fi

cd "$PROJECT_DIR"
"$UV_BIN" sync --extra dev --python 3.12
"$UV_BIN" run pytest -q

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
Start/stop manually: bash scripts/start-core.sh / bash scripts/stop-core.sh
NEXT: Open http://192.168.0.100:9095 in the Acer browser over your existing VPN.
Health check on CORE: curl -fsS http://192.168.0.100:9095/api/health
Do NOT forward port 9095 to the public internet: v0.1 has no authentication.
TXT
