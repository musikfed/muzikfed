"""New composition diversity, editable Russian lyrics and durable UI controls."""
from pathlib import Path
import xml.etree.ElementTree as ET

from fastapi.testclient import TestClient

from pocket_orchestra.app import app
from pocket_orchestra.composer import Config, compose
from pocket_orchestra.lyrics import draft_lyrics, annotate_score_lyrics
from pocket_orchestra.export import write_musicxml


def test_same_inputs_reproducible_but_prompt_changes_score():
    base = dict(ensemble="orchestra", bars=16, seed=42)
    a = compose(Config(**base, title="Марш великанов", prompt="Торжественный марш"))
    b = compose(Config(**base, title="Марш великанов", prompt="Торжественный марш"))
    c = compose(Config(**base, title="Вечерняя лирика", prompt="Тихий нежный романс"))
    assert a.tracks == b.tracks
    assert a.harmony == b.harmony
    assert a.tracks["violin_1"] != c.tracks["violin_1"]
    assert a.planning["resolved_style"] == "march"
    assert c.planning["resolved_style"] == "lyrical"
    assert a.planning["composition_signature"] != c.planning["composition_signature"]


def test_style_validation_and_unique_seed():
    from pytest import raises
    with raises(ValueError):
        Config(style="unknown")
    with raises(ValueError):
        Config(lyrics="x" * 4001)
    cfg = dict(ensemble="quartet", prompt="Торжественное шествие")
    signatures = {compose(Config(**cfg, seed=seed)).planning["composition_signature"]
                  for seed in range(12)}
    assert len(signatures) == 12


def test_lyrics_as_text_and_musicxml_not_as_fake_sung_audio(tmp_path):
    custom = "Пусть поднимется солнце над нами\nПусть сияет простор впереди"
    cfg = Config(ensemble="choir", lyrics=custom, bars=8)
    piece = compose(cfg)
    text = draft_lyrics(cfg)
    assert text == custom
    assert annotate_score_lyrics(piece, text) > 0
    xml = write_musicxml(piece, tmp_path / "score.musicxml")
    root = ET.parse(xml).getroot()
    assert root.findall(".//lyric/text")
    assert any(el.text == "Пусть" for el in root.findall(".//lyric/text"))


def test_choir_job_returns_lyrics_but_not_sung_voice():
    client = TestClient(app)
    response = client.post("/api/generate", json={"config": {
        "ensemble": "choir", "bars": 8, "lyrics": "Ветер зовёт нас домой",
        "style": "opera", "use_ollama": False
    }, "render_preview": False})
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["lyrics"] == "Ветер зовёт нас домой"
    assert data["lyrics_sung"] is False
    assert "lyrics.txt" in data["urls"]
    assert client.get(data["urls"]["lyrics.txt"]).content.decode().strip() == "Ветер зовёт нас домой"


def test_instrumental_has_no_lyrics_file():
    client = TestClient(app)
    r = client.post("/api/generate", json={"config": {
        "ensemble": "orchestra", "bars": 8, "lyrics": "любые слова",
        "use_ollama": False
    }, "render_preview": False})
    assert r.status_code == 200, r.text
    assert "lyrics.txt" not in r.json()["urls"]


def test_ui_persists_in_browser_and_has_reset():
    client = TestClient(app)
    html = client.get("/").text
    assert "localStorage.setItem(SETTINGS_KEY" in html
    assert "localStorage.getItem(SETTINGS_KEY" in html
    assert 'id="resetSettings"' in html
    assert 'id="lyrics"' in html
    assert 'id="style"' in html
    assert 'id="lyricsLink"' in html
