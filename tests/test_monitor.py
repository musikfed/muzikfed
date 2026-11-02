"""Tests for read-only dual-socket CORE .100 monitoring."""
from collections import namedtuple
import subprocess

from fastapi.testclient import TestClient

from pocket_orchestra.app import app
from pocket_orchestra import monitor


def test_dual_socket_cpu_delta_and_process(monkeypatch):
    monitor._CPU_LAST = {}
    monitor._PROC_LAST = None
    calls = iter([
        {0: (100, 70), 1: (100, 70), 2: (100, 60), 3: (100, 60)},
        {0: (200, 90), 1: (200, 90), 2: (200, 110), 3: (200, 110)},
    ])
    monkeypatch.setattr(monitor, "_cpu_snapshot", lambda: next(calls))
    monkeypatch.setattr(monitor, "_package_for_cpu", lambda cpu: 0 if cpu < 2 else 1)
    monkeypatch.setattr(monitor, "_ram", lambda: {"percent": 25})
    monkeypatch.setattr(monitor, "_gpu", lambda: {"available": False})
    monkeypatch.setattr(monitor, "_process_rss_mib", lambda: 30.)
    monkeypatch.setattr(monitor.os, "getloadavg", lambda: (3.5, 3.0, 2.0))
    d = namedtuple("Disk", "total used free")
    monkeypatch.setattr(monitor.shutil, "disk_usage", lambda _: d(1000, 200, 800))
    mock_times = iter([1.0, 1.4])
    class FakeTime:
        def __init__(self, user): self.user = user; self.system = 0
    monkeypatch.setattr(monitor.os, "times", lambda: FakeTime(next(mock_times)))
    wall = iter([10., 12.])
    monkeypatch.setattr(monitor.time, "monotonic", lambda: next(wall))

    first = monitor.collect_metrics()
    assert first["cpu"]["percent"] is None  # requires an interval
    assert len(first["cpu"]["sockets"]) == 2
    second = monitor.collect_metrics()
    assert second["cpu"]["percent"] == 65.0
    assert [s["percent"] for s in second["cpu"]["sockets"]] == [80.0, 50.0]
    assert [s["logical_threads"] for s in second["cpu"]["sockets"]] == [2, 2]
    assert second["cpu"]["threads"] == 4
    assert second["process"]["cpu_percent_total"] == 5.0


def test_ram_available_and_swap(monkeypatch):
    mem = ("MemTotal:       49152000 kB\n"
           "MemFree:         3000000 kB\n"
           "MemAvailable:   30000000 kB\n"
           "SwapTotal:       4096000 kB\n"
           "SwapFree:        2048000 kB\n")
    monkeypatch.setattr(monitor.Path, "read_text", lambda self, **kwargs: mem)
    ram = monitor._ram()
    assert ram["percent"] == 39.0
    assert ram["used_gib"] > 0
    assert ram["swap_used_gib"] > 0


def test_gpu_metrics_and_missing_driver(monkeypatch):
    monkeypatch.setattr(monitor.shutil, "which", lambda _: "/usr/bin/nvidia-smi")
    text = "NVIDIA GeForce RTX 3060, 46, 2200, 12288, 55, 94.5\n"
    def fake_run(*args, **kwargs):
        assert "timeout" in kwargs
        return subprocess.CompletedProcess(args[0], 0, text, "")
    monkeypatch.setattr(monitor.subprocess, "run", fake_run)
    gpu = monitor._gpu()
    assert gpu["available"] is True
    assert gpu["utilization_pct"] == 46
    assert gpu["vram_used_mib"] == 2200
    assert gpu["vram_total_mib"] == 12288
    assert gpu["temperature_c"] == 55
    assert gpu["power_w"] == 94.5
    assert 17 < gpu["vram_percent"] < 19
    monkeypatch.setattr(monitor.shutil, "which", lambda _: None)
    assert monitor._gpu()["available"] is False


def test_nvidia_smi_timeout_is_nonfatal(monkeypatch):
    monkeypatch.setattr(monitor.shutil, "which", lambda _: "/usr/bin/nvidia-smi")
    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired("nvidia-smi", 2.5)
    monkeypatch.setattr(monitor.subprocess, "run", timeout)
    gpu = monitor._gpu()
    assert gpu["available"] is False
    assert "nvidia-smi" in gpu["message"]


def test_metrics_route_and_dashboard(monkeypatch):
    monkeypatch.setattr(monitor, "_gpu", lambda: {
        "available": False, "message": "NVIDIA unavailable"})
    client = TestClient(app)
    r = client.get("/api/metrics")
    assert r.status_code == 200, r.text
    data = r.json()
    assert {"cpu", "ram", "gpu", "process", "storage"} <= set(data)
    assert isinstance(data["cpu"]["sockets"], list)
    assert data["gpu"]["available"] is False
    html = client.get("/").text
    assert 'id="monitorCard"' in html
    assert 'id="monVram"' in html
    assert "setInterval(pollMonitor,3000)" in html
