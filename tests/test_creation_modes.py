"""The three UI production groups map only to ensembles implemented in v0.1.

Voice and voice+orchestra are still SATB notation with optional lyrics; do not
claim SF2 preview audio articulates Russian words. ACE-Step is separately optional.
"""
from pathlib import Path

WEB = (Path(__file__).resolve().parents[1] / "web/index.html").read_text(encoding="utf-8")


def test_creation_mode_choices_and_group_mapping():
    assert 'id="creationMode"' in WEB
    assert '<option value="instrumental">' in WEB
    assert '<option value="vocal">' in WEB
    assert '<option value="combined">' in WEB
    assert "instrumental:{ensembles:['orchestra','quartet','chiptune','synthwave']" in WEB
    assert "vocal:{ensembles:['choir']" in WEB
    assert "combined:{ensembles:['orchestra_choir','quartet_choir']" in WEB


def test_no_misleading_lyric_claim_in_ui():
    assert "Черновой WAV ещё не поёт русский текст" in WEB
    assert "синхронизированных отдельных вокальных WAV-стемов пока нет" in WEB
    assert "Пока ACE-Step не установлена, голосового WAV нет" in WEB
    assert "FluidSynth не произносит русский текст" in WEB
    assert 'id="aceGenerate"' in WEB


def test_first_run_defaults_to_orchestra_without_ollama():
    assert '<option value="orchestra" selected>' in WEB
    assert '<input type="checkbox" id="useOllama">' in WEB
    assert '<input type="checkbox" id="render" checked>' in WEB
    assert "$('creationMode').addEventListener('change',selectCreationMode)" in WEB
