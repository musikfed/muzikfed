"""VPN dashboard stop: no token; allow same-origin browser requests only."""
import subprocess

from fastapi.testclient import TestClient

from pocket_orchestra.app import app
from pocket_orchestra import control

client = TestClient(app)
ORIGIN = {"Origin": "http://testserver"}


def test_stop_denies_cross_origin_requests(monkeypatch):
    calls = []
    monkeypatch.setattr(control.subprocess, "run", lambda *args, **kwargs: calls.append(args))
    assert client.post("/api/admin/stop").status_code == 403
    assert client.post("/api/admin/stop", headers={"Origin": "http://other.example"}).status_code == 403
    assert not calls


def test_stop_does_not_need_token_and_schedules_only_our_service(monkeypatch):
    calls = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(control.subprocess, "run", fake_run)
    res = client.post("/api/admin/stop", headers=ORIGIN)
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


def test_stop_fails_safely_when_systemd_unavailable(monkeypatch):
    def fail(*args, **kwargs):
        raise FileNotFoundError("systemd-run absent")

    monkeypatch.setattr(control.subprocess, "run", fail)
    res = client.post("/api/admin/stop", headers=ORIGIN)
    assert res.status_code == 503


def test_dashboard_has_simple_service_controls():
    html = client.get("/").text
    assert 'id="stopCore"' in html
    assert 'id="stopToken"' not in html
    assert 'id="creationMode"' in html
    assert 'show-control-token.sh' not in html
    assert "Только голос" in html
