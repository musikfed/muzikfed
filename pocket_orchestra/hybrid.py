"""Prepare ACE-Step 1.5 original or score-guided audio requests.

The 'cover' mode conditions on a local FluidSynth WAV derived from score.mid.
It can change notes and melody; it is NOT a note-accurate MIDI renderer.
"""
from __future__ import annotations

import json
from pathlib import Path

STYLES = {
    "opera": "operatic aria, expressive trained classical singer, legato, dynamic phrasing",
    "march": "ceremonial orchestral march, clear rhythmic accents, heroic energy",
    "lyrical": "lyrical ballad, expressive soft legato, intimate emotions",
    "folk": "Russian folk melodic character, acoustic instruments, expressive vocal phrasing",
    "ambient": "ambient cinematic textures, minimal pulse, evolving dynamics",
    "cinematic": "cinematic symphonic score, rich orchestration, contrasting sections",
}


def build_payload(job_dir: Path, mode: str = "original") -> tuple[dict, str]:
    """Construct and validate an ACE-Step request without side effects or networking."""
    if mode not in ("original", "guided"):
        raise ValueError("Режим звука: original или guided")
    report = json.loads((job_dir / "report.json").read_text(encoding="utf-8"))
    comp = report["composition"]
    cfg = comp["config"]
    style = cfg.get("style", "auto")
    if style == "auto":
        style = comp.get("planning", {}).get("resolved_style", "cinematic")
    character = STYLES.get(style, STYLES["cinematic"])
    ensemble = cfg["ensemble"]
    is_voice = "choir" in ensemble
    lyric_file = job_dir / "lyrics.txt"
    lyrics = lyric_file.read_text(encoding="utf-8").strip() if lyric_file.is_file() else ""
    title = cfg.get("title", "").strip()
    topic = cfg.get("prompt", "").strip()[:3000]
    if not topic:
        raise ValueError("Описание музыки не должно быть пустым")
    mode_description = ("Russian-language sung solo vocal, clear diction" if ensemble == "choir"
                        else "Russian-language sung lead with symphonic orchestral accompaniment"
                        if is_voice else "Instrumental only, no vocals")
    caption = f"{character}. {mode_description}. Title: {title}. Full user request: {topic}"
    seconds = max(10, min(600, round(int(cfg["bars"]) * 4 * 60 / int(cfg["tempo"]))))
    payload = {
        "prompt": caption, "lyrics": lyrics if is_voice else "[Instrumental]",
        "vocal_language": "ru" if is_voice else "en",
        "audio_format": "wav", "audio_duration": seconds,
        "bpm": int(cfg["tempo"]),
        "key_scale": f"{cfg['key']} {'minor' if cfg['mode'] == 'minor' else 'major'}",
        "time_signature": "4", "thinking": True, "model": "acestep-v15-turbo",
        "use_random_seed": False, "seed": int(cfg["seed"]), "batch_size": 1,
    }
    if is_voice and not lyrics:
        # Let the local model propose words from the real prompt, never hardcoded verses.
        payload["sample_query"] = f"Original Russian lyrics, with natural rhymes. {topic}"
        payload["sample_mode"] = True
    if mode == "guided":
        guide = (job_dir / "preview.wav").resolve()
        if not guide.is_file() or guide.stat().st_size < 44:
            raise ValueError("Для гибрида сначала создай опорный WAV из MIDI (галочка WAV).")
        payload.update(task_type="cover", src_audio_path=str(guide), audio_cover_strength=.65)
        note = "Нотный WAV передан как источник cover; ACE-Step может менять мелодию и длительность."
    else:
        note = "Новая нейропесня по промпту; нотная партитура остаётся независимой."
    return payload, note
