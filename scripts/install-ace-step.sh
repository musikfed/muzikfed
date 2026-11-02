#!/usr/bin/env bash
# Install the OFFICIAL, free ACE-Step 1.5 engine on Huananzhi CORE .100.
# All dependencies/checkpoints remain on /1tbdisk/muzikfed. NO public GPU/API port.
# Default: clone, install CUDA Python packages, download Turbo + small LM, install
# on-demand systemd user unit. Never enables automatic GPU loading at boot.
set -Eeuo pipefail

BASE="/1tbdisk/muzikfed"
ENGINE="$BASE/engines/ACE-Step-1.5"
SOURCE="https://github.com/ace-step/ACE-Step-1.5.git"
UNIT="pocket-orchestra-ace.service"
MODEL="acestep-v15-turbo"
LM_MODEL="acestep-5Hz-lm-0.6B"
DOWNLOAD=true
PREFLIGHT_ONLY=false

usage() {
  cat <<'HELP'
ACE-Step 1.5 installer on CORE .100 (RTX 3060 12GB, Ubuntu 24.04)
  bash scripts/install-ace-step.sh                  full install + download models
  bash scripts/install-ace-step.sh --preflight       check GPU/disk, don't change anything
  bash scripts/install-ace-step.sh --skip-download   dependencies/service only; model downloads on startup
  bash scripts/install-ace-step.sh --help            show this help
After install:
  bash scripts/start-ace-step.sh                     manual start (normally web button starts it)
  bash scripts/stop-ace-step.sh                      stop and release RTX
  curl -fsS http://127.0.0.1:8001/health            local API check when running
HELP
}

case "${1:-}" in
  "") ;;
  --preflight) PREFLIGHT_ONLY=true ;;
  --skip-download) DOWNLOAD=false ;;
  --help|-h) usage; exit 0 ;;
  *) usage >&2; exit 2 ;;
esac

die() { echo "ERROR: $*" >&2; exit 1; }
[[ "$(id -u)" -ne 0 ]] || die "Run as normal user, NEVER sudo bash."
[[ -d "$BASE/.git" ]] || die "Missing Pocket Orchestra checkout: $BASE"
[[ ! -L "$ENGINE" ]] || die "Refusing a symlinked engine directory."
command -v git >/dev/null || die "Install git first."
command -v nvidia-smi >/dev/null || die "NVIDIA driver not found; run nvidia-smi first."
GPU_INFO="$(nvidia-smi --query-gpu=name,memory.total --format=csv,noheader,nounits 2>/dev/null)" ||
  die "nvidia-smi failed. Check the NVIDIA driver before installing the AI engine."
[[ -n "$GPU_INFO" ]] || die "No CUDA GPU detected."
echo "NVIDIA GPU: $GPU_INFO"

# Give the model (roughly 10GB), Python/CUDA dependencies, and temporary files room.
FREE_KB="$(df -Pk "$BASE" | awk 'END {print $4}')"
[[ "$FREE_KB" =~ ^[0-9]+$ ]] || die "Could not check free space on /1tbdisk."
if (( FREE_KB < 20 * 1024 * 1024 )); then
  die "Need at least 20 GiB free on $BASE for the first install; available $((FREE_KB / 1024 / 1024)) GiB."
fi
echo "Disk free: $((FREE_KB / 1024 / 1024)) GiB on $BASE"

UV="$(command -v uv || true)"
if [[ -z "$UV" && -x "$HOME/.local/bin/uv" ]]; then UV="$HOME/.local/bin/uv"; fi
if [[ -z "$UV" && -x "$HOME/.cargo/bin/uv" ]]; then UV="$HOME/.cargo/bin/uv"; fi
[[ -n "$UV" ]] || die "uv not found. You already have uv 0.12.0 on CORE; check PATH."
echo "uv: $UV ($("$UV" --version))"
echo "ACE-Step source: $SOURCE"
echo "Engine directory: $ENGINE"
echo "DiT: $MODEL; language model: $LM_MODEL; download: $DOWNLOAD"
if [[ "$PREFLIGHT_ONLY" == true ]]; then
  echo "PREFLIGHT OK. No files downloaded, no systemd changes made."
  exit 0
fi

command -v systemctl >/dev/null || die "systemd is required for the on-demand web integration."
if systemctl --user is-active --quiet "$UNIT"; then
  die "$UNIT is running. First finish the song or run bash scripts/stop-ace-step.sh."
fi
mkdir -p "$BASE/engines" "$BASE/.cache/huggingface" "$BASE/.cache/uv" "$BASE/.cache/triton"
chmod 700 "$BASE/.cache"
if [[ -e "$ENGINE" && ! -d "$ENGINE/.git" ]]; then
  die "Existing non-Git folder at $ENGINE. Refusing overwrite."
fi
if [[ ! -e "$ENGINE" ]]; then
  git clone --depth 1 "$SOURCE" "$ENGINE"
else
  ORIGIN="$(git -C "$ENGINE" remote get-url origin || true)"
  case "$ORIGIN" in
    https://github.com/ace-step/ACE-Step-1.5.git|https://github.com/ACE-Step/ACE-Step-1.5.git|https://github.com/ace-step/ACE-Step-1.5|https://github.com/ACE-Step/ACE-Step-1.5)
      echo "Existing official ACE-Step checkout: no automatic upstream pull." ;;
    *) die "Unexpected engine Git remote: $ORIGIN" ;;
  esac
fi

export HF_HOME="$BASE/.cache/huggingface"
export UV_CACHE_DIR="$BASE/.cache/uv"
export TRITON_CACHE_DIR="$BASE/.cache/triton"
cd "$ENGINE"
echo "Installing official ACE-Step dependencies in its own .venv (Python 3.12)..."
"$UV" sync --python 3.12

echo "Checking CUDA from the isolated ACE-Step Python, not system Python..."
"$UV" run --no-sync python -c '
import torch
if not torch.cuda.is_available():
    raise SystemExit("ERROR: ACE-Step Python cannot use CUDA. Check PyTorch/CUDA installation.")
print("CUDA READY:", torch.cuda.get_device_name(0),
      "| PyTorch", torch.__version__, "| CUDA", torch.version.cuda)
'

if [[ "$DOWNLOAD" == true ]]; then
  echo "Downloading the official base Turbo weights to $ENGINE/checkpoints."
  echo "First download is several GB; interruptions are safe to retry."
  "$UV" run --no-sync acestep-download
  echo "Downloading the small 0.6B music language model for RTX 3060 12GB..."
  "$UV" run --no-sync acestep-download --model "$LM_MODEL"
else
  echo "Weights not downloaded (--skip-download). First service start may download several GB."
fi

USER_UNITS="$HOME/.config/systemd/user"
mkdir -p "$USER_UNITS"
cat > "$USER_UNITS/$UNIT" <<EOF
[Unit]
Description=ACE-Step 1.5 on-demand neural music on Huananzhi CORE
After=network.target

[Service]
Type=simple
WorkingDirectory=$ENGINE
ExecStart=$UV run --no-sync --project $ENGINE acestep-api
Environment=UV_CACHE_DIR=$BASE/.cache/uv
Environment=HF_HOME=$BASE/.cache/huggingface
Environment=TRITON_CACHE_DIR=$BASE/.cache/triton
Environment=ACESTEP_CHECKPOINTS_DIR=$ENGINE/checkpoints
Environment=ACESTEP_API_HOST=127.0.0.1
Environment=ACESTEP_API_PORT=8001
Environment=ACESTEP_CONFIG_PATH=$MODEL
Environment=ACESTEP_LM_MODEL_PATH=$LM_MODEL
Environment=ACESTEP_INIT_LLM=auto
Environment=ACESTEP_OFFLOAD_TO_CPU=true
UMask=0077
NoNewPrivileges=true
PrivateTmp=true
Restart=no
RuntimeMaxSec=3600

[Install]
WantedBy=default.target
EOF
systemctl --user daemon-reload
systemctl --user disable "$UNIT" >/dev/null 2>&1 || true
echo
echo "ACE-Step installed on disk. Service is DISABLED at boot: no reserved VRAM."
echo "Now check: bash $BASE/scripts/check-ace-step.sh"
echo "Manual start for first test: bash $BASE/scripts/start-ace-step.sh"
echo "Watch logs: journalctl --user -u $UNIT -f"
echo "Web: http://192.168.0.100:9095 (Ctrl+F5; audio buttons enabled)"
