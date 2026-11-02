"""Export a concert-pitch score as MIDI (with slight timing realism) and MusicXML."""
from __future__ import annotations
from collections import defaultdict
import random
from pathlib import Path
import xml.etree.ElementTree as ET
import mido
from .composer import Piece, Note
from .theory import INSTRUMENTS, key_fifths

PITCHES_SHARP = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")
PITCHES_FLAT = ("C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B")
DURATION_TYPES = {240: ("eighth", False), 480: ("quarter", False), 720: ("quarter", True),
                  960: ("half", False), 1440: ("half", True), 1920: ("whole", False)}


def _name(pitch: int, flats: bool):
    letters = PITCHES_FLAT if flats else PITCHES_SHARP
    s = letters[pitch % 12]
    return s[0], -1 if s.endswith("b") else 1 if s.endswith("#") else 0, pitch // 12 - 1


def _node(parent, tag, text=None, **attrs):
    el = ET.SubElement(parent, tag, {k: str(v) for k, v in attrs.items()})
    if text is not None:
        el.text = str(text)
    return el


def _note_xml(measure, pitch: int | None, duration_ticks: int, flats: bool, art: str = "", lyric: str = ""):
    note = _node(measure, "note")
    if pitch is None:
        _node(note, "rest")
    else:
        step, alter, octave = _name(pitch, flats)
        p = _node(note, "pitch")
        _node(p, "step", step)
        if alter:
            _node(p, "alter", alter)
        _node(p, "octave", octave)
    _node(note, "duration", duration_ticks)
    typ, dotted = DURATION_TYPES[duration_ticks]
    _node(note, "type", typ)
    if dotted:
        _node(note, "dot")
    if art in ("tenuto", "staccato", "accent") and pitch is not None:
        arts = _node(_node(note, "notations"), "articulations")
        _node(arts, art)
    if lyric and pitch is not None:
        lyr = _node(note, "lyric")
        _node(lyr, "syllabic", "single")
        _node(lyr, "text", lyric)


def write_musicxml(piece: Piece, target: Path) -> Path:
    """MusicXML 4.0 with separate staves, dynamics, tempi and choir syllables."""
    target = Path(target)
    score = ET.Element("score-partwise", {"version": "4.0"})
    work = _node(score, "work")
    _node(work, "work-title", piece.config.title)
    _node(score, "movement-title", piece.config.title)
    identification = _node(score, "identification")
    _node(identification, "creator", "Pocket Orchestra", type="composer")
    defaults = _node(score, "defaults")
    scaling = _node(defaults, "scaling")
    _node(scaling, "millimeters", 7)
    _node(scaling, "tenths", 40)
    part_list = _node(score, "part-list")
    instruments = list(piece.tracks)
    channel_map = {}
    melodic_channels = [n for n in range(16) if n != 9]
    for key in instruments:
        pgm = INSTRUMENTS[key].gm_program
        if pgm not in channel_map:
            channel_map[pgm] = melodic_channels[len(channel_map)] + 1
    for idx, key in enumerate(instruments, 1):
        inst = INSTRUMENTS[key]
        sp = _node(part_list, "score-part", id=f"P{idx}")
        _node(sp, "part-name", inst.name)
        si = _node(sp, "score-instrument", id=f"I{idx}")
        _node(si, "instrument-name", inst.name)
        mi = _node(sp, "midi-instrument", id=f"I{idx}")
        _node(mi, "midi-channel", channel_map[inst.gm_program])
        _node(mi, "midi-program", inst.gm_program + 1)

    flats = key_fifths(piece.config.key, piece.config.mode) < 0
    for idx, key in enumerate(instruments, 1):
        p = _node(score, "part", id=f"P{idx}")
        inst = INSTRUMENTS[key]
        by_bar = defaultdict(list)
        for note in piece.tracks[key]:
            by_bar[int(note.start // 4)].append(note)
        for bar in range(piece.config.bars):
            m = _node(p, "measure", number=bar + 1)
            if bar == 0:
                attrs = _node(m, "attributes")
                _node(attrs, "divisions", 480)
                ks = _node(attrs, "key")
                _node(ks, "fifths", key_fifths(piece.config.key, piece.config.mode))
                _node(ks, "mode", piece.config.mode)
                t = _node(attrs, "time")
                _node(t, "beats", 4)
                _node(t, "beat-type", 4)
                c = _node(attrs, "clef")
                _node(c, "sign", inst.clef)
                _node(c, "line", 3 if inst.clef == "C" else 4 if inst.clef == "F" else 2)
                tempo = _node(m, "direction", placement="above")
                dt = _node(tempo, "direction-type")
                met = _node(dt, "metronome")
                _node(met, "beat-unit", "quarter")
                _node(met, "per-minute", piece.config.tempo)
                _node(tempo, "sound", tempo=piece.config.tempo)
            # Explicit notated dynamics matter: MuseSounds interprets score
            # markings, not the MIDI velocities from the independent MIDI file.
            events_in_bar = by_bar[bar]
            if events_in_bar:
                average = sum(n.velocity for n in events_in_bar) / len(events_in_bar)
                label = ("pp" if average < 50 else "p" if average < 61 else "mp"
                         if average < 72 else "mf" if average < 84 else "f" if average < 97 else "ff")
                previous = by_bar.get(bar - 1, [])
                previous_average = sum(n.velocity for n in previous) / len(previous) if previous else None
                previous_label = ("pp" if previous_average < 50 else "p" if previous_average < 61 else "mp"
                                  if previous_average < 72 else "mf" if previous_average < 84 else "f"
                                  if previous_average < 97 else "ff") if previous_average is not None else None
                if label != previous_label or bar % 4 == 0:
                    direction = _node(m, "direction")
                    dyn = _node(_node(direction, "direction-type"), "dynamics")
                    _node(dyn, label)
                    _node(direction, "sound", dynamics={"pp": 31, "p": 44, "mp": 60,
                                                          "mf": 74, "f": 88, "ff": 108}[label])
            if idx == 1 and bar % 4 == 0:
                mark = _node(m, "direction", placement="above")
                _node(_node(mark, "direction-type"), "words", piece.section_names[bar])
            cursor = 0
            for event in sorted(by_bar[bar], key=lambda x: x.start):
                start = round((event.start - bar * 4) * 480)
                dur = round(event.duration * 480)
                if start < cursor or start + dur > 1920:
                    raise ValueError(f"Overlapping or overflowing notes in {key}, bar {bar + 1}")
                if start > cursor:
                    _note_xml(m, None, start - cursor, flats)
                _note_xml(m, event.pitch, dur, flats, event.articulation, event.lyric)
                cursor = start + dur
            if cursor < 1920:
                _note_xml(m, None, 1920 - cursor, flats)
    ET.indent(score, space="  ")
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = ET.tostring(score, encoding="utf-8", xml_declaration=True)
    target.write_bytes(payload)
    return target


def write_midi(piece: Piece, target: Path) -> Path:
    """Type-1 MIDI. Musical event lengths remain exact in MusicXML.

    Tracks with the same General MIDI program share one channel, avoiding the
    16-channel limit while keeping one editable MIDI track per instrument.
    """
    target = Path(target)
    mid = mido.MidiFile(type=1, ticks_per_beat=480)
    conductor = mido.MidiTrack()
    mid.tracks.append(conductor)
    conductor.append(mido.MetaMessage("track_name", name="Conductor", time=0))
    conductor.append(mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(piece.config.tempo), time=0))
    conductor.append(mido.MetaMessage("time_signature", numerator=4, denominator=4, time=0))
    conductor.append(mido.MetaMessage("key_signature", key=piece.config.key + ("m" if piece.config.mode == "minor" else ""), time=0))
    conductor.append(mido.MetaMessage("end_of_track", time=0))
    # Channel 9 is drums, and must not receive pitched timpani data.
    melodic_channels = [n for n in range(16) if n != 9]
    program_channels = {}
    for key in piece.tracks:
        program = INSTRUMENTS[key].gm_program
        if program not in program_channels:
            program_channels[program] = melodic_channels[len(program_channels)]
    rng = random.Random(piece.config.seed + 12345)
    for key, notes in piece.tracks.items():
        track = mido.MidiTrack()
        mid.tracks.append(track)
        inst = INSTRUMENTS[key]
        channel = program_channels[inst.gm_program]
        track.append(mido.MetaMessage("track_name", name=key, time=0))
        track.append(mido.Message("program_change", channel=channel, program=inst.gm_program, time=0))
        events = []
        for note in notes:
            dither = rng.uniform(-.032, .032) * piece.config.humanize
            s = max(0, round((note.start + dither) * 480))
            e = max(s + 30, round((note.start + note.duration - .035 * piece.config.humanize) * 480))
            events += [(s, 1, note.pitch, note.velocity), (e, 0, note.pitch, 0)]
        events.sort(key=lambda x: (x[0], x[1]))
        cursor = 0
        for tick, on, pitch, velocity in events:
            track.append(mido.Message("note_on" if on else "note_off", channel=channel,
                                      note=pitch, velocity=velocity, time=tick - cursor))
            cursor = tick
        track.append(mido.MetaMessage("end_of_track", time=0))
    target.parent.mkdir(parents=True, exist_ok=True)
    mid.save(str(target))
    return target
