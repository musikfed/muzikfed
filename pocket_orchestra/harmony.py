"""Four-part SATB chord voicing via bounded beam search.

Avoid crossed voices and penalize parallel fifths/octaves while keeping melodic
phrases/registral separation. A simplified arranger, not a full counterpoint tutor.
"""
from __future__ import annotations
from itertools import product, combinations
from random import Random
from .theory import INSTRUMENTS, TONICS, chord_pcs
from .composer import Piece, Note, _velocity, _arc

VOICES = ("soprano", "alto", "tenor", "choral_bass")
ANCHORS = (73, 65, 57, 48)


def _pitches(pc: int, voice: str, anchor: int) -> list[int]:
    inst = INSTRUMENTS[voice]
    options = [n for n in range(inst.low, inst.high + 1) if n % 12 == pc]
    return sorted(options, key=lambda n: abs(n - anchor))[:2]


def _choices(chord: tuple[int, int, int], lead: int | None) -> list[tuple[float, tuple[int, ...]]]:
    pools = []
    for i, voice in enumerate(VOICES):
        if i == 0 and lead is not None:
            if lead % 12 not in chord:
                raise ValueError("Lead melody strong beat must be a chord tone")
            options = [lead]
        elif i == 3:
            options = sorted(set(_pitches(chord[0], voice, ANCHORS[i]) +
                                 _pitches(chord[1], voice, ANCHORS[i])))
        else:
            options = sorted(set(n for pc in chord for n in _pitches(pc, voice, ANCHORS[i])))
        pools.append(options)
    choices = []
    for notes in product(*pools):
        s, a, t, b = notes
        if not (s > a > t > b and 3 <= s-a <= 12 and 3 <= a-t <= 12 and 4 <= t-b <= 17):
            continue
        if set(notes[i] % 12 for i in range(4)) != set(chord):
            continue
        cost = sum(.14 * abs(n - ANCHORS[i]) for i, n in enumerate(notes))
        cost += .9 if b % 12 != chord[0] else 0
        cost += 1 if s % 12 == chord[0] else 0  # favor third/fifth in soprano
        choices.append((cost, notes))
    return sorted(choices, key=lambda c: c[0])[:180]


def parallel_perfects(before: tuple[int, ...], after: tuple[int, ...]) -> int:
    total = 0
    for i, j in combinations(range(4), 2):
        old_interval = (before[i] - before[j]) % 12
        new_interval = (after[i] - after[j]) % 12
        motion_i, motion_j = after[i] - before[i], after[j] - before[j]
        if old_interval == new_interval and old_interval in (0, 7) and motion_i * motion_j > 0:
            total += 1
    return total


def _transition(before: tuple[int, ...], after: tuple[int, ...]) -> float:
    movement = sum((abs(a-b) ** 1.4) * weight for a, b, weight in
                   zip(after, before, (.8, 1.0, 1.0, .6)))
    leaps = sum(max(0, abs(a-b)-7) * 5 for a, b in zip(after, before))
    fixed = sum(1 for a, b in zip(after, before) if a == b)
    return movement + leaps + 100 * parallel_perfects(before, after) + max(0, fixed - 2) * 2


def optimize_satb(piece: Piece) -> dict:
    cfg = piece.config
    if not set(VOICES).issubset(piece.tracks):
        return {"applied": False, "reason": "SATB not requested"}
    lead_pitches = {}
    if cfg.ensemble == "choir":
        for n in piece.tracks["soprano"]:
            if n.start % 4 == 0:
                lead_pitches[int(n.start // 4)] = n.pitch
    candidates = []
    for bar, degree in enumerate(piece.harmony):
        chord = chord_pcs(TONICS[cfg.key], cfg.mode, degree)
        choices = _choices(chord, lead_pitches.get(bar))
        if not choices:
            raise ValueError(f"Unable to voice SATB chord in bar {bar+1}")
        candidates.append(choices)
    beam = [(cost, [notes]) for cost, notes in candidates[0][:40]]
    for bar in range(1, cfg.bars):
        next_beam = []
        for cost, notes in candidates[bar]:
            best_cost, best_path = min(((past_cost + _transition(path[-1], notes) + cost, path)
                                        for past_cost, path in beam), key=lambda x: x[0])
            next_beam.append((best_cost, best_path + [notes]))
        next_beam.sort(key=lambda x: x[0])
        beam = next_beam[:35]
    _, best_path = min(beam, key=lambda x: x[0])
    rng = Random(cfg.seed + 77)
    if cfg.choir_entry >= 0:
        entry_bar = min(cfg.bars - 4, round(cfg.bars * cfg.choir_entry / 4) * 4)
    elif piece.planning.get("prompt_cues", {}).get("choir_enters_late") and cfg.ensemble in ("orchestra_choir", "quartet_choir"):
        entry_bar = (cfg.bars // 8) * 4  # start at a four-bar phrase boundary
    else:
        entry_bar = 0
    late = entry_bar > 0
    for idx, voice in enumerate(VOICES):
        if cfg.ensemble == "choir" and voice == "soprano":
            continue  # Retain thematic rhythmic melody for solo vocal quartet
        part = []
        for bar, notes in enumerate(best_path):
            if late and bar < entry_bar:
                continue
            arc = _arc(bar, cfg.bars, cfg.climax)
            if piece.planning.get("prompt_cues", {}).get("quiet_coda") and bar >= cfg.bars - 2:
                arc *= .34
            part.append(Note(notes[idx], bar * 4, 4, _velocity(cfg, arc, voice, rng),
                             "tenuto", cfg.choir_vowel))
        piece.tracks[voice] = part
    if late:
        piece.tracks["soprano"] = [n for n in piece.tracks["soprano"] if n.start >= entry_bar * 4]
    parallels = sum(parallel_perfects(a, b) for a, b in zip(best_path, best_path[1:]))
    return {"applied": True, "parallel_perfects": parallels,
            "bars": cfg.bars, "choir_late": late, "choir_entry_bar": entry_bar + 1, "method": "SATB beam search; avoid voice crossing and parallel perfect intervals"}
