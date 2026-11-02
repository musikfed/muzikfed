"""FastAPI control desk for CORE .100; keep this unauthenticated API inside trusted LAN/VPN."""
from __future__ import annotations
import json
import os
import shutil
import subprocess
import uuid
from pathlib import Path
from dataclasses import asdict
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, FileResponse
from pydantic import BaseModel
from .composer import Config, compose, Piece
from .export import write_midi, write_musicxml
from .quality import inspect
from .harmony import optimize_satb
from .ollama import generate_plan, generate_lyrics
from .lyrics import draft_lyrics, annotate_score_lyrics
from . import ace_step, gpu_control
from .ai_score import generate_counterpoint, apply_counterpoint
from .control import router as control_router
from .monitor import collect_metrics
from .engines import ollama_status

ROOT = Path(__file__).resolve().parent.parent
OUTPUTS = Path(os.environ.get("POCKET_ORCHESTRA_OUTPUT", str(ROOT / "outputs"))).resolve()
OUTPUTS.mkdir(parents=True, exist_ok=True)
SOUNDFONT = Path(os.environ.get("POCKET_ORCHESTRA_SF2", "/usr/share/sounds/sf2/FluidR3_GM.sf2"))
app = FastAPI(title="Pocket Orchestra", version="0.1.0", docs_url="/api/docs", redoc_url=None)
app.include_router(control_router)


class GenerateRequest(BaseModel):
    config: dict
    render_preview: bool = True
    guide_for_ai: bool = False


class RenderRequest(BaseModel):
    job_id: str
    mode: str = 'original'


@app.get("/", response_class=HTMLResponse)
def home():
    return (ROOT / "web" / "index.html").read_text(encoding="utf-8")


@app.get("/api/metrics")
def metrics():
    """Live read-only CORE hardware status, polled every ~3 seconds by VPN UI."""
    return collect_metrics()


@app.get("/api/engines")
def ai_engine_status():
    """Honest engine readiness: installed Qwen, optional ACE-Step and GPU lease."""
    return {"score_ai": ollama_status(), "audio_ai": {**ace_step.status(), **gpu_control.state()}}


@app.get("/api/health")
def health():
    return {"status": "ok", "renderer": bool(shutil.which("fluidsynth") and SOUNDFONT.is_file()),
            "soundfont": str(SOUNDFONT) if SOUNDFONT.is_file() else None,
            "note": "MuseSounds rendering is performed on Windows .103 in MuseScore Studio"}


def _jobdir(job_id: str) -> Path:
    try:
        if str(uuid.UUID(job_id)) != job_id:
            raise ValueError()
    except (ValueError, TypeError):
        raise HTTPException(400, "Invalid job_id")
    location = OUTPUTS / job_id
    if not location.is_dir():
        raise HTTPException(404, "Job not found")
    return location


def _render(path: Path, *, guide_for_ai: bool = False) -> str:
    """FluidSynth renders a temporary WAV, then produces only an MP3 listening file.

    For a hybrid ACE-Step cover, keep the source WAV until the AI has finished.
    """
    if not shutil.which("fluidsynth"):
        return "Предпросмотр недоступен: не установлен FluidSynth"
    if not SOUNDFONT.is_file():
        return "Предпросмотр недоступен: SoundFont SF2 не найден"
    source = path / "preview.wav"
    try:
        result = subprocess.run(["fluidsynth", "-ni", "-F", str(source),
                                 str(SOUNDFONT), str(path / "score.mid")],
                                capture_output=True, text=True, timeout=240, check=False)
        if result.returncode or not source.is_file():
            return "Ошибка FluidSynth: " + result.stderr[-350:]
        if guide_for_ai:
            return "Временный WAV из MIDI готов для ACE-Step cover; после получения MP3 он удалится."
        encoder = shutil.which("ffmpeg")
        if not encoder:
            return "Для компактного MIDI-предпрослушивания установи ffmpeg: sudo apt install -y ffmpeg"
        mp3 = path / "preview.mp3"
        result = subprocess.run([encoder, "-hide_banner", "-nostdin", "-loglevel",
                                 "error", "-y", "-i", str(source), "-c:a", "libmp3lame",
                                 "-b:a", "192k", str(mp3)],
                                capture_output=True, text=True, timeout=240, check=False)
        if result.returncode or not mp3.is_file():
            return "Ошибка MP3-конвертации: " + result.stderr[-250:]
        return "Предпрослушивание создано в MP3 через FluidSynth (не MuseSounds)."
    except (OSError, subprocess.TimeoutExpired) as exc:
        return "Рендер завершился ошибкой: " + str(exc)[:200]
    finally:
        if not guide_for_ai:
            source.unlink(missing_ok=True)


@app.post("/api/audio/project")
def new_audio_project(payload: GenerateRequest):
    """One-click ACE-Step-only project: full prompt, no fake/random MIDI composition."""
    try:
        cfg = Config.from_dict(payload.config)
    except (ValueError, TypeError) as exc:
        raise HTTPException(422, str(exc)) from exc
    job_id = str(uuid.uuid4())
    job = OUTPUTS / job_id
    job.mkdir(parents=True)
    try:
        from .composer import _style
        report = {
            "composition": {"config": asdict(cfg), "planning": {
                "resolved_style": _style(cfg), "source": "audio_prompt_only"}},
            "engine": "ACE-Step 1.5 / neural original text-to-music",
            "source_midi": None,
        }
        (job / "report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        if cfg.lyrics.strip() and "choir" in cfg.ensemble:
            (job / "lyrics.txt").write_text(cfg.lyrics.strip() + "\n", encoding="utf-8")
    except Exception:
        shutil.rmtree(job, ignore_errors=True)
        raise
    return {"job_id": job_id, "engine": "ace-step", "mode": "original",
            "note": "Словесный промпт передан нейросети напрямую, MIDI не создавался."}


@app.post("/api/generate")
def generate(payload: GenerateRequest):
    try:
        cfg = Config.from_dict(payload.config)
    except (TypeError, ValueError) as e:
        raise HTTPException(422, str(e)) from e
    # Keep Qwen's VRAM lease for the ENTIRE composition/lyric LLM operation.
    # The old preflight-only check had a race with simultaneous audio requests.
    from contextlib import nullcontext
    session = (gpu_control.score_session(cfg.model)
               if cfg.use_ollama or cfg.score_engine == "ai_polyphony"
               else nullcontext())
    try:
        with session:
            plan = None
            llm_message = "Встроенный композитор: мотив + гармония + правила оркестровки"
            if cfg.use_ollama:
                try:
                    plan = generate_plan(cfg)
                    llm_message = f"LLM: {cfg.model}; план получен и проверен"
                except (RuntimeError, ValueError) as e:
                    raise HTTPException(503, f"Выбран режим Ollama, но музыкальный AI-план не получен: {str(e)[:200]}") from e
            piece = compose(cfg, plan)
            voice_result = optimize_satb(piece)
            piece.planning["satb_optimization"] = voice_result
            if cfg.score_engine == "ai_polyphony":
                try:
                    proposal = generate_counterpoint(cfg)
                    apply_counterpoint(piece, proposal)
                    llm_message += f"; AI-полифония: ноты двух голосов написал {cfg.model}"
                except (RuntimeError, ValueError) as exc:
                    raise HTTPException(503, f"ИИ-полифония не создана: {str(exc)[:180]}") from exc
            lyrics_text = None
            if "soprano" in piece.tracks:
                lyrics_text = cfg.lyrics.strip() or None
                lyric_mode = "user" if lyrics_text else "not_provided"
                if cfg.use_ollama and not lyrics_text:
                    try:
                        lyrics_text = generate_lyrics(cfg)
                        lyric_mode = f"ollama:{cfg.model}"
                        llm_message += "; оригинальные русские стихи написаны LLM"
                    except (RuntimeError, ValueError) as exc:
                        raise HTTPException(
                            503, f"Оllama не сочинила стихов. Впиши свой текст или проверь Ollama: {str(exc)[:150]}"
                        ) from exc
                if lyrics_text:
                    piece.planning["lyrics_on_soprano_notes"] = annotate_score_lyrics(piece, lyrics_text)
                piece.planning["lyric_mode"] = lyric_mode
                piece.planning["sung_audio_available"] = False
    except (RuntimeError, OSError) as exc:
        raise HTTPException(409, str(exc)[:250]) from exc
    report = inspect(piece)
    job_id = str(uuid.uuid4())
    out = OUTPUTS / job_id
    out.mkdir(parents=True)
    try:
        if lyrics_text:
            (out / "lyrics.txt").write_text(lyrics_text + "\n", encoding="utf-8")
        write_musicxml(piece, out / "score.musicxml")
        write_midi(piece, out / "score.mid")
        if set(("soprano", "alto", "tenor", "choral_bass")).issubset(piece.tracks):
            choir_tracks = {k: piece.tracks[k] for k in ("soprano", "alto", "tenor", "choral_bass")}
            choir = Piece(cfg, choir_tracks, piece.harmony, piece.section_names, piece.planning)
            write_musicxml(choir, out / "choir.musicxml")
            write_midi(choir, out / "choir.mid")
            instrumental = {k: v for k, v in piece.tracks.items() if k not in choir_tracks}
            if instrumental:
                accompaniment = Piece(cfg, instrumental, piece.harmony, piece.section_names, piece.planning)
                basename = "quartet" if cfg.ensemble == "quartet_choir" else "orchestra"
                write_musicxml(accompaniment, out / f"{basename}.musicxml")
                write_midi(accompaniment, out / f"{basename}.mid")
        manifest = {"composition": piece.summary(), "quality": report, "llm": llm_message,
                    "lyrics_note": "Если введены или получены настоящие стихи — они в lyrics.txt; FluidSynth слов не произносит",
                    "renderer": "Final audio should be exported from MuseScore Studio + MuseSounds on .103"}
        (out / "report.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        render_message = _render(out, guide_for_ai=payload.guide_for_ai) if payload.render_preview else "Предпрослушивание не запрошено"
    except Exception:
        shutil.rmtree(out, ignore_errors=True)
        raise
    urls = {"musicxml": f"/api/artifacts/{job_id}/score.musicxml",
            "midi": f"/api/artifacts/{job_id}/score.mid",
            "report": f"/api/artifacts/{job_id}/report.json"}
    for name in ("lyrics.txt", "choir.musicxml", "choir.mid", "orchestra.musicxml", "orchestra.mid", "quartet.musicxml", "quartet.mid", "neural_song.wav"):
        if (out / name).is_file():
            urls[name] = f"/api/artifacts/{job_id}/{name}"
    if (out / "preview.mp3").is_file():
        urls["mp3"] = f"/api/artifacts/{job_id}/preview.mp3"
    return {"job_id": job_id, "urls": urls, "quality": report, "llm": llm_message,
            "lyrics": lyrics_text, "lyrics_sung": False,
            "render": render_message, "composition": piece.summary()}


@app.get("/api/vocal/status")
def vocal_engine_status():
    state = gpu_control.state()
    engine = ace_step.status()
    # Service may be installed but stopped to release VRAM.
    return {**engine, **state, "available": state["ace_installed"] or engine["available"]}


@app.get("/api/gpu/status")
def gpu_engine_status():
    return gpu_control.state()


def _watch_audio_job(job_id: str) -> None:
    """Free VRAM when audio finishes even if the browser closes its tab.

    Runs only while the API process is alive; ACE-Step systemd RuntimeMaxSec
    also limits the independent model service as a crash-safety fallback.
    """
    import time
    # Long tracks need more than the former fixed 20-minute watcher window.
    # The service has a longer wall-clock cap, and the GPU lease is serialized.
    try:
        report = json.loads((_jobdir(job_id) / "report.json").read_text(encoding="utf-8"))
        duration = int(report["composition"]["config"].get("ai_duration") or 300)
    except (OSError, ValueError, KeyError, TypeError):
        duration = 300
    deadline = time.monotonic() + max(1800, min(10200, duration * 12))
    while time.monotonic() < deadline:
        time.sleep(6)
        try:
            state = ace_step.poll(_jobdir(job_id))
        except (OSError, RuntimeError, ValueError, KeyError, TypeError, json.JSONDecodeError):
            continue
        if state.get("state") in ("complete", "failed"):
            gpu_control.release_audio(job_id)
            return
    gpu_control.release_audio(job_id)


@app.post("/api/vocal/start")
def vocal_engine_start(payload: RenderRequest):
    job = _jobdir(payload.job_id)
    try:
        gpu_control.claim_audio(payload.job_id)
        gpu_control.launch_audio()
        # First run downloads its weights; wait for REST readiness, not for VRAM metrics.
        import time
        for _ in range(45):
            if ace_step.status()["available"]:
                break
            time.sleep(2)
        else:
            raise RuntimeError("ACE-Step ещё загружает веса или не стартовала. Проверь journalctl --user -u pocket-orchestra-ace.service")
        result = ace_step.start(job, mode=payload.mode)
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError, RuntimeError) as exc:
        gpu_control.release_audio(payload.job_id)
        raise HTTPException(503, str(exc)[:250]) from exc
    import threading
    threading.Thread(target=_watch_audio_job, args=(payload.job_id,),
                     daemon=True, name=f"ace-watch-{payload.job_id[:8]}").start()
    return result


@app.get("/api/vocal/poll/{job_id}")
def vocal_engine_poll(job_id: str):
    job = _jobdir(job_id)
    try:
        status = ace_step.poll(job, download=False)
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        raise HTTPException(503, str(exc)[:250]) from exc
    if status.get("url_ready") or status.get("state") == "failed":
        gpu_control.release_audio(job_id)
    if status.get("url_ready"):
        status["mp3_url"] = f"/api/artifacts/{job_id}/neural_song.mp3"
    return status


@app.post("/api/render")
def render_job(payload: RenderRequest):
    path = _jobdir(payload.job_id)
    result = _render(path)
    return {"message": result, "wav_url": f"/api/artifacts/{payload.job_id}/preview.wav" if (path / "preview.wav").is_file() else None}


@app.get("/api/artifacts/{job_id}/{filename}")
def artifact(job_id: str, filename: str):
    if filename not in ("score.musicxml", "score.mid", "report.json", "preview.mp3", "lyrics.txt", "choir.musicxml", "choir.mid", "orchestra.musicxml", "orchestra.mid", "quartet.musicxml", "quartet.mid", "neural_song.mp3"):
        raise HTTPException(404, "Unsupported artifact")
    path = _jobdir(job_id) / filename
    if not path.is_file():
        raise HTTPException(404, "Artifact not found")
    return FileResponse(path, filename=filename)


def main():
    import uvicorn
    uvicorn.run("pocket_orchestra.app:app", host=os.environ.get("POCKET_ORCHESTRA_HOST", "192.168.0.100"),
                port=int(os.environ.get("POCKET_ORCHESTRA_PORT", "9095")))


if __name__ == "__main__":
    main()
