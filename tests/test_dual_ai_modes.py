"""Regression checks for explicit score, independent neural song and MIDI-guided AI mode."""
import json
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from pocket_orchestra import gpu_control
from pocket_orchestra.ai_score import apply_counterpoint, validate_proposal
from pocket_orchestra.composer import Config, compose
from pocket_orchestra.hybrid import build_payload
from pocket_orchestra.app import app

PROPOSAL = {
    "upper_a": [[0, 2, 4, 3], [4, 3, 1, 2], [4, 5, 2, 1], [2, 3, 1, 0]],
    "upper_b": [[4, 2, 3, 5], [3, 4, 2, 1], [4, 3, 2, 0], [2, 1, 0, 0]],
    "lower_a": [[0, 3], [3, 5], [1, 4], [2, 0]],
    "lower_b": [[1, 3], [0, 4], [5, 2], [4, 0]],
}


def test_ai_score_rejects_fake_or_repeated_voices():
    with pytest.raises(ValueError):
        validate_proposal({"upper_a": [0, 1]})
    bad = {k: [bar[:] for bar in v] for k, v in PROPOSAL.items()}
    bad["lower_a"] = [[bar[0], 0] for bar in bad["upper_a"]]
    with pytest.raises(ValueError, match="независимые"):
        validate_proposal(bad)


def test_ai_changes_real_score_notes_and_preserves_other_parts():
    cfg = Config(ensemble="orchestra", bars=16, score_engine="ai_polyphony")
    piece = compose(cfg)
    previous_lead = piece.tracks["violin_1"][:]
    previous_second = piece.tracks["violin_2"][:]
    apply_counterpoint(piece, PROPOSAL)
    assert piece.tracks["violin_1"] != previous_lead
    assert piece.tracks["violin_2"] == previous_second
    assert len(piece.tracks["violin_1"]) == 16 * 4
    assert len(piece.tracks["cello"]) == 16 * 2
    assert piece.planning["ai_counterpoint"]["source"] == "ollama_note_level"
    assert piece.planning["ai_counterpoint"]["guaranteed_bach_quality"] is False


def test_neural_song_prompt_has_semantics_without_fake_lyrics(tmp_path):
    job = tmp_path / "job"
    job.mkdir()
    data = {"composition": {"config": {
        "ensemble": "orchestra_choir", "title": "Морское путешествие",
        "prompt": "Женский оперный голос о морском шторме и победе",
        "bars": 16, "tempo": 94, "key": "D", "mode": "minor", "style": "opera",
        "seed": 42,
    }, "planning": {"resolved_style": "opera"}}}
    (job / "report.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    payload, note = build_payload(job, "original")
    assert payload["task_type"] if "task_type" in payload else "text2music"
    assert "морском шторме" in payload["prompt"]
    assert payload.get("sample_mode") is not True  # no unrelated random samples
    assert "Original Russian lyrics" in payload["sample_query"]
    assert "заря" not in payload["lyrics"]
    assert payload["vocal_language"] == "ru"
    with pytest.raises(ValueError, match="впиши свой текст"):
        build_payload(job, "guided")

    (job / "lyrics.txt").write_text("Ветер качает корабли", encoding="utf-8")
    (job / "preview.wav").write_bytes(b"RIFF" + b"0" * 100)
    guided, note = build_payload(job, "guided")
    assert guided["task_type"] == "cover"
    assert guided["src_audio_path"].endswith("preview.wav")
    assert guided["lyrics"] == "Ветер качает корабли"
    assert "может менять" in note


def test_instrumental_ai_is_not_forced_to_sing(tmp_path):
    job = tmp_path / "j"
    job.mkdir()
    (job / "report.json").write_text(json.dumps({"composition": {"config": {
        "ensemble": "orchestra", "prompt": "Чисто симфоническая сюита",
        "bars": 24, "tempo": 110, "mode": "major", "key": "G", "seed": 10}}}),
        encoding="utf-8")
    p, _ = build_payload(job)
    assert p["lyrics"] == "[Instrumental]"
    assert "Instrumental only" in p["prompt"]


def test_gpu_lease_prevents_parallel_jobs_and_releases(tmp_path, monkeypatch):
    monkeypatch.setattr(gpu_control, "RUNTIME", tmp_path)
    monkeypatch.setattr(gpu_control, "LOCK", tmp_path / "lock")
    monkeypatch.setattr(gpu_control, "LEASE", tmp_path / "active.json")
    monkeypatch.setattr(gpu_control, "unload_ollama", lambda _: None)
    monkeypatch.setattr(gpu_control, "_unit_installed", lambda: False)
    gpu_control.claim_audio("first")
    assert gpu_control.state()["audio_job_active"]
    with pytest.raises(RuntimeError):
        gpu_control.before_score()
    with pytest.raises(RuntimeError):
        gpu_control.claim_audio("second")
    gpu_control.release_audio("first")
    assert not gpu_control.state()["audio_job_active"]
    gpu_control.before_score()


def test_web_has_three_real_actions_and_explicit_score_engine():
    html = TestClient(app).get("/").text
    assert 'id="go"' in html
    assert 'id="aceGenerate"' in html
    assert 'id="aceHybrid"' in html
    assert 'id="scoreEngine"' in html
    assert "score_engine:$('scoreEngine').value" in html
    assert "createAiSong('original')" in html
    assert "createAiSong('guided')" in html


def test_orchestra_api_ai_mode_uses_mocked_note_level_model(monkeypatch):
    import importlib
    app_module = importlib.import_module("pocket_orchestra.app")
    monkeypatch.setattr(app_module.gpu_control, "before_score", lambda: None)
    monkeypatch.setattr(app_module.gpu_control, "unload_ollama", lambda _: None)
    monkeypatch.setattr(app_module, "generate_counterpoint", lambda cfg: PROPOSAL)
    monkeypatch.setattr(app_module, "generate_plan", lambda cfg: {"progression_a":[0,5,2,4],"progression_b":[3,5,4,0],"motif":[4,3,2,0],"source":"ollama:mock"})
    r = TestClient(app).post("/api/generate", json={
        "config": {"ensemble": "orchestra", "bars": 8,
                   "score_engine": "ai_polyphony"},
        "render_preview": False,
    })
    assert r.status_code == 200, r.text
    assert r.json()["composition"]["planning"]["ai_counterpoint"]["source"] == "ollama_note_level"
    assert r.json()["composition"]["planning"]["source"] == "ollama:mock"


def test_direct_neural_song_project_does_not_compose_fake_midi():
    from pocket_orchestra.app import app
    c = TestClient(app)
    response = c.post("/api/audio/project", json={"config": {
        "ensemble": "orchestra_choir", "title": "Тайна моря",
        "prompt": "Оперная песня о морских путешествиях", "lyrics": "Река несёт мечты",
        "bars": 16, "style": "opera"},
        "render_preview": False})
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["engine"] == "ace-step"
    assert data["mode"] == "original"
    report = c.get(f"/api/artifacts/{data['job_id']}/report.json").json()
    assert report["composition"]["config"]["prompt"] == "Оперная песня о морских путешествиях"
    assert report["source_midi"] is None
    assert c.get(f"/api/artifacts/{data['job_id']}/score.mid").status_code == 404
    lyrics = c.get(f"/api/artifacts/{data['job_id']}/lyrics.txt").text
    assert "Река несёт мечты" in lyrics


def test_original_song_web_calls_direct_endpoint():
    page = TestClient(app).get("/").text
    assert "mode==='guided'?'/api/generate':'/api/audio/project'" in page
    assert "mode==='original'" in page


def test_server_watcher_releases_gpu_after_audio_even_if_browser_closed(tmp_path, monkeypatch):
    import importlib
    module = importlib.import_module("pocket_orchestra.app")
    released = []
    monkeypatch.setattr(module, "_jobdir", lambda job_id: tmp_path)
    monkeypatch.setattr(module.ace_step, "poll", lambda job: {
        "state": "complete", "url_ready": True
    })
    monkeypatch.setattr(module.gpu_control, "release_audio",
                        lambda job_id: released.append(job_id))
    monkeypatch.setattr("time.sleep", lambda _: None)
    module._watch_audio_job("audio-1")
    assert released == ["audio-1"]


def test_browser_status_avoids_duplicate_mp3_download(tmp_path, monkeypatch):
    import importlib
    module = importlib.import_module("pocket_orchestra.app")
    monkeypatch.setattr(module, "_jobdir", lambda job_id: tmp_path)
    called = []
    def fake_poll(path, *, download=True):
        called.append(download)
        return {"state": "working", "url_ready": False}
    monkeypatch.setattr(module.ace_step, "poll", fake_poll)
    r = TestClient(app).get("/api/vocal/poll/12345678-1234-1234-1234-123456789abc")
    assert r.status_code == 200
    assert called == [False]
