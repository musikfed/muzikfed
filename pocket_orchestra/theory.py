"""Music theory definitions: concert pitch, octave ranges and diatonic harmony."""
from dataclasses import dataclass

SCALES = {"minor": (0, 2, 3, 5, 7, 8, 10), "major": (0, 2, 4, 5, 7, 9, 11)}
TONICS = {"C": 0, "C#": 1, "D": 2, "Eb": 3, "E": 4, "F": 5, "F#": 6,
          "G": 7, "Ab": 8, "A": 9, "Bb": 10, "B": 11}
MAJOR_FIFTHS = {"C": 0, "G": 1, "D": 2, "A": 3, "E": 4, "B": 5,
                "F#": 6, "C#": 7, "F": -1, "Bb": -2, "Eb": -3, "Ab": -4}
MINOR_FIFTHS = {"A": 0, "E": 1, "B": 2, "F#": 3, "C#": 4, "G": -2,
                "D": -1, "C": -3, "F": -4, "Bb": -5, "Eb": -6, "Ab": -7}

@dataclass(frozen=True)
class Instrument:
    key: str
    name: str
    low: int
    high: int
    gm_program: int  # zero-based General MIDI
    clef: str = "G"
    family: str = "strings"

INSTRUMENTS = {
    "violin_1": Instrument("violin_1", "Скрипки I", 60, 96, 40),
    "violin_2": Instrument("violin_2", "Скрипки II", 55, 88, 40),
    "viola": Instrument("viola", "Альты", 48, 84, 41, "C"),
    "cello": Instrument("cello", "Виолончели", 36, 76, 42, "F"),
    "bass": Instrument("bass", "Контрабасы", 28, 60, 43, "F"),
    "flute": Instrument("flute", "Флейта", 60, 96, 73, "G", "woodwinds"),
    "oboe": Instrument("oboe", "Гобой", 58, 89, 68, "G", "woodwinds"),
    "clarinet": Instrument("clarinet", "Кларнет (концертный строй)", 50, 91, 71, "G", "woodwinds"),
    "horn": Instrument("horn", "Валторны (концертный строй)", 40, 77, 60, "F", "brass"),
    "trumpet": Instrument("trumpet", "Трубы (концертный строй)", 54, 84, 56, "G", "brass"),
    "harp": Instrument("harp", "Арфа", 48, 96, 46, "G", "other"),
    "timpani": Instrument("timpani", "Литавры", 36, 60, 47, "F", "percussion"),
    "soprano": Instrument("soprano", "Хор — сопрано", 60, 81, 52, "G", "choir"),
    "alto": Instrument("alto", "Хор — альт", 55, 74, 52, "G", "choir"),
    "tenor": Instrument("tenor", "Хор — тенор", 48, 69, 52, "G", "choir"),
    "choral_bass": Instrument("choral_bass", "Хор — бас", 40, 64, 52, "F", "choir"),
}
STRING_QUARTET = ("violin_1", "violin_2", "viola", "cello")
ORCHESTRA = ("violin_1", "violin_2", "viola", "cello", "bass", "flute", "oboe",
             "clarinet", "horn", "trumpet", "harp", "timpani")
CHOIR = ("soprano", "alto", "tenor", "choral_bass")


def note_in_range(pc: int, target: int, inst: Instrument) -> int:
    """Select a pitch class in the instrument range nearest to target."""
    opts = [n for n in range(inst.low, inst.high + 1) if n % 12 == pc % 12]
    if not opts:
        raise ValueError(f"No note for {inst.key}, pc={pc}")
    return min(opts, key=lambda n: (abs(n - target), n))


def diatonic(tonic: int, mode: str, degree: int, octave_base: int) -> int:
    """A diatonic note at a degree, including degrees outside 0..6."""
    chroma = SCALES[mode][degree % 7]
    octave = degree // 7
    return note_class_near(tonic + chroma, octave_base + 12 * octave)


def note_class_near(pc: int, target: int) -> int:
    candidates = [n for n in range(target - 18, target + 19) if n % 12 == pc % 12]
    return min(candidates, key=lambda n: abs(n - target))


def chord_pcs(tonic: int, mode: str, degree: int) -> tuple[int, int, int]:
    return tuple((tonic + SCALES[mode][(degree + x) % 7]) % 12 for x in (0, 2, 4))


def key_fifths(key: str, mode: str) -> int:
    return (MINOR_FIFTHS if mode == "minor" else MAJOR_FIFTHS)[key]
