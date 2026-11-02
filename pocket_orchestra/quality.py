"""Static musical diagnostics. These are NOT a subjective quality rating."""
from __future__ import annotations
from .composer import Piece
from .theory import INSTRUMENTS, TONICS, chord_pcs
from .harmony import VOICES, parallel_perfects


def inspect(piece: Piece) -> dict:
    checks = []
    warnings = []
    out_of_range = []
    overlaps = []
    total, leaps, strong_total, strong_chord = 0, 0, 0, 0
    silent_bars = 0
    for key, notes in piece.tracks.items():
        instrument = INSTRUMENTS[key]
        prev = None
        last_end = 0
        active = set()
        for n in notes:
            total += 1
            if n.pitch < instrument.low or n.pitch > instrument.high:
                out_of_range.append(f"{key}: {n.pitch}")
            if n.start < last_end - 1e-9:
                overlaps.append(f"{key} @ {n.start}")
            last_end = n.start + n.duration
            if prev is not None and abs(n.pitch - prev) > 12:
                leaps += 1
            prev = n.pitch
            beat_in_bar = n.start % 4
            if beat_in_bar in (0, 2):
                strong_total += 1
                pcs = chord_pcs(TONICS[piece.config.key], piece.config.mode, piece.harmony[int(n.start // 4)])
                if n.pitch % 12 in pcs:
                    strong_chord += 1
        occupied = {int(x.start // 4) for x in notes}
        silent_bars += piece.config.bars - len(occupied)
    leap_rate = round(leaps / max(1, total), 3)
    chord_rate = round(strong_chord / max(1, strong_total), 3)
    checks += [{"id": "ranges", "ok": not out_of_range, "description": "Диапазоны инструментов"},
               {"id": "overlaps", "ok": not overlaps, "description": "Нет наложений в одной партии"},
               {"id": "bar_count", "ok": all(x.start + x.duration <= piece.config.bars * 4 + 1e-9 for t in piece.tracks.values() for x in t),
                "description": "События укладываются в форму"},
               {"id": "harmony", "ok": chord_rate >= .72, "description": "Опорные доли согласованы с гармонией"},
               {"id": "melodic_leaps", "ok": leap_rate <= .12, "description": "Нет избытка больших мелодических скачков"}]
    satb_parallels = 0
    satb_crossings = 0
    if set(VOICES).issubset(piece.tracks):
        previous_voicing = None
        for bar in range(piece.config.bars):
            # Include any note sounding on beat 1, even if the soprano is melodic.
            sounding = [next((n.pitch for n in piece.tracks[voice]
                              if n.start <= bar * 4 < n.start + n.duration), None)
                        for voice in VOICES]
            if any(pitch is None for pitch in sounding):
                previous_voicing = None
                continue
            voicing = tuple(sounding)
            if not (voicing[0] > voicing[1] > voicing[2] > voicing[3]):
                satb_crossings += 1
            if previous_voicing is not None:
                satb_parallels += parallel_perfects(previous_voicing, voicing)
            previous_voicing = voicing
        checks += [{"id": "satb_crossing", "ok": satb_crossings == 0,
                    "description": "Хоровые голоса не перекрещиваются"},
                   {"id": "satb_parallel", "ok": satb_parallels == 0,
                    "description": "Нет параллельных квинт и октав на границах тактов"}]
        if satb_parallels:
            warnings.append(f"Параллельные совершенные интервалы SATB: {satb_parallels}")
        if satb_crossings:
            warnings.append(f"Перекрещивания голосов SATB: {satb_crossings}")
    if silent_bars:
        warnings.append(f"Паузы в оркестровке: {silent_bars} пустых партие-тактов — могут быть намеренными")
    if chord_rate < .72:
        warnings.append("Проверь диссонансы на сильных долях; выразительные задержания не обязательно ошибка")
    if leap_rate > .12:
        warnings.append("Много скачков больше октавы; стоит проверить голосоведение")
    if out_of_range:
        warnings.append("Ноты вне диапазонов: " + ", ".join(out_of_range[:5]))
    if overlaps:
        warnings.append("Перекрывающиеся события: " + ", ".join(overlaps[:5]))
    return {"passed": sum(x["ok"] for x in checks), "total": len(checks), "checks": checks,
            "statistics": {"notes": total, "parts": len(piece.tracks), "leap_rate": leap_rate,
                           "strong_beat_chord_ratio": chord_rate, "silent_part_bars": silent_bars, "satb_parallel_perfects": satb_parallels, "satb_crossings": satb_crossings},
            "warnings": warnings,
            "notice": "Статические проверки не оценивают вкус, драматургию и реализм звучания."}
