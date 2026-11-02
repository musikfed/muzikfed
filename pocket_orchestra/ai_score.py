"""AI symbolic counterpoint composer (Ollama/Qwen) with validated note-level output.

A separate AI from ACE-Step audio. Produces two interacting lines on the 4/4
MusicXML/MIDI score; this is an exploratory contrapuntal mode, NOT Bach-quality.
"""
from __future__ import annotations

import json
from dataclasses import replace
import urllib.error
import urllib.request

from .composer import Config, Note, Piece, _near_degree
from .theory import INSTRUMENTS


def _phrase(value: object, label: str, per_bar: int) -> list[list[int]]:
    if (not isinstance(value, list) or len(value) != 4 or
        any(not isinstance(bar, list) or len(bar) != per_bar for bar in value)):
        raise ValueError(f"ИИ вернул неправильную структуру {label}")
    result: list[list[int]] = []
    for bar in value:
        if any(type(note) is not int or not -3 <= note <= 9 for note in bar):
            raise ValueError(f"ИИ вернул неправильные ноты {label}")
        result.append(bar)
    return result


def validate_proposal(raw: object) -> dict:
    """Reject malformed or clearly non-independent lines; no hidden fallback."""
    if not isinstance(raw, dict):
        raise ValueError("ИИ-композитор не вернул JSON-объект")
    data = {k: _phrase(raw.get(k), k, 4 if k.startswith("upper") else 2)
            for k in ("upper_a", "upper_b", "lower_a", "lower_b")}
    for upper, lower in (("upper_a", "lower_a"), ("upper_b", "lower_b")):
        if all(data[upper][bar][0] == data[lower][bar][0] for bar in range(4)):
            raise ValueError("ИИ не создал независимые голоса")
    return data


def generate_counterpoint(cfg: Config, *, endpoint: str = "http://127.0.0.1:11434/api/generate") -> dict:
    """Ask local Qwen to actually write note degrees, rather than choosing templates."""
    prompt = f"""Ты композитор классической полифонии. Сочини ОРИГИНАЛЬНЫЕ 2 независимые
мелодические линии с имитацией, секвенциями и контрапунктом, выразительной
кульминацией и разрешением. Не копируй известных композиторов.
Полный художественный замысел: {cfg.prompt}
Название: {cfg.title}. Тональность: {cfg.key} {cfg.mode}; 4/4; темп {cfg.tempo}.
Стиль: {cfg.style}; ансамбль: {cfg.ensemble}; seed для вариации: {cfg.seed}.
Если чиптюн/Dendy: создавай запоминающийся игровой мотив и контрастную секцию;
если synthwave: мелодия над пульсирующими синтезаторами; для оркестра —
фразировку и встречные голоса. Приоритет — целостная оригинальная тема.
Каждая нота - ступень выбранного лада, ЦЕЛОЕ число от -3 до 9, относительно тоники.
Верни только JSON: верхний голос upper_a и upper_b по 4 такта, в каждом такте
4 ступени (четверти). Нижний голос lower_a и lower_b по 4 такта, в каждом 2
ступени (половинные ноты). Каждая тема B отличается от A, но связана с ней.
Нижний голос должен двигаться самостоятельно, часто противоположно верхнему;
избегай параллельных квинт и октав. Реальный рисунок нот, а не описание.
Формат: {{"upper_a":[[0,2,4,3],[2,4,5,4],[3,2,1,0],[2,1,0,0]],
"upper_b":[[4,5,6,4],[5,4,3,2],[4,3,1,2],[2,1,0,0]],
"lower_a":[[0,4],[3,1],[4,2],[4,0]],
"lower_b":[[0,2],[3,1],[4,2],[4,0]]}}
Не повторяй цифры примера: придумай свою музыку по моему описанию."""
    body = json.dumps({"model": cfg.model, "prompt": prompt, "stream": False,
                       "format": "json", "options": {"temperature": .9, "num_predict": 1100},
                       "keep_alive": 0}).encode("utf-8")
    try:
        req = urllib.request.Request(endpoint, data=body, method="POST",
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=180) as response:
            result = json.loads(response.read(2_000_000))
        return validate_proposal(json.loads(result["response"]))
    except (OSError, urllib.error.URLError, ValueError, KeyError) as err:
        raise RuntimeError(f"ИИ-полифонист не ответил или нарушил нотную схему: {err}") from err


def apply_counterpoint(piece: Piece, proposal: dict) -> Piece:
    """Write the AI's two independent voices as MIDI-ready Note events."""
    data = validate_proposal(proposal)
    tracks = piece.tracks
    upper = next((v for v in ("chip_lead", "synth_lead", "violin_1", "soprano")
                  if v in tracks), None)
    lower = next((v for v in ("chip_bass", "synth_bass", "cello", "choral_bass")
                  if v in tracks), None)
    if lower is None or upper is None:
        raise ValueError("В выбранном составе отсутствуют два независимых голоса")
    cfg = piece.config
    output: dict[str, list[Note]] = {upper: [], lower: []}
    last = {upper: 76 if upper in ("chip_lead", "synth_lead", "violin_1") else 72, lower: 48}
    for bar in range(cfg.bars):
        section = (bar // 4) % 4
        phrase = "b" if section == 2 else "a"
        pos = bar % 4
        high = data["upper_" + phrase][pos][:]
        low = data["lower_" + phrase][pos][:]
        if section == 1 and pos == 3:
            high[-1] = max(-3, high[-1] - 1)
        if bar == cfg.bars - 1:
            high[-1] = low[-1] = 0
        for staff, steps, beat_size in ((upper, high, 1), (lower, low, 2)):
            for index, degree in enumerate(steps):
                pitch = _near_degree(cfg, degree, last[staff], staff)
                last[staff] = pitch
                output[staff].append(Note(pitch=pitch, start=bar*4 + index*beat_size,
                                          duration=beat_size, velocity=85 if staff == upper else 70,
                                          articulation="legato"))
    for staff, notes in output.items():
        tracks[staff] = notes
    piece.planning["ai_counterpoint"] = {
        "source": "ollama_note_level", "model": cfg.model,
        "roles": [upper, lower], "phrase_data": data,
        "description": "AI writes actual notes for two independent parts; accompaniment remains rule-based",
        "guaranteed_bach_quality": False,
    }
    return piece
