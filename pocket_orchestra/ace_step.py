"""Optional local ACE-Step 1.5 REST bridge; no package or GPU dependency.

The singing model must be installed separately and bound to 127.0.0.1:8001.
It generates an *independent* AI audio interpretation of a lyric+style brief;
there is NO MIDI alignment or guaranteed isolated voice stem in this mode.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import urllib.error
import urllib.parse
import urllib.request

URL = "http://127.0.0.1:8001"
MAX_DOWNLOAD = 120 * 1024 * 1024
RESULT_NAME = "neural_song.wav"


def _request(path: str, payload: dict | None = None, timeout: float = 10) -> dict:
    if not path.startswith("/") or path.startswith("//"):
        raise ValueError("Invalid ACE-Step path")
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(
        URL + path, data=data,
        method="POST" if payload is not None else "GET",
        headers={"Content-Type": "application/json"} if payload is not None else {},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        obj = json.loads(r.read(2_000_000))
    if not isinstance(obj, dict):
        raise ValueError("Invalid ACE-Step response")
    return obj


def status() -> dict:
    try:
        _request("/health", timeout=2)
        return {"available": True, "message": "ACE-Step отвечает локально, модель может загружаться отдельно"}
    except (OSError, ValueError, urllib.error.URLError) as err:
        return {"available": False, "message": "ACE-Step на CORE не запущен; требуется отдельная установка."}


def start(job_dir: Path) -> dict:
    """Submit a song generated from the existing notation job and its lyrics."""
    report = json.loads((job_dir / "report.json").read_text(encoding="utf-8"))
    cfg = report["composition"]["config"]
    lyric_file = job_dir / "lyrics.txt"
    if not lyric_file.is_file():
        raise ValueError("Для нейропения сначала создай нотный хоровой проект с текстом")
    lyrics = lyric_file.read_text(encoding="utf-8").strip()
    if not lyrics:
        raise ValueError("Пустой текст песни")
    if (job_dir / "neural_task.json").exists():
        raise ValueError("Нейрозадача для этого произведения уже запущена")

    style = cfg.get("style", "auto")
    if style == "auto":
        style = report["composition"].get("planning", {}).get("resolved_style", "cinematic")
    solo = cfg.get("ensemble") == "choir"
    context = ("Russian solo operatic singer, expressive aria, a cappella, no instruments"
               if solo else
               "Russian expressive operatic lead vocal with symphonic orchestra, emotional cinematic arrangement")
    description = f"{context}. Musical style: {style}. Subject: {cfg['prompt'][:700]}"
    seconds = max(10, min(600, round(cfg["bars"] * 4 * 60 / cfg["tempo"])))
    response = _request("/release_task", {
        "prompt": description, "lyrics": lyrics,
        "vocal_language": "ru", "audio_format": "wav",
        "audio_duration": seconds, "thinking": True,
    }, timeout=30)
    task = (response.get("data") or {}).get("task_id")
    if not isinstance(task, str) or not 8 <= len(task) <= 128:
        raise ValueError("ACE-Step не вернул task_id")
    info = {"task_id": task, "audio_mode": "a_cappella_requested" if solo else "song_with_arrangement",
            "note": "Нейрозвук самостоятельный: не совпадает точно с MIDI, изолированные WAV-стемы не гарантируются"}
    (job_dir / "neural_task.json").write_text(json.dumps(info, ensure_ascii=False), encoding="utf-8")
    return {"state": "queued", **info}


def poll(job_dir: Path) -> dict:
    """Read ACE-Step result and download one validated locally hosted WAV."""
    if (job_dir / RESULT_NAME).is_file():
        return {"state": "complete", "url_ready": True}
    task_path = job_dir / "neural_task.json"
    if not task_path.is_file():
        raise ValueError("Нейрозадача ещё не запущена")
    info = json.loads(task_path.read_text(encoding="utf-8"))
    data = _request("/query_result", {"task_id_list": [info["task_id"]]}, timeout=12)
    records = data.get("data") or []
    if not records or not isinstance(records, list):
        return {"state": "working", "url_ready": False}
    row = records[0]
    state = row.get("status")
    if state == 2:
        return {"state": "failed", "message": "ACE-Step сообщил об ошибке генерации", "url_ready": False}
    if state != 1:
        return {"state": "working", "url_ready": False}
    result = row.get("result")
    if isinstance(result, str):
        result = json.loads(result)
    if not isinstance(result, list) or not result:
        raise ValueError("ACE-Step завершил работу без ссылки на аудио")
    audio_path = result[0].get("file") if isinstance(result[0], dict) else None
    if not isinstance(audio_path, str):
        raise ValueError("ACE-Step не вернул путь к аудио")
    parts = urllib.parse.urlsplit(audio_path)
    # Never accept absolute URLs, other ports, file:// or unrelated API paths.
    if parts.scheme or parts.netloc or parts.path != "/v1/audio":
        raise ValueError("Небезопасный путь загрузки аудио от ACE-Step")
    if "path" not in urllib.parse.parse_qs(parts.query):
        raise ValueError("ACE-Step не указал путь к аудиофайлу")
    request = urllib.request.Request(URL + audio_path)
    with urllib.request.urlopen(request, timeout=35) as stream:
        audio = stream.read(MAX_DOWNLOAD + 1)
    if len(audio) > MAX_DOWNLOAD:
        raise ValueError("Слишком большой WAV от ACE-Step")
    if not (audio.startswith(b"RIFF") and audio[8:12] == b"WAVE"):
        raise ValueError("ACE-Step вернул не WAV; проверь audio_format и конфигурацию модели")
    target = job_dir / RESULT_NAME
    temp = job_dir / "neural_song.pending"
    temp.write_bytes(audio)
    os.replace(temp, target)
    return {"state": "complete", "url_ready": True}
