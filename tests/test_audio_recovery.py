"""Regression coverage for song downloads when ACE-Step stops or browser reloads."""
import json
import uuid
from pathlib import Path

from fastapi.testclient import TestClient
from pocket_orchestra import ace_step
from pocket_orchestra.app import app


def test_saved_mp3_is_available_without_live_ace_service(tmp_path, monkeypatch):
    import importlib
    module=importlib.import_module("pocket_orchestra.app")
    monkeypatch.setattr(module,"OUTPUTS",tmp_path)
    job_id=str(uuid.uuid4())
    job=tmp_path/job_id
    job.mkdir()
    (job/"neural_song.mp3").write_bytes(b"ID3"+b"\0"*120)
    monkeypatch.setattr(ace_step,"_request",lambda *a,**kw: (_ for _ in ()).throw(OSError("ACE stopped")))
    response=TestClient(app).get("/api/vocal/poll/"+job_id)
    assert response.status_code==200
    assert response.json()["state"]=="complete"
    assert response.json()["mp3_url"].endswith("/neural_song.mp3")
    download=TestClient(app).get(response.json()["mp3_url"])
    assert download.status_code==200
    assert download.content.startswith(b"ID3")


def test_persisted_failure_is_visible_without_running_model(tmp_path):
    (tmp_path/"neural_error.json").write_text(json.dumps(
        {"message":"Ошибка MP3: некорректный формат файла"},ensure_ascii=False),encoding="utf-8")
    value=ace_step.poll(tmp_path)
    assert value["state"]=="failed"
    assert "некорректный" in value["message"]


def test_download_error_is_not_masked_by_previous_task(tmp_path):
    (tmp_path/"neural_task.json").write_text('{"task_id":"fake"}')
    (tmp_path/"neural_error.json").write_text('{"message":"Песня не создана"}')
    assert ace_step.poll(tmp_path,download=False)["state"]=="failed"


def test_browser_saves_job_and_has_explicit_mp3_recovery():
    html=TestClient(app).get("/").text
    assert "id=\"aceCheckResult\"" in html
    assert "pocket_orchestra_last_audio_job" in html
    assert "checkSavedAudio({silent:true})" in html
    assert "showFinishedMp3(v.mp3_url)" in html
    assert "Ошибка генерации:" in html
