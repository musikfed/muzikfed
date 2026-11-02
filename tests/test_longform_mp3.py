"""Long-form tracks are real MP3s; hybrid MIDI is only an intermediate guide."""
import io
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from pocket_orchestra.app import app
from pocket_orchestra.composer import Config
from pocket_orchestra.hybrid import build_payload
from pocket_orchestra import ace_step


def job_report(tmp_path, *, bars=16, ai_duration=300, ensemble="choir", lyrics=""):
    job = tmp_path / "job"
    job.mkdir()
    config = dict(title="Далёкая звезда", prompt="Большая музыка с развитием",
                  ensemble=ensemble, key="D", mode="minor", bars=bars, tempo=94,
                  seed=42, style="opera", lyrics=lyrics, ai_duration=ai_duration)
    report = {"composition": {"config": config, "planning": {"resolved_style": "opera"}}}
    (job / "report.json").write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")
    if lyrics:
        (job / "lyrics.txt").write_text(lyrics, encoding="utf-8")
    return job


def test_mp3_duration_5_minutes_independent_of_midi_bars(tmp_path):
    job = job_report(tmp_path)
    request, note = build_payload(job)
    assert request["audio_duration"] == 300
    assert request["audio_format"] == "mp3"
    assert request["thinking"] is True
    assert "300 сек" in note


@pytest.mark.parametrize("value", [60, 120, 180, 300, 480, 600])
def test_requested_duration_is_preserved(tmp_path, value):
    job = job_report(tmp_path, ai_duration=value, ensemble="orchestra")
    data, note = build_payload(job)
    assert data["audio_duration"] == value
    assert data["lyrics"] == "[Instrumental]"
    assert data["audio_format"] == "mp3"
    if value == 600:
        assert data["thinking"] is False


def test_10min_voice_requires_own_lyrics_on_12gb(tmp_path):
    job = job_report(tmp_path, ai_duration=600)
    with pytest.raises(ValueError, match="впиши готовый текст"):
        build_payload(job)


def test_10min_russian_voice_with_lyrics_disables_lm(tmp_path):
    job = job_report(tmp_path, ai_duration=600, lyrics="Я лечу к далёкой звезде")
    data, note = build_payload(job)
    assert data["audio_duration"] == 600
    assert data["thinking"] is False
    assert data["vocal_language"] == "ru"


def test_hybrid_requires_matching_midi_duration(tmp_path):
    job = job_report(tmp_path, ai_duration=300, lyrics="Новый куплет")
    (job / "preview.wav").write_bytes(b"RIFF" + b"x" * 128)
    with pytest.raises(ValueError, match="примерно той же длины"):
        build_payload(job, "guided")


def test_actual_long_midi_bars_allow_up_to_512():
    assert Config(bars=236, ai_duration=600).bars == 236
    assert Config(bars=476, ai_duration=600).bars == 476
    with pytest.raises(ValueError):
        Config(bars=516)


def test_ai_mp3_finishes_and_deletes_temporary_hybrid_wav(tmp_path, monkeypatch):
    job = job_report(tmp_path, ai_duration=300, lyrics="Текст куплета")
    (job / "preview.wav").write_bytes(b"RIFF" + b"x" * 80)
    (job / "neural_task.json").write_text(json.dumps({
        "task_id": "fake-job", "generation_mode": "guided"
    }), encoding="utf-8")
    monkeypatch.setattr(ace_step, "_request", lambda *args, **kwargs: {
        "data": [{"status": 1, "result": json.dumps([
            {"file": "/v1/audio?path=%2Fgenerated.mp3"}
        ])}]
    })
    class Stream(io.BytesIO):
        def __enter__(self): return self
        def __exit__(self, *exc): self.close()
    data = b"ID3" + b"\0" * 8 + b"\xff\xfb" * 200000
    monkeypatch.setattr(ace_step.urllib.request, "urlopen",
                        lambda *args, **kwargs: Stream(data))
    outcome = ace_step.poll(job)
    assert outcome["state"] == "complete"
    assert (job / "neural_song.mp3").read_bytes() == data
    assert not (job / "neural_song.wav").exists()
    assert not (job / "preview.wav").exists()


def test_ai_mp3_endpoint_exposes_only_completed_mp3(tmp_path, monkeypatch):
    import importlib, uuid
    module = importlib.import_module("pocket_orchestra.app")
    monkeypatch.setattr(module, "OUTPUTS", tmp_path)
    identifier = str(uuid.uuid4())
    job = tmp_path / identifier
    job.mkdir()
    (job / "neural_song.mp3").write_bytes(b"ID3" + b"\0" * 20)
    url = f"/api/vocal/poll/{identifier}"
    result = TestClient(app).get(url)
    assert result.status_code == 200, result.text
    assert result.json()["mp3_url"].endswith("/neural_song.mp3")
    assert "wav_url" not in result.json()
    assert TestClient(app).get(f"/api/artifacts/{identifier}/neural_song.mp3").status_code == 200


def test_web_has_separate_audio_duration_and_mp3_download():
    html = TestClient(app).get("/").text
    assert 'id="aiDuration"' in html
    assert '<option value="300" selected>' in html
    assert "ai_duration:+$('aiDuration').value" in html
    assert "'neural_song.mp3'" in html
    assert "v.mp3_url" in html
    assert "d.urls.mp3" in html
    assert "guide_for_ai:mode==='guided'" in html
