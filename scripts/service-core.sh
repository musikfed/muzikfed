#!/usr/bin/env bash
# Manage only the Pocket Orchestra user service on CORE .100.
# Usage: bash scripts/service-core.sh {start|stop|restart|status|logs}
# start: enable at user-session boot + start now; stop: disable + stop now.
# Does not affect Ollama, FluidSynth's own user unit, SSH, VPN or Ubuntu.
set -Eeuo pipefail
PROJECT="/1tbdisk/muzikfed"
SERVICE="pocket-orchestra.service"
ACTION="${1:-}"
if [[ "$(id -u)" -eq 0 ]]; then
  echo 'ERROR: run as the normal user (user), never via sudo bash.' >&2
  exit 1
fi
case "$ACTION" in
  start)
    [[ -f "$HOME/.config/systemd/user/$SERVICE" ]] || {
      echo "ERROR: unit not installed. Run bash $PROJECT/scripts/install-core.sh first." >&2; exit 1;
    }
    systemctl --user daemon-reload
    systemctl --user enable --now "$SERVICE"
    bash "$PROJECT/scripts/wait-core.sh"
    echo 'Web READY: http://192.168.0.100:9095'
    ;;
  stop)
    systemctl --user disable --now "$SERVICE"
    if systemctl --user is-active --quiet "$SERVICE"; then
      echo 'ERROR: Pocket Orchestra is still running; inspect user service logs.' >&2
      exit 1
    fi
    echo 'Pocket Orchestra stopped and disabled. Its files and outputs are untouched.'
    echo "Start again: bash $PROJECT/scripts/start-core.sh"
    ;;
  restart)
    systemctl --user restart "$SERVICE"
    bash "$PROJECT/scripts/wait-core.sh"
    echo 'Web READY: http://192.168.0.100:9095'
    ;;
  status)
    systemctl --user status "$SERVICE" --no-pager || true
    echo '---'
    systemctl --user is-enabled "$SERVICE" || true
    if systemctl --user is-active --quiet "$SERVICE"; then
      if ! curl --fail --silent --show-error --max-time 5 http://192.168.0.100:9095/api/health; then
        echo "WARNING: service active, but HTTP not responding; run bash $PROJECT/scripts/wait-core.sh" >&2
      fi
      echo
    fi
    ;;
  logs)
    journalctl --user -u "$SERVICE" -n 100 --no-pager
    ;;
  *)
    echo "Usage: bash $PROJECT/scripts/service-core.sh {start|stop|restart|status|logs}" >&2
    exit 2
    ;;
esac
