#!/usr/bin/env bash
# START Pocket Orchestra on CORE .100.
set -Eeuo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec bash "$SCRIPT_DIR/service-core.sh" start
