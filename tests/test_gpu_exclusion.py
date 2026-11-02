"""Verify that Qwen and ACE-Step never get cooperative leases simultaneously.

No NVIDIA card or real Ollama server is required: this tests the exact file
reservation and stop ordering used by CORE's FastAPI workers.
"""
import json

import pytest
from fastapi.testclient import TestClient

from pocket_orchestra import gpu_control
from pocket_orchestra.app import app


@pytest.fixture
def clean_gpu(tmp_path, monkeypatch):
    monkeypatch.setattr(gpu_control, "RUNTIME", tmp_path)
    monkeypatch.setattr(gpu_control, "LOCK", tmp_path / "gpu-control.lock")
    monkeypatch.setattr(gpu_control, "LEASE", tmp_path / "gpu-audio-active.json")
    monkeypatch.setattr(gpu_control, "SCORE_LEASE", tmp_path / "gpu-score-active.json")
    monkeypatch.setattr(gpu_control, "_unit_installed", lambda: False)
    released = []
    monkeypatch.setattr(gpu_control, "unload_ollama", lambda model: released.append(model))
    return released


def test_qwen_reserves_gpu_for_entire_composition_and_blocks_audio(clean_gpu):
    with gpu_control.score_session("qwen3:8b"):
        status = gpu_control.state()
        assert status["gpu_owner"] == "qwen"
        assert status["score_job_active"]
        assert not status["audio_job_active"]
        with pytest.raises(RuntimeError, match="Qwen"):
            gpu_control.claim_audio("song-1")
        with pytest.raises(RuntimeError, match="другой партитурой Qwen"):
            with gpu_control.score_session("qwen3:8b"):
                pass
    assert clean_gpu == ["qwen3:8b"]
    assert gpu_control.state()["gpu_owner"] == "idle"
    gpu_control.claim_audio("song-1")
    assert gpu_control.state()["gpu_owner"] == "ace-step"
    gpu_control.release_audio("song-1")
    assert gpu_control.state()["gpu_owner"] == "idle"


def test_score_lease_is_cleared_after_model_error(clean_gpu):
    with pytest.raises(ValueError, match="bad composition"):
        with gpu_control.score_session("qwen3:8b"):
            raise ValueError("bad composition")
    assert clean_gpu == ["qwen3:8b"]
    assert gpu_control.state()["gpu_owner"] == "idle"


def test_audio_lease_blocks_qwen_until_release(clean_gpu):
    gpu_control.claim_audio("song-2")
    assert gpu_control.state()["audio_job_active"]
    with pytest.raises(RuntimeError, match="ACE-Step"):
        with gpu_control.score_session("qwen3:8b"):
            pass
    gpu_control.release_audio("song-2")
    with gpu_control.score_session("qwen3:8b"):
        assert gpu_control.state()["gpu_owner"] == "qwen"


def test_audio_service_stops_before_gpu_lease_is_released(clean_gpu, monkeypatch):
    observed = []
    monkeypatch.setattr(gpu_control, "_unit_installed", lambda: True)

    def fake_ctl(*action, **kwargs):
        assert action == ("stop",)
        observed.append(gpu_control._active())
    monkeypatch.setattr(gpu_control, "_systemctl", fake_ctl)
    gpu_control.claim_audio("song-3")
    gpu_control.release_audio("song-3")
    assert observed[0]["job_id"] == "song-3"
    assert gpu_control.state()["gpu_owner"] == "idle"


def test_unavailable_qwen_and_ace_voice_status_are_separate(clean_gpu, monkeypatch):
    import importlib
    module = importlib.import_module("pocket_orchestra.app")
    monkeypatch.setattr(module.ace_step, "status",
                        lambda: {"available": False, "message": "Не запущена"})
    result = TestClient(app).get("/api/vocal/status")
    assert result.status_code == 200
    payload = result.json()
    assert payload["gpu_owner"] == "idle"
    assert "score_job_active" in payload


def test_frontend_indicates_qwen_occupancy():
    html = TestClient(app).get("/").text
    assert "d.score_job_active?'RTX занята партитурой Qwen'" in html
    assert "||!!d.score_job_active" in html
