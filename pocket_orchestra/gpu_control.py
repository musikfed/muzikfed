"""Single-RTX-3060 cooperative scheduler for Qwen/Ollama and ACE-Step.

The two independent AI engines are activated on request and not intentionally
kept resident together. File-backed ACE task lease is shared across API workers.
This does not control unrelated GPU programs on CORE.
"""
from __future__ import annotations

from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path
import subprocess
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / ".cache"
LEASE = RUNTIME / "gpu-audio-active.json"
LOCK = RUNTIME / "gpu-control.lock"
ACE_UNIT = "pocket-orchestra-ace.service"


@contextmanager
def _locked():
    RUNTIME.mkdir(parents=True, exist_ok=True)
    with LOCK.open("a+") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _active() -> dict | None:
    try:
        entry = json.loads(LEASE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if time.time() - entry.get("created", 0) > 7200:
        LEASE.unlink(missing_ok=True)
        return None
    return entry


def _unit_installed() -> bool:
    return (Path.home() / ".config/systemd/user" / ACE_UNIT).is_file()


def ace_installed() -> bool:
    return _unit_installed()


def _systemctl(*action: str, timeout: int = 20) -> None:
    result = subprocess.run(["systemctl", "--user", *action, ACE_UNIT],
                            capture_output=True, text=True, timeout=timeout)
    if result.returncode:
        raise RuntimeError(result.stderr.strip()[:220] or "systemd ACE-Step error")


def unload_ollama(model: str) -> None:
    """Best effort GPU unload. No effect if Ollama is already stopped."""
    data = json.dumps({"model": model, "keep_alive": 0, "stream": False}).encode()
    request = urllib.request.Request("http://127.0.0.1:11434/api/generate",
                                      data=data, method="POST",
                                      headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=15) as r:
            r.read(512)
    except (OSError, ValueError):
        pass


def before_score() -> None:
    """Do not start Qwen while ACE song job owns GPU."""
    with _locked():
        if _active():
            raise RuntimeError("RTX занята генерацией песни. Дождись WAV или останови ACE-Step.")
        if _unit_installed():
            _systemctl("stop")


def claim_audio(job_id: str, model: str = "qwen3:8b") -> None:
    with _locked():
        if _active():
            raise RuntimeError("RTX уже занята нейропесней. Дождись завершения.")
        unload_ollama(model)
        LEASE.write_text(json.dumps({"job_id": job_id, "created": time.time()}), encoding="utf-8")


def launch_audio() -> None:
    if not _unit_installed():
        raise RuntimeError("ACE-Step ещё не установлена. Выполни bash scripts/install-ace-step.sh.")
    _systemctl("start", timeout=90)


def release_audio(job_id: str) -> None:
    with _locked():
        active = _active()
        if active and active.get("job_id") == job_id:
            LEASE.unlink(missing_ok=True)
            if _unit_installed():
                try:
                    _systemctl("stop")
                except RuntimeError:
                    pass


def state() -> dict:
    with _locked():
        active = _active()
        return {
            "ace_installed": _unit_installed(), "audio_job_active": bool(active),
            "job_id": active.get("job_id") if active else None,
            "policy": "Сначала освобождаем RTX от Ollama, затем запускаем ACE-Step. После WAV останавливаем ACE-Step.",
        }
