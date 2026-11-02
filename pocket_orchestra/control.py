"""Shutdown only the Pocket Orchestra user service from its VPN-only dashboard.

No passwords, keys or control tokens. The operator confirms in the browser.
Start again via SSH, because a stopped web application cannot accept requests.
Keep port 9095 reachable only from the trusted LAN/VPN.
"""
from __future__ import annotations

import secrets
import subprocess

from fastapi import APIRouter, HTTPException, Request

router = APIRouter()
SERVICE = "pocket-orchestra.service"


@router.post("/api/admin/stop", status_code=202)
def stop_service(request: Request):
    """Schedule a delayed stop+disable for just this user-systemd unit.

    Require a same-origin browser request to reduce cross-site shutdown attempts.
    No shell is involved and only the fixed unit name can be stopped.
    """
    if request.headers.get("origin") != str(request.base_url).rstrip("/"):
        raise HTTPException(status_code=403, detail="Запрос разрешён только из веб-пульта Pocket Orchestra")

    # Complete the HTTP response before the service shuts itself down.
    unit = "pocket-orchestra-web-stop-" + secrets.token_hex(5)
    command = [
        "systemd-run", "--user", "--quiet", "--collect", "--on-active=3s",
        "--unit=" + unit,
        "/usr/bin/systemctl", "--user", "disable", "--now", SERVICE,
    ]
    try:
        subprocess.run(command, capture_output=True, text=True, check=True, timeout=12)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as exc:
        raise HTTPException(
            status_code=503,
            detail="Не удалось запланировать остановку; по SSH: bash scripts/stop-core.sh",
        ) from exc

    return {
        "status": "stop_scheduled",
        "message": "Служба Pocket Orchestra будет остановлена, автозапуск выключен.",
        "restart": "bash /1tbdisk/muzikfed/scripts/start-core.sh",
    }
