#!/usr/bin/env bash
# Read-only diagnostics for a running Pocket Orchestra installation on CORE .100.
# Does not install packages, restart services, edit files or access private keys.
set -Eeuo pipefail

PROJECT_DIR="/1tbdisk/muzikfed"
DASHBOARD="http://192.168.0.100:9095"
errors=0

ok()   { printf '[OK] %s\n' "$1"; }
warn() { printf '[WARN] %s\n' "$1"; }
fail() { printf '[FAIL] %s\n' "$1" >&2; errors=$((errors + 1)); }

echo "Pocket Orchestra — CORE .100 diagnostics"
echo "Project: $PROJECT_DIR"
echo "Dashboard: $DASHBOARD"
echo

if [[ ! -d "$PROJECT_DIR/.git" ]]; then
  fail "Git checkout not found at $PROJECT_DIR"
else
  ok "Git checkout found"
  git -C "$PROJECT_DIR" log -1 --format='Last commit: %h %s'
  if [[ -n "$(git -C "$PROJECT_DIR" status --porcelain --untracked-files=normal)" ]]; then
    warn "Local uncommitted changes found; update-core.sh will refuse to overwrite them"
  else
    ok "Working tree is clean"
  fi
fi

if command -v findmnt >/dev/null 2>&1; then
  mount_target="$(findmnt -n -o TARGET -T "$PROJECT_DIR" || true)"
  if [[ -n "$mount_target" && "$mount_target" != "/" ]]; then
    ok "Project filesystem mounted at $mount_target"
    findmnt -n -o TARGET,SOURCE,FSTYPE -T "$PROJECT_DIR"
  else
    fail "Project is on root filesystem or /1tbdisk is not mounted"
  fi
else
  warn "findmnt not found; cannot confirm disk mount"
fi

for folder in .venv .cache/uv outputs; do
  if [[ -d "$PROJECT_DIR/$folder" ]]; then
    ok "$folder exists on project disk"
  else
    fail "$folder missing from $PROJECT_DIR"
  fi
done

if systemctl --user is-active --quiet pocket-orchestra.service; then
  ok "systemd user service is active"
else
  fail "systemd user service not active"
  echo "Hint: systemctl --user status pocket-orchestra --no-pager"
fi

if command -v curl >/dev/null 2>&1; then
  if health_json="$(curl -fsS --connect-timeout 3 --max-time 10 "$DASHBOARD/api/health")"; then
    if printf '%s' "$health_json" | python3 -c 'import json,sys; data=json.load(sys.stdin); sys.exit(0 if data.get("status") == "ok" else 1)' >/dev/null 2>&1; then
      ok "API health reports status=ok"
      printf 'Health: %s\n' "$health_json"
      if printf '%s' "$health_json" | python3 -c 'import json,sys; sys.exit(0 if json.load(sys.stdin).get("renderer") is True else 1)' >/dev/null 2>&1; then
        ok "FluidSynth and SoundFont detected"
      else
        warn "Renderer not ready: check fluidsynth and soundfont"
      fi
    else
      fail "Unexpected API health response: $health_json"
    fi
  else
    fail "Cannot connect to $DASHBOARD/api/health"
  fi
else
  fail "curl is not installed"
fi

echo
if ((errors == 0)); then
  echo "Diagnostics: OK (no blocking failures)."
  echo "Check the dashboard from Acer over VPN: $DASHBOARD"
else
  printf 'Diagnostics: %d blocking issue(s).\n' "$errors" >&2
  exit 1
fi
