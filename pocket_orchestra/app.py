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

ROOT = Path(__file__).resolve().parent.parent
OUTPUTS = Path(os.environ.get("POCKET_ORCHESTRA_OUTPUT", str(ROOT / "outputs"))).resolve()
OUTPUTS.mkdir(parents=True, exist_ok=True)
SOUNDFONT = Path(os.environ.get("POCKET_ORCHESTRA_SF2", "/usr/share/sounds/sf2/FluidR3_GM.sf2"))
app = FastAPI(title="Pocket Orchestra", version="0.1.0", docs_url="/api/docs", redoc_url=None)
app.include_router(control_router)


class GenerateRequest(BaseModel):
    config: dict
    render_preview: bool = True


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


def _render(path: Path) -> str:
    if not shutil.which("fluidsynth"):
        return "Предпросмотр недоступен: не установлен fluidsynth"
    if not SOUNDFONT.is_file():
        return "Предпросмотр недоступен: SoundFont SF2 не найден"
    try:
        result = subprocess.run(["fluidsynth", "-ni", "-F", str(path / "preview.wav"),
                                 str(SOUNDFONT), str(path / "score.mid")],
                                capture_output=True, text=True, timeout=180, check=False)
    except (OSError, subprocess.TimeoutExpired) as e:
        return "Рендер завершился ошибкой: " + str(e)[:200]
    if result.returncode or not (path / "preview.wav").is_file():
        return "Ошибка FluidSynth: " + result.stderr[-350:]
    return "Черновой WAV создан с помощью FluidSynth; не путать с финальным MuseSounds"


@app.post("/api/generate")
def generate(payload: GenerateRequest):
    try:
        cfg = Config.from_dict(payload.config)
    except (TypeError, ValueError) as e:
        raise HTTPException(422, str(e)) from e
    if cfg.use_ollama or cfg.score_engine == "ai_polyphony":
        try:
            gpu_control.before_score()
        except (RuntimeError, OSError) as exc:
            raise HTTPException(409, str(exc)) from exc
    plan = None
    llm_message = "Встроенный композитор: мотив + гармония + правила оркестровки"
    if cfg.use_ollama:
        try:
            plan = generate_plan(cfg)
            llm_message = f"LLM: {cfg.model}; план получен и проверен"
        except (RuntimeError, ValueError) as e:
            gpu_control.unload_ollama(cfg.model)
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
            gpu_control.unload_ollama(cfg.model)
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
                gpu_control.unload_ollama(cfg.model)
                raise HTTPException(
                    503, f"Оllama не сочинила стихов. Впиши свой текст или проверь Ollama: {str(exc)[:150]}"
                ) from exc
        if lyrics_text:
            piece.planning["lyrics_on_soprano_notes"] = annotate_score_lyrics(piece, lyrics_text)
        piece.planning["lyric_mode"] = lyric_mode
        piece.planning["sung_audio_available"] = False
    if cfg.use_ollama or cfg.score_engine == "ai_polyphony":
        gpu_control.unload_ollama(cfg.model)
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
        render_message = _render(out) if payload.render_preview else "Черновой WAV не запрошен"
    except Exception:
        shutil.rmtree(out, ignore_errors=True)
        raise
    urls = {"musicxml": f"/api/artifacts/{job_id}/score.musicxml",
            "midi": f"/api/artifacts/{job_id}/score.mid",
            "report": f"/api/artifacts/{job_id}/report.json"}
    for name in ("lyrics.txt", "choir.musicxml", "choir.mid", "orchestra.musicxml", "orchestra.mid", "quartet.musicxml", "quartet.mid", "neural_song.wav"):
        if (out / name).is_file():
            urls[name] = f"/api/artifacts/{job_id}/{name}"
    if (out / "preview.wav").is_file():
        urls["wav"] = f"/api/artifacts/{job_id}/preview.wav"
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
    return result


@app.get("/api/vocal/poll/{job_id}")
def vocal_engine_poll(job_id: str):
    job = _jobdir(job_id)
    try:
        status = ace_step.poll(job)
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        raise HTTPException(503, str(exc)[:250]) from exc
    if status.get("url_ready") or status.get("state") == "failed":
        gpu_control.release_audio(job_id)
    if status.get("url_ready"):
        status["wav_url"] = f"/api/artifacts/{job_id}/neural_song.wav"
    return status


@app.post("/api/render")
def render_job(payload: RenderRequest):
    path = _jobdir(payload.job_id)
    result = _render(path)
    return {"message": result, "wav_url": f"/api/artifacts/{payload.job_id}/preview.wav" if (path / "preview.wav").is_file() else None}


@app.get("/api/artifacts/{job_id}/{filename}")
def artifact(job_id: str, filename: str):
    if filename not in ("score.musicxml", "score.mid", "report.json", "preview.wav", "lyrics.txt", "choir.musicxml", "choir.mid", "orchestra.musicxml", "orchestra.mid", "quartet.musicxml", "quartet.mid", "neural_song.wav"):
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
