"""Optional local ACE-Step bridge tests: no model, GPU or network required."""
import io
import json
from pathlib import Path

from fastapi.testclient import TestClient

from pocket_orchestra.app import app
from pocket_orchestra import ace_step

client = TestClient(app)


def test_optional_engine_status_unavailable(monkeypatch):
    monkeypatch.setattr(ace_step, "_request",
                        lambda path, **kwargs: (_ for _ in ()).throw(OSError("not running")))
    r = client.get("/api/vocal/status")
    assert r.status_code == 200
    assert r.json()["available"] is False


def test_bridged_song_creates_local_wav(tmp_path, monkeypatch):
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
                "file": "/v1/audio?path=%2Ftmp%2Fexample.wav"}])}]}
        raise AssertionError(path)

    class FakeStream(io.BytesIO):
        def __enter__(self): return self
        def __exit__(self, *args): self.close()

    wav_bytes = b"RIFF" + (40).to_bytes(4, "little") + b"WAVEfmt " + b"\0" * 36
    monkeypatch.setattr(ace_step, "_request", api_request)
    monkeypatch.setattr(ace_step.urllib.request, "urlopen",
                        lambda *args, **kwargs: FakeStream(wav_bytes))
    task = ace_step.start(job)
    assert task["state"] == "queued"
    assert task["audio_mode"] == "a_cappella_requested"
    assert calls[0][1]["vocal_language"] == "ru"
    assert calls[0][1]["audio_format"] == "wav"
    assert "a cappella" in calls[0][1]["prompt"]
    result = ace_step.poll(job)
    assert result["url_ready"]
    assert (job / "neural_song.wav").read_bytes() == wav_bytes
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
