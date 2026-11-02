"""Admin stop must be authenticated, same-origin and scheduled safely."""
import subprocess

from fastapi.testclient import TestClient

from pocket_orchestra.app import app
from pocket_orchestra import control

client = TestClient(app)
ORIGIN = {"Origin": "http://testserver"}


def test_stop_requires_origin_and_secret(tmp_path, monkeypatch):
    token_file = tmp_path / "token"
    token_file.write_text("example-private-secret", encoding="utf-8")
    monkeypatch.setattr(control, "TOKEN_FILE", token_file)

    assert client.post("/api/admin/stop").status_code == 403
    assert client.post("/api/admin/stop", headers=ORIGIN).status_code == 403
    assert client.post("/api/admin/stop", headers={
        **ORIGIN, "X-Pocket-Control-Token": "wrong",
    }).status_code == 403
    assert client.post("/api/admin/stop", headers={
        "Origin": "http://attacker.example",
        "X-Pocket-Control-Token": "example-private-secret",
    }).status_code == 403


def test_stop_requires_installed_token(tmp_path, monkeypatch):
    monkeypatch.setattr(control, "TOKEN_FILE", tmp_path / "absent")
    res = client.post("/api/admin/stop", headers={
        **ORIGIN, "X-Pocket-Control-Token": "anything",
    })
    assert res.status_code == 503


def test_stop_schedules_only_our_service(tmp_path, monkeypatch):
    token_file = tmp_path / "token"
    token_file.write_text("example-private-secret", encoding="utf-8")
    monkeypatch.setattr(control, "TOKEN_FILE", token_file)
    calls = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(control.subprocess, "run", fake_run)
    res = client.post("/api/admin/stop", headers={
        **ORIGIN, "X-Pocket-Control-Token": "example-private-secret",
    })
    assert res.status_code == 202, res.text
    assert res.json()["status"] == "stop_scheduled"
    assert len(calls) == 1
    command, kwargs = calls[0]
    assert command[0] == "systemd-run"
    assert "--user" in command and "--on-active=3s" in command
    assert command[-5:] == [
        "/usr/bin/systemctl", "--user", "disable", "--now",
        "pocket-orchestra.service",
    ]
    assert kwargs["check"] is True


def test_stop_fails_safely_when_user_systemd_unavailable(tmp_path, monkeypatch):
    token_file = tmp_path / "token"
    token_file.write_text("example-private-secret", encoding="utf-8")
    monkeypatch.setattr(control, "TOKEN_FILE", token_file)

    def fail(*args, **kwargs):
        raise FileNotFoundError("systemd-run absent")

    monkeypatch.setattr(control.subprocess, "run", fail)
    res = client.post("/api/admin/stop", headers={
        **ORIGIN, "X-Pocket-Control-Token": "example-private-secret",
    })
    assert res.status_code == 503


def test_dashboard_has_service_controls():
    html = client.get("/").text
    assert 'id="stopCore"' in html
    assert 'id="stopToken"' in html
    assert 'id="creationMode"' in html
    assert "Только голос" in html
