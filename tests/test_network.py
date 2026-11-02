"""Check configurable server bind address without opening a network socket."""
import uvicorn
from pocket_orchestra.app import main


def test_default_core_bind(monkeypatch):
    monkeypatch.delenv("POCKET_ORCHESTRA_HOST", raising=False)
    monkeypatch.delenv("POCKET_ORCHESTRA_PORT", raising=False)
    captured = {}
    monkeypatch.setattr(uvicorn, "run", lambda *args, **kwargs: captured.update(kwargs))
    main()
    assert captured["host"] == "192.168.0.100"
    assert captured["port"] == 9095


def test_override_bind(monkeypatch):
    monkeypatch.setenv("POCKET_ORCHESTRA_HOST", "127.0.0.1")
    monkeypatch.setenv("POCKET_ORCHESTRA_PORT", "9096")
    captured = {}
    monkeypatch.setattr(uvicorn, "run", lambda *args, **kwargs: captured.update(kwargs))
    main()
    assert captured["host"] == "127.0.0.1"
    assert captured["port"] == 9096
