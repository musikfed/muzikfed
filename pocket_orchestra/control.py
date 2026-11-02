"""Authenticated user-service shutdown initiated by the web dashboard.

The API cannot start itself after shutdown. Starting requires SSH (start-core.sh).
The admin token lives in .cache/admin-token, never in the Git repository or HTML.
"""
from __future__ import annotations

import hmac
import os
import secrets
import subprocess
from pathlib import Path

from fastapi import APIRouter, Header, HTTPException, Request

router = APIRouter()
TOKEN_FILE = Path(os.environ.get(
    "POCKET_ORCHESTRA_CONTROL_TOKEN_FILE",
    str(Path(__file__).resolve().parent.parent / ".cache" / "admin-token"),
))
SERVICE = "pocket-orchestra.service"


@router.post("/api/admin/stop", status_code=202)
def stop_service(
    request: Request,
    x_pocket_control_token: str | None = Header(default=None),
):
    """Schedule an authenticated stop+disable using a detached user systemd timer.

    A timer is necessary so the HTTP response can complete before stopping its own
    systemd unit. We only invoke a fixed executable/argument vector, never a shell.
    """
    # Defense-in-depth against browser cross-site requests. Not a substitute for token.
    if request.headers.get("origin") != str(request.base_url).rstrip("/"):
        raise HTTPException(status_code=403, detail="Origin mismatch")
    try:
        expected = TOKEN_FILE.read_text(encoding="utf-8").strip()
    except OSError:
        raise HTTPException(
            status_code=503,
            detail="Код управления отсутствует; запусти bash scripts/install-core.sh на CORE",
        ) from None
    if not expected or not x_pocket_control_token or not hmac.compare_digest(
        expected, x_pocket_control_token
    ):
        raise HTTPException(status_code=403, detail="Неверный код управления")

    # systemd-run --on-active creates a timer outside the service being shut down.
    # This prevents killing the HTTP response before the browser receives it.
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
            detail="Не удалось запланировать остановку; воспользуйся bash scripts/stop-core.sh по SSH",
        ) from exc

    return {
        "status": "stop_scheduled",
        "message": "Остановка и отключение автозапуска службы запланированы через 3 сек.",
        "restart": "ssh user@192.168.0.100, затем bash /1tbdisk/muzikfed/scripts/start-core.sh",
    }
