"""Regression tests: do not claim AI engines are installed or HTTP-ready without evidence."""
from pathlib import Path
import io
import json

from fastapi.testclient import TestClient
from pocket_orchestra.app import app
from pocket_orchestra import engines

ROOT = Path(__file__).resolve().parents[1]


def test_ollama_engine_status_when_offline(monkeypatch):
    def offline(*args, **kwargs):
        raise ConnectionError("refused")
    monkeypatch.setattr(engines.urllib.request, "urlopen", offline)
    result = engines.ollama_status()
    assert result["model_installed"] is False
    assert result["ollama_running"] is False
    assert result["loaded_in_gpu"] is None


def test_ollama_engine_status_when_qwen_is_installed(monkeypatch):
    class FakeResponse(io.BytesIO):
        def __enter__(self): return self
        def __exit__(self, *args): self.close()
    def fake_open(*args, **kwargs):
        return FakeResponse(json.dumps({"models": [{"name": "qwen3:8b"}]}).encode())
    monkeypatch.setattr(engines.urllib.request, "urlopen", fake_open)
    result = engines.ollama_status()
    assert result["model_installed"] is True
    assert result["model"] == "qwen3:8b"
    assert result["loaded_in_gpu"] is None  # availability does not load model


def test_readiness_is_explicit_in_core_startup_scripts():
    checker = ROOT / "scripts/wait-core.sh"
    assert checker.is_file()
    assert "/api/health" in checker.read_text()
    assert "curl --fail" in checker.read_text()
    installer = (ROOT / "scripts/install-core.sh").read_text()
    service = (ROOT / "scripts/service-core.sh").read_text()
    assert 'bash "$PROJECT_DIR/scripts/wait-core.sh"' in installer
    assert 'bash "$PROJECT/scripts/wait-core.sh"' in service


def test_web_engine_status_is_visible():
    html = TestClient(app).get("/").text
    assert 'id="qwenStatus"' in html
    assert "/api/engines" in html
    assert 'id="aceStatus"' in html
    assert "CPU: нотный алгоритм (без ИИ)" in html
