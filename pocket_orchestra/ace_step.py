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

from .hybrid import build_payload

URL = "http://127.0.0.1:8001"
MAX_DOWNLOAD = 64 * 1024 * 1024  # MP3 up to 10min; keep strict cap
RESULT_NAME = "neural_song.mp3"


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


def start(job_dir: Path, mode: str = "original") -> dict:
    """Submit original neural music or a score-guided 'cover' of MIDI-rendered WAV.

    No fake lyrics or hidden replacement scores; explicitly declare the mode.
    """
    if (job_dir / "neural_task.json").exists():
        raise ValueError("Для этого произведения нейрозадача уже запускалась; сделай новую вариацию")
    payload, note = build_payload(job_dir, mode)
    response = _request("/release_task", payload, timeout=30)
    task = (response.get("data") or {}).get("task_id")
    if not isinstance(task, str) or not 8 <= len(task) <= 128:
        raise ValueError("ACE-Step не вернул task_id")
    cfg = json.loads((job_dir / "report.json").read_text(encoding="utf-8"))["composition"]["config"]
    solo = cfg.get("ensemble") == "choir"
    info = {
        "task_id": task, "generation_mode": mode,
        "audio_mode": "a_cappella_requested" if solo else
                      "instrumental" if "choir" not in cfg.get("ensemble", "") else "song_with_arrangement",
        "note": note,
    }
    (job_dir / "neural_task.json").write_text(
        json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return {"state": "queued", **info}


def poll(job_dir: Path, *, download: bool = True) -> dict:
    """Read ACE-Step result and download one validated locally hosted MP3."""
    if (job_dir / RESULT_NAME).is_file():
        return {"state": "complete", "url_ready": True}
    error_file = job_dir / "neural_error.json"
    if error_file.is_file():
        try:
            error = json.loads(error_file.read_text(encoding="utf-8"))
            message = str(error.get("message", "Ошибка ACE-Step"))[:400]
        except (OSError, ValueError, AttributeError):
            message = "Ошибка ACE-Step: смотри журнал pocket-orchestra"
        return {"state": "failed", "url_ready": False, "message": message}
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
        detail = row.get("error") or row.get("message") or row.get("result")
        detail = str(detail)[:240] if detail else "проверь журнал ACE-Step"
        return {"state": "failed", "message": "ACE-Step отклонила задачу: " + detail,
                "url_ready": False}
    if state != 1:
        return {"state": "working", "url_ready": False}
    if not download:
        # API status checks only; the server-side watcher is the sole WAV downloader.
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
    target = job_dir / RESULT_NAME
    temp = job_dir / "neural_song.pending"
    # Download directly as MP3: no intermediate AI WAV, no ffmpeg requirement.
    # Stream to disk instead of loading a long song into RAM.
    try:
        with urllib.request.urlopen(request, timeout=60) as stream, temp.open("wb") as sink:
            header = stream.read(10)
            if not (header.startswith(b"ID3") or (
                len(header) >= 2 and header[0] == 0xFF and header[1] & 0xE0 == 0xE0
            )):
                raise ValueError("ACE-Step вернул не MP3; проверь audio_format модели")
            sink.write(header)
            size = len(header)
            while chunk := stream.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_DOWNLOAD:
                    raise ValueError("Слишком большой MP3 от ACE-Step (макс. 64 МиБ)")
                sink.write(chunk)
        os.replace(temp, target)
        # Temporary MIDI/FluidSynth guide is needed only during cover; remove
        # it AFTER MP3 completed. Keep score.mid / MusicXML for editing.
        task_data = json.loads(task_path.read_text(encoding="utf-8"))
        if task_data.get("generation_mode") == "guided":
            (job_dir / "preview.wav").unlink(missing_ok=True)
    finally:
        temp.unlink(missing_ok=True)
    # In description-only mode the real ACE-Step LM can write the lyrics.
    # Save the ACTUAL text returned by the model; never substitute hardcoded verses.
    if not (job_dir / "lyrics.txt").exists() and isinstance(result[0], dict):
        generated = result[0].get("lyrics")
        if (isinstance(generated, str) and 0 < len(generated) <= 12000
                and generated.strip() not in ("[Instrumental]", "instrumental")):
            (job_dir / "lyrics.txt").write_text(generated.strip() + "\n", encoding="utf-8")
    return {"state": "complete", "url_ready": True}
