#!/usr/bin/env bash
# OPTIONAL: prepare ACE-Step 1.5 as a separate project on /1tbdisk/muzikfed.
# Never run during normal Pocket Orchestra updates.
set -Eeuo pipefail
BASE="/1tbdisk/muzikfed"
ENGINE="$BASE/engines/ACE-Step-1.5"
SOURCE="https://github.com/ace-step/ACE-Step-1.5.git"
UNIT="pocket-orchestra-ace.service"
if [[ "$(id -u)" -eq 0 ]]; then echo "Run as user, not root." >&2; exit 1; fi
[[ -d "$BASE/.git" ]] || { echo "CORE project not found at $BASE" >&2; exit 1; }
command -v git >/dev/null || { echo "git not installed" >&2; exit 1; }
UV="$(command -v uv || true)"
if [[ -z "$UV" && -x "$HOME/.local/bin/uv" ]]; then UV="$HOME/.local/bin/uv"; fi
[[ -n "$UV" ]] || { echo "uv missing" >&2; exit 1; }
if ! command -v nvidia-smi >/dev/null || ! nvidia-smi -L; then
  echo "NVIDIA GPU not ready: first confirm nvidia-smi works on CORE." >&2
  exit 1
fi
mkdir -p "$BASE/engines" "$BASE/.cache/huggingface" "$BASE/.cache/uv"
if [[ -e "$ENGINE" && ! -d "$ENGINE/.git" ]]; then
  echo "Existing non-Git folder at $ENGINE; refusing overwrite." >&2
  exit 1
fi
if [[ ! -e "$ENGINE" ]]; then
  git clone --depth 1 "$SOURCE" "$ENGINE"
else
  echo "ACE-Step checkout already exists. No automatic upgrade; review upstream separately."
fi
export HF_HOME="$BASE/.cache/huggingface"
export UV_CACHE_DIR="$BASE/.cache/uv"
cd "$ENGINE"
"$UV" sync --python 3.12
USER_UNITS="$HOME/.config/systemd/user"
mkdir -p "$USER_UNITS"
cat > "$USER_UNITS/$UNIT" <<EOF
[Unit]
Description=Optional local ACE-Step 1.5 vocal generator on CORE .100
After=network.target

[Service]
Type=simple
WorkingDirectory=$ENGINE
ExecStart=$UV run --project $ENGINE acestep-api
Environment=HF_HOME=$BASE/.cache/huggingface
Environment=UV_CACHE_DIR=$BASE/.cache/uv
Environment=ACESTEP_CHECKPOINTS_DIR=$ENGINE/checkpoints
Environment=ACESTEP_API_HOST=127.0.0.1
Environment=ACESTEP_API_PORT=8001
Environment=ACESTEP_INIT_LLM=auto
Environment=ACESTEP_CONFIG_PATH=acestep-v15-turbo
Environment=ACESTEP_LM_MODEL_PATH=acestep-5Hz-lm-0.6B
Environment=ACESTEP_OFFLOAD_TO_CPU=true
UMask=0077
NoNewPrivileges=true
PrivateTmp=true
Restart=no
RuntimeMaxSec=3600
RestartSec=10

[Install]
WantedBy=default.target
EOF
systemctl --user daemon-reload
systemctl --user disable "$UNIT" >/dev/null 2>&1 || true
echo "ACE-Step dependencies prepared on 2 TB disk. No model was started."
echo "Next: bash $BASE/scripts/start-ace-step.sh"
echo "Initial model download requires internet and free disk space; check progress in logs."
