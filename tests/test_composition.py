from pathlib import Path
import xml.etree.ElementTree as ET
import mido
import pytest
from pocket_orchestra.composer import Config, compose, instrumentation
from pocket_orchestra.harmony import optimize_satb
from pocket_orchestra.export import write_musicxml, write_midi
from pocket_orchestra.quality import inspect

@pytest.mark.parametrize("ensemble", ["quartet", "orchestra", "choir", "orchestra_choir", "quartet_choir"])
@pytest.mark.parametrize("key,mode", [("D", "minor"), ("C", "major"), ("Ab", "major"), ("F#", "minor")])
def test_midi_and_musicxml(tmp_path, ensemble, key, mode):
    cfg = Config(title="Проверка", ensemble=ensemble, key=key, mode=mode, bars=8, seed=7)
    piece = compose(cfg)
    optimize_satb(piece)
    report = inspect(piece)
    assert all(x["ok"] for x in report["checks"]), report
    assert len(piece.tracks) == len(instrumentation(ensemble))
    xml = write_musicxml(piece, tmp_path / "work.musicxml")
    midi = write_midi(piece, tmp_path / "work.mid")
    root = ET.parse(xml).getroot()
    assert root.tag == "score-partwise"
    assert len(root.findall("part")) == len(piece.tracks)
    for part in root.findall("part"):
        assert len(part.findall("measure")) == cfg.bars
    obj = mido.MidiFile(midi)
    assert len(obj.tracks) == len(piece.tracks) + 1
    assert sum(x.type == "note_on" and x.velocity > 0 for tr in obj.tracks for x in tr) > 50


def test_prompt_changes_orchestration():
    cfg = Config(prompt="Тревожное начало у виолончелей, хор только в кульминации, в конце тихая кода")
    piece = compose(cfg)
    assert min(n.start for n in piece.tracks["cello"]) == 0
    assert min(n.start for n in piece.tracks["violin_1"]) >= 16
    assert piece.planning["prompt_cues"]["quiet_coda"]
    optimize_satb(piece)
    assert min(n.start for n in piece.tracks["soprano"]) >= cfg.bars * 2
    assert inspect(piece)["passed"] == inspect(piece)["total"]


def test_reproducible_midi(tmp_path):
    cfg = Config(ensemble="quartet", seed=10)
    p1 = compose(cfg)
    p2 = compose(cfg)
    assert p1.tracks == p2.tracks
    assert compose(Config(ensemble="quartet", seed=11)).tracks != p1.tracks
    assert write_midi(p1, tmp_path / "1.mid").read_bytes() == write_midi(p2, tmp_path / "2.mid").read_bytes()


@pytest.mark.parametrize("invalid", [
    {"ensemble": "rock_band"}, {"mode": "jazz"}, {"tempo": 300}, {"bars": 17},
    {"key": "H"}, {"seed": -1}, {"density": 8}, {"choir_entry": 1.1}, {"brass_level": 2}, {"choir_vowel": "la"},
    {"other": 55}, {"title": ""},
])
def test_invalid_config(invalid):
    with pytest.raises(ValueError):
        Config.from_dict(invalid)


def test_no_ollama_required():
    cfg = Config()
    piece = compose(cfg)
    assert piece.planning["source"] == "rule_based"
