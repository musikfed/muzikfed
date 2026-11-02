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
    systemctl --user is-active "$SERVICE"
    echo 'Web: http://192.168.0.100:9095'
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
    systemctl --user is-active "$SERVICE"
    echo 'Web: http://192.168.0.100:9095'
    ;;
  status)
    systemctl --user status "$SERVICE" --no-pager || true
    echo '---'
    systemctl --user is-enabled "$SERVICE" || true
    if systemctl --user is-active --quiet "$SERVICE"; then
      curl --fail --silent --show-error --max-time 8 http://192.168.0.100:9095/api/health || true
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
