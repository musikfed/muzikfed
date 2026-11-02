"""Optional local ACE-Step bridge tests: no model, GPU or network required."""
import io
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from pocket_orchestra.app import app
from pocket_orchestra import ace_step, gpu_control

client = TestClient(app)


@pytest.mark.parametrize("installed", [False, True])
def test_optional_engine_status_unavailable(monkeypatch, installed):
    """Test both CORE states without probing the runner's REAL systemd home.

    A workstation with no ACE unit must be unavailable; CORE with a unit
    installed but intentionally stopped must remain startable from the UI.
    """
    monkeypatch.setattr(ace_step, "_request",
                        lambda path, **kwargs: (_ for _ in ()).throw(OSError("not running")))
    monkeypatch.setattr(gpu_control, "state", lambda: {
        "ace_installed": installed, "audio_job_active": False,
        "score_job_active": False, "gpu_owner": "idle", "job_id": None,
    })
    r = client.get("/api/vocal/status")
    assert r.status_code == 200
    state = r.json()
    assert state["available"] is installed
    assert state["running"] is False
    assert state["ace_installed"] is installed
    if installed:
        assert "запускается по кнопке" in state["message"]


def test_optional_engine_running_without_user_systemd_unit(monkeypatch):
    """Live health also grants availability even if systemd is not detected."""
    monkeypatch.setattr(ace_step, "_request",
                        lambda path, **kwargs: {"data": {"status": "ok"}})
    monkeypatch.setattr(gpu_control, "state", lambda: {
        "ace_installed": False, "audio_job_active": False,
        "score_job_active": False, "gpu_owner": "idle", "job_id": None,
    })
    result = client.get("/api/vocal/status")
    assert result.status_code == 200
    assert result.json()["available"] is True
    assert result.json()["running"] is True


def test_bridged_song_creates_local_mp3(tmp_path, monkeypatch):
    job = tmp_path / "job"
    job.mkdir()
    report = {"composition": {"config": {
        "bars": 16, "tempo": 94, "ensemble": "choir", "style": "opera",
        "prompt": "Песнь о рассвете"}, "planning": {"resolved_style": "opera"}}}
    (job / "report.json").write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")
    (job / "lyrics.txt").write_text("Пусть сияет рассвет над нами", encoding="utf-8")
    calls = []

    def api_request(path, payload=None, **kwargs):
        calls.append((path, payload))
        if path == "/release_task":
            return {"data": {"task_id": "550e8400-e29b-41d4-a716-446655440000"}}
        if path == "/query_result":
            return {"data": [{"status": 1, "result": json.dumps([{
                "file": "/v1/audio?path=%2Ftmp%2Fexample.mp3"}])}]}
        raise AssertionError(path)

    class FakeStream(io.BytesIO):
        def __enter__(self): return self
        def __exit__(self, *args): self.close()

    mp3_bytes = b"ID3" + b"\0" * 20 + b"\xff\xfb" * 64
    monkeypatch.setattr(ace_step, "_request", api_request)
    monkeypatch.setattr(ace_step.urllib.request, "urlopen",
                        lambda *args, **kwargs: FakeStream(mp3_bytes))
    task = ace_step.start(job)
    assert task["state"] == "queued"
    assert task["audio_mode"] == "a_cappella_requested"
    assert calls[0][1]["vocal_language"] == "ru"
    assert calls[0][1]["audio_format"] == "mp3"
    assert "a cappella" in calls[0][1]["prompt"]
    result = ace_step.poll(job)
    assert result["url_ready"]
    assert (job / "neural_song.mp3").read_bytes() == mp3_bytes
    assert not (job / "neural_song.wav").exists()
    assert ace_step.poll(job)["state"] == "complete"


def test_blocks_untrusted_audio_urls(tmp_path, monkeypatch):
    path = tmp_path / "job"
    path.mkdir()
    (path / "neural_task.json").write_text('{"task_id":"example-task"}')
    monkeypatch.setattr(ace_step, "_request", lambda *args, **kwargs: {
        "data": [{"status": 1, "result": json.dumps([{
            "file": "http://untrusted.example/steal"}])}]})
    from pytest import raises
    with raises(ValueError, match="Небезопасный"):
        ace_step.poll(path)


def test_vocal_poll_requires_existing_job():
    r = client.get("/api/vocal/poll/not-a-uuid")
    assert r.status_code == 400


def test_dashboard_exposes_optional_neural_controls():
    page = client.get("/").text
    assert 'id="aceGenerate"' in page
    assert 'id="aceStatus"' in page
    assert "/api/vocal/status" in page


def test_completed_neural_mp3_is_downloadable(tmp_path, monkeypatch):
    import importlib
    import uuid
    module = importlib.import_module("pocket_orchestra.app")
    monkeypatch.setattr(module, "OUTPUTS", tmp_path)
    job_id = str(uuid.uuid4())
    out = tmp_path / job_id
    out.mkdir()
    mp3 = b"ID3" + b"\0" * 20 + b"\xff\xfb" * 64
    (out / "neural_song.mp3").write_bytes(mp3)
    response = client.get(f"/api/artifacts/{job_id}/neural_song.mp3")
    assert response.status_code == 200, response.text
    assert response.content == mp3


def test_songwriter_lyrics_are_saved_from_real_ace_response(tmp_path, monkeypatch):
    """Prompt-only songs receive exactly the words generated by ACE, not a template."""
    (tmp_path / "neural_task.json").write_text('{"task_id":"demo-task"}')
    payload = {"data": [{"status": 1, "result": json.dumps([{
        "file": "/v1/audio?path=%2Ftmp%2Fgenerated.mp3",
        "lyrics": "[Verse]\\nПой мне, ветер, о море\\n[Chorus]\\nВернусь домой",
    }], ensure_ascii=False)}]}
    monkeypatch.setattr(ace_step, "_request", lambda *args, **kwargs: payload)

    class FakeStream(io.BytesIO):
        def __enter__(self): return self
        def __exit__(self, *args): self.close()

    sound = b"ID3" + b"\0" * 20 + b"\xff\xfb" * 64
    monkeypatch.setattr(ace_step.urllib.request, "urlopen",
                        lambda *args, **kwargs: FakeStream(sound))
    result = ace_step.poll(tmp_path)
    assert result["state"] == "complete"
    lyrics = (tmp_path / "lyrics.txt").read_text(encoding="utf-8")
    assert "Пой мне, ветер, о море" in lyrics
    assert "Вернусь домой" in lyrics
    assert "я мартышка" not in lyrics
