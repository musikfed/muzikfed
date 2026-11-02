"""Reproducible thematic composer; *not* an ML model or promise of artistic quality.

A motif returns throughout the work, with contrasting bridge and cadence;
arrangement is role-based, instead of independent random note generation.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict, fields
from random import Random
from .theory import TONICS, SCALES, INSTRUMENTS, ORCHESTRA, STRING_QUARTET, CHOIR, chord_pcs, note_in_range


@dataclass
class Config:
    title: str = "Симфонический эскиз"
    prompt: str = "Тревожное начало, светлая кульминация и тёплое завершение."
    ensemble: str = "orchestra_choir"
    key: str = "D"
    mode: str = "minor"
    tempo: int = 94
    bars: int = 16
    density: float = 0.55
    tension: float = 0.7
    expression: float = 0.8
    humanize: float = 0.25
    brass_level: float = 0.65
    choir_entry: float = -1.0  # -1 = derive from prompt; 0..0.9 = proportion of piece
    climax: float = 0.73
    seed: int = 42
    choir_vowel: str = "Ahh"
    use_ollama: bool = False
    model: str = "qwen3:8b"

    def __post_init__(self):
        if not (1 <= len(self.title) <= 100 and len(self.prompt) <= 4000):
            raise ValueError("Название (1–100) или промпт (до 4000 символов) некорректны")
        if self.ensemble not in ("orchestra", "quartet", "choir", "orchestra_choir", "quartet_choir"):
            raise ValueError("Неизвестный состав ансамбля")
        if self.key not in TONICS or self.mode not in SCALES:
            raise ValueError("Неизвестная тональность/лад")
        if not (45 <= self.tempo <= 190) or self.bars not in (8, 12, 16, 24, 32, 48, 64):
            raise ValueError("Темп 45–190, тактов: 8/12/16/24/32/48/64")
        for name in ("density", "tension", "expression", "humanize", "brass_level", "climax"):
            if not (0 <= float(getattr(self, name)) <= 1):
                raise ValueError(f"{name} должен быть от 0 до 1")
        if self.choir_entry != -1 and not (0 <= self.choir_entry <= .9):
            raise ValueError("choir_entry: -1 (авто) или от 0 до 0.9")
        if self.choir_vowel not in ("Ahh", "Ooh", "Mmm"):
            raise ValueError("Допустимые гласные: Ahh, Ooh, Mmm")
        if not (0 <= self.seed < 2**32):
            raise ValueError("seed вне диапазона")
        if not (1 <= len(self.model) <= 80):
            raise ValueError("Некорректное имя модели")

    @classmethod
    def from_dict(cls, value: dict) -> "Config":
        allowed = {f.name for f in fields(cls)}
        unknown = set(value) - allowed
        if unknown:
            raise ValueError(f"Неизвестные параметры: {', '.join(sorted(unknown))}")
        return cls(**value)


@dataclass(frozen=True)
class Note:
    pitch: int
    start: float   # beats (quarter note units) from beginning
    duration: float
    velocity: int
    articulation: str = ""
    lyric: str = ""


@dataclass
class Piece:
    config: Config
    tracks: dict[str, list[Note]]
    harmony: list[int]
    section_names: list[str]
    planning: dict

    def summary(self):
        return {"config": asdict(self.config), "sections": self.section_names,
                "harmony": self.harmony, "parts": {k: len(v) for k, v in self.tracks.items()},
                "planning": self.planning}


def instrumentation(ensemble: str) -> tuple[str, ...]:
    return {"quartet": STRING_QUARTET, "choir": CHOIR, "orchestra": ORCHESTRA,
            "orchestra_choir": ORCHESTRA + CHOIR, "quartet_choir": STRING_QUARTET + CHOIR}[ensemble]


def _near_degree(cfg: Config, degree: int, target: int, instr: str) -> int:
    pc = (TONICS[cfg.key] + SCALES[cfg.mode][degree % 7]) % 12
    return note_in_range(pc, target, INSTRUMENTS[instr])


def _velocity(cfg: Config, arc: float, instrument: str, rng: Random) -> int:
    base = 52 + 43 * arc + 10 * cfg.expression
    if instrument in ("flute", "harp", "clarinet"):
        base -= 10
    if instrument in CHOIR:
        base -= 5
    if instrument in ("horn", "trumpet"):
        base += (cfg.brass_level - .65) * 26
    return int(max(35, min(120, base + rng.uniform(-3, 3))))


def _arc(bar: int, n: int, climax: float) -> float:
    position = (bar + 0.5) / n
    dist = abs(position - climax)
    return max(0.12, min(1.0, 1.0 - dist / max(0.28, climax)))


def _choose_harmony(cfg: Config, plan: dict | None) -> tuple[list[int], list[str]]:
    # Harmony is diatonic. Chosen from contrasting 4-bar cells with a stable cadence.
    if cfg.mode == "minor":
        variants = ([0, 5, 2, 4], [0, 3, 5, 4], [0, 6, 3, 4], [0, 5, 3, 4])
        a, b = list(variants[cfg.seed % len(variants)]), [3, 5, 4, 0]
    else:
        variants = ([0, 4, 5, 3], [0, 3, 4, 0], [0, 5, 3, 4], [0, 1, 4, 0])
        a, b = list(variants[cfg.seed % len(variants)]), [3, 1, 4, 0]
    if plan:
        maybe_a, maybe_b = plan.get("progression_a"), plan.get("progression_b")
        if isinstance(maybe_a, list) and len(maybe_a) == 4 and all(type(x) is int and 0 <= x <= 6 for x in maybe_a):
            a = maybe_a
        if isinstance(maybe_b, list) and len(maybe_b) == 4 and all(type(x) is int and 0 <= x <= 6 for x in maybe_b):
            b = maybe_b
    sections = []
    harmony = []
    for bar in range(cfg.bars):
        # 4-bar groups: A -> A' -> B -> A'', repeating for longer pieces.
        k = (bar // 4) % 4
        section = ("A", "A′", "B", "A″")[k]
        sections.append(section)
        progression = b if k == 2 else a
        degree = progression[bar % 4]
        if bar == cfg.bars - 1:
            degree = 0
        harmony.append(degree)
    return harmony, sections


def interpret_prompt(cfg: Config) -> dict:
    """Conservative Russian/English cue detector; real semantic parsing needs Ollama."""
    text = cfg.prompt.casefold()
    intro_cello = ("виолонч" in text or "cello" in text) and any(x in text for x in ("начал", "вступлен", "opening", "intro"))
    choir_late = any(x in text for x in ("кульминац", "финал", "climax", "finale")) and any(x in text for x in ("хор", "choir"))
    quiet_coda = ("кода" in text or "coda" in text or "в конце" in text or "ending" in text) and any(x in text for x in ("тих", "спокой", "quiet", "soft"))
    return {"cello_intro": intro_cello, "choir_enters_late": choir_late,
            "quiet_coda": quiet_coda, "parser": "simple cue heuristics (not full NLP)"}


def compose(cfg: Config, plan: dict | None = None) -> Piece:
    rng = Random(cfg.seed)
    intent = interpret_prompt(cfg)
    harmony, sections = _choose_harmony(cfg, plan)
    keys = instrumentation(cfg.ensemble)
    tracks: dict[str, list[Note]] = {key: [] for key in keys}
    # Melodic motif offsets are scale degrees relative to a harmonic root.
    motif = list([[4, 3, 2, 0], [2, 4, 3, 0], [4, 5, 2, 0], [2, 1, 0, 2]][(cfg.seed // 4) % 4])
    if plan and isinstance(plan.get("motif"), list):
        proposal = plan["motif"]
        if len(proposal) == 4 and all(type(x) is int and -4 <= x <= 7 for x in proposal):
            motif = proposal
    primary_voice = "violin_1" if "violin_1" in keys else "soprano"
    previous = {k: (INSTRUMENTS[k].low + INSTRUMENTS[k].high) // 2 for k in keys}

    def add(key: str, bar: int, offset: float, length: float, degree: int,
            register: int | None = None, art: str = "", lyric: str = ""):
        if key not in tracks:
            return
        target = previous[key] if register is None else register
        note = _near_degree(cfg, degree, target, key)
        # Keep a steady register and smooth most voices; octave jumps are intentional
        previous[key] = note
        arc = _arc(bar, cfg.bars, cfg.climax)
        if intent["quiet_coda"] and bar >= cfg.bars - 2:
            arc *= .34
        tracks[key].append(Note(note, bar * 4 + offset, length,
                                _velocity(cfg, arc, key, rng), art, lyric))

    for bar, chord in enumerate(harmony):
        section = sections[bar]
        energy = _arc(bar, cfg.bars, cfg.climax)
        # SAME motif returns in A/A′/A″, transposed by harmony, with a contrasting B.
        variant = [motif[0], motif[1], motif[2], motif[3]]
        if section == "B":
            variant = [2, 4, 5, 2]
        elif section == "A′":
            variant[-1] = max(-4, min(7, variant[-1] + 1))
        elif section == "A″" and bar % 4 == 3:
            variant = [4, 2, 1, 0]
        if bar == cfg.bars - 1:
            variant = [4, 2, 0, 0]

        lead = "cello" if (intent["cello_intro"] and bar < 4 and "cello" in keys) else primary_voice
        # Melodic rhythm uses an intentionally recognizable bar shape.
        durations = [(1, 1, 1, 1), (1.5, .5, 1, 1), (2, 1, 1)][(bar // 4) % 3]
        if cfg.density < 0.4:
            durations = (2, 1, 1)
        start = 0.0
        for i, dur in enumerate(durations):
            degree = chord + variant[min(i, 3)]
            if i == 0:
                degree = chord + 4  # a chord tone on the downbeat
            add(lead, bar, start, dur, degree,
                56 if lead == "cello" else 76 if lead == "violin_1" else 71,
                "tenuto" if dur >= 2 else "", cfg.choir_vowel if lead in CHOIR else "")
            start += dur

        if "violin_2" in keys:
            for off, degree in ((0, chord + 2), (2, chord + 1)):
                add("violin_2", bar, off, 2, degree, 69, "legato")
        if "viola" in keys:
            add("viola", bar, 0, 2, chord + 2, 59)
            add("viola", bar, 2, 2, chord + 4, 59)
        if "cello" in keys and not (lead == "cello"):
            add("cello", bar, 0, 2, chord, 48, "tenuto")
            add("cello", bar, 2, 2, chord + 4, 50)
        if "bass" in keys:
            add("bass", bar, 0, 4, chord, 37, "tenuto")
        if "flute" in keys and (bar % 4 in (1, 2) or energy > 0.88):
            add("flute", bar, 0, 2, chord + 4, 81, "legato")
            add("flute", bar, 2, 2, chord + 2, 79)
        if "oboe" in keys and bar % 4 in (0, 3):
            add("oboe", bar, 2, 2, chord + 2, 72)
        if "clarinet" in keys and (cfg.density > .32 or section == "B"):
            for off, deg in ((0, chord), (1, chord + 2), (2, chord + 4), (3, chord + 2)):
                add("clarinet", bar, off, 1, deg, 65, "staccato" if cfg.density > .8 else "")
        if "horn" in keys and (energy > (.55 - .28 * cfg.brass_level) or section == "B"):
            add("horn", bar, 0, 4, chord + 2, 58, "tenuto")
        if "trumpet" in keys and not (intent["quiet_coda"] and bar >= cfg.bars - 2) and energy > (0.78 - 0.3 * cfg.brass_level + 0.1 * (1 - cfg.tension)):
            add("trumpet", bar, 0, 2, chord + 4, 70, "accent")
            add("trumpet", bar, 2, 2, chord + 2, 68)
        if "harp" in keys:
            if cfg.density > .5 or bar % 2 == 0:
                for off, deg in ((0, chord), (1, chord + 2), (2, chord + 4), (3, chord + 2)):
                    add("harp", bar, off, 1, deg, 72)
        if "timpani" in keys and (bar % 4 == 0 or bar == cfg.bars - 1 or energy > .92):
            add("timpani", bar, 0, 2, chord, 44, "accent")
        # SATB harmony is composed separately, not simply a 40-voice sample label.
        # Each staff gets its own line with parsimonious (nearest-note) voice leading.
        if "soprano" in keys and primary_voice != "soprano":
            add("soprano", bar, 0, 4, chord + 4, 73, "legato", cfg.choir_vowel)
        if "alto" in keys:
            add("alto", bar, 0, 4, chord + 2, 65, "legato", cfg.choir_vowel)
        if "tenor" in keys:
            add("tenor", bar, 0, 4, chord + 4, 58, "legato", cfg.choir_vowel)
        if "choral_bass" in keys:
            add("choral_bass", bar, 0, 4, chord, 48, "legato", cfg.choir_vowel)

    result_plan = dict(plan) if plan else {"source": "rule_based", "notes": "Recurrent motif, diatonic harmony, contrasting B section, cadential tonic"}
    result_plan["prompt_cues"] = intent
    return Piece(cfg, tracks, harmony, sections, result_plan)
