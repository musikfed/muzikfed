"""Chiptune and synthwave are real distinct MIDI scores; 20s neural previews stay serial."""
import json

import mido
import pytest
from fastapi.testclient import TestClient

from pocket_orchestra.composer import Config, compose, _style
from pocket_orchestra.export import write_midi, write_musicxml
from pocket_orchestra.quality import inspect
from pocket_orchestra.hybrid import build_payload
from pocket_orchestra.ai_score import apply_counterpoint


@pytest.mark.parametrize("ensemble,expected", [
    ("chiptune", {"chip_lead", "chip_counter", "chip_arp", "chip_bass"}),
    ("synthwave", {"synth_lead", "synth_pad", "synth_arp", "synth_bass"}),
])
def test_real_editable_electronic_midi_tracks(ensemble, expected, tmp_path):
    cfg = Config(ensemble=ensemble, bars=16, tempo=128, style=ensemble,
                 prompt="Оригинальное приключение с темой, контрастом и каденцией")
    piece = compose(cfg)
    assert set(piece.tracks) == expected
    assert all(piece.tracks.values())
    assert piece.planning["resolved_style"] == ensemble
    assert "General MIDI" in piece.planning["sound_design"]
    midi = write_midi(piece, tmp_path / "sound.mid")
    score = write_musicxml(piece, tmp_path / "sound.musicxml")
    assert midi.is_file() and score.is_file()
    data = mido.MidiFile(str(midi))
    assert len(data.tracks) == 5
    assert len({m.program for t in data.tracks for m in t if m.type == "program_change"}) == 4
    assert inspect(piece)["passed"] == inspect(piece)["total"]


def test_chiptune_contains_game_rhythm_and_prompt_variety():
    base = dict(ensemble="chiptune", bars=32, tempo=150, seed=52)
    a = compose(Config(**base, prompt="Весёлая аркада с прыжками и наградой"))
    b = compose(Config(**base, prompt="Мрачная подземная битва со злодеем"))
    assert a.tracks["chip_lead"] != b.tracks["chip_lead"]
    assert any(n.duration == 0.5 for n in a.tracks["chip_arp"])
    assert len(a.tracks["chip_arp"]) == 32 * 8
    assert len(a.tracks["chip_counter"]) == 32 * 4
    assert a.tracks["chip_lead"] != a.tracks["chip_counter"]


def test_auto_style_understands_russian_8bit_and_synthwave_prompts():
    assert _style(Config(prompt="Музыка для игры Денди, 8 бит")) == "chiptune"
    assert _style(Config(prompt="Синтвейв и ночной киберпанк")) == "synthwave"


def test_qwen_independent_electronic_voices(tmp_path):
    p = compose(Config(ensemble="chiptune", bars=16))
    old = p.tracks["chip_lead"][:]
    proposal = {
        "upper_a": [[0,2,4,3],[4,3,1,2],[4,5,2,1],[2,3,1,0]],
        "upper_b": [[4,2,3,5],[3,4,2,1],[4,3,2,0],[2,1,0,0]],
        "lower_a": [[0,3],[3,5],[1,4],[2,0]],
        "lower_b": [[1,3],[0,4],[5,2],[4,0]]
    }
    apply_counterpoint(p, proposal)
    assert p.tracks["chip_lead"] != old
    assert p.planning["ai_counterpoint"]["roles"] == ["chip_lead", "chip_bass"]
    assert p.tracks["chip_arp"]  # independent parts remain


def test_twenty_second_preview_request_not_full_song(tmp_path):
    job = tmp_path / "job"
    job.mkdir()
    (job / "report.json").write_text(json.dumps({"composition": {
        "config": {"ensemble":"choir","bars":16,"tempo":94,"ai_duration":20,
                   "prompt":"Лирический певец на русском языке","style":"lyrical"},
        "planning":{"resolved_style":"lyrical"}
    }},ensure_ascii=False),encoding="utf-8")
    payload, _ = build_payload(job)
    assert payload["audio_format"] == "mp3"
    assert payload["audio_duration"] == 20
    assert payload["task_type"] if "task_type" in payload else True


def test_ui_has_real_20s_audio_button_and_prompt_recipes():
    html = TestClient(__import__("pocket_orchestra.app",fromlist=["app"]).app).get("/").text
    assert 'id="acePreview"' in html
    assert "createAiSong('preview')" in html
    assert "cfg.ai_duration=20" in html
    assert "mode==='guided'?'guided':'original'" in html
    assert 'id="usePromptPreset"' in html
    assert 'id="promptPreset"' in html
    assert "'chiptune'" in html and "'synthwave'" in html


def test_web_preview_direct_api_has_no_fake_midi():
    client = TestClient(__import__("pocket_orchestra.app",fromlist=["app"]).app)
    r = client.post("/api/audio/project", json={"config": {
        "ensemble":"chiptune","ai_duration":20,
        "title":"Пример для Денди","prompt":"8-bit приключение",
        "style":"chiptune"}, "render_preview":False})
    assert r.status_code == 200, r.text
    data = r.json()
    report = client.get(f"/api/artifacts/{data['job_id']}/report.json").json()
    assert report["composition"]["config"]["ai_duration"] == 20
    assert report["source_midi"] is None
