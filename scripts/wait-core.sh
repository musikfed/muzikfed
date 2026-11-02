#!/usr/bin/env bash
# Wait until uvicorn is actually accepting HTTP on CORE .100; systemd "active" alone is too early.
set -Eeuo pipefail
URL="${POCKET_ORCHESTRA_HEALTH_URL:-http://192.168.0.100:9095/api/health}"
SERVICE=pocket-orchestra.service
for attempt in {1..40}; do
  if curl --fail --silent --show-error --max-time 2 "$URL" >/dev/null 2>&1; then
    echo "READY: $URL (attempt $attempt/40)"
    exit 0
  fi
  if ! systemctl --user is-active --quiet "$SERVICE"; then
    echo "ERROR: $SERVICE stopped before the HTTP endpoint was ready." >&2
    journalctl --user -u "$SERVICE" -n 35 --no-pager >&2 || true
    exit 1
  fi
  sleep 0.5
done
echo "ERROR: Pocket Orchestra did not answer its HTTP health endpoint within the readiness window: $URL" >&2
systemctl --user status "$SERVICE" --no-pager >&2 || true
journalctl --user -u "$SERVICE" -n 45 --no-pager >&2 || true
exit 1
