"""Read-only CORE .100 hardware telemetry for the VPN dashboard.

No external Python dependencies. Linux /proc and /sys provide dual-socket CPU,
RAM and the API process; nvidia-smi (if NVIDIA drivers are installed) supplies
RTX GPU activity, VRAM, temperature and power. Values are SYSTEM-WIDE unless
explicitly marked as Pocket Orchestra API process. Never run sudo.
"""
from __future__ import annotations

import csv
import functools
import os
from pathlib import Path
import re
import shutil
import subprocess
import threading
import time

_CPU_LAST: dict[int, tuple[int, int]] = {}
_PROC_LAST: tuple[float, float] | None = None
_LOCK = threading.Lock()


def _percent(used: float, total: float) -> float | None:
    return round(100.0 * used / total, 1) if total > 0 else None


@functools.lru_cache(maxsize=512)
def _package_for_cpu(cpu: int) -> int:
    """Linux physical_package_id tells which Xeon socket owns this logical CPU."""
    try:
        return int(Path(f"/sys/devices/system/cpu/cpu{cpu}/topology/physical_package_id").read_text().strip())
    except (OSError, ValueError):
        return 0  # virtualized/unavailable topology: a single aggregate group


def _cpu_snapshot() -> dict[int, tuple[int, int]]:
    """Map logical CPU -> (all jiffies, idle+iowait jiffies)."""
    results: dict[int, tuple[int, int]] = {}
    for row in Path("/proc/stat").read_text().splitlines():
        m = re.match(r"^cpu(\d+)\s+(.+)$", row)
        if not m:
            continue
        values = [int(item) for item in m.group(2).split()]
        if len(values) >= 4:
            cpu = int(m.group(1))
            total = sum(values)
            idle = values[3] + (values[4] if len(values) > 4 else 0)
            results[cpu] = (total, idle)
    return results


def _ram() -> dict:
    values: dict[str, int] = {}
    for line in Path("/proc/meminfo").read_text().splitlines():
        name, sep, val = line.partition(":")
        if sep:
            try:
                values[name] = int(val.strip().split()[0]) * 1024
            except (IndexError, ValueError):
                continue
    total = values.get("MemTotal", 0)
    available = values.get("MemAvailable", values.get("MemFree", 0))
    used = max(0, total - available)
    swap_total = values.get("SwapTotal", 0)
    swap_free = values.get("SwapFree", swap_total)
    return {
        "total_gib": round(total / 1024**3, 2),
        "used_gib": round(used / 1024**3, 2),
        "available_gib": round(available / 1024**3, 2),
        "percent": _percent(used, total),
        "swap_used_gib": round(max(0, swap_total - swap_free) / 1024**3, 2),
        "swap_total_gib": round(swap_total / 1024**3, 2),
    }


def _float(value: str) -> float | None:
    value = value.strip()
    if not value or value.upper() in ("N/A", "[NOT SUPPORTED]", "NOT SUPPORTED"):
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _gpu() -> dict:
    """nvidia-smi is intentionally separate and has a short timeout."""
    if not shutil.which("nvidia-smi"):
        return {"available": False, "message": "nvidia-smi не найден: проверь драйвер NVIDIA на CORE"}
    try:
        result = subprocess.run(
            ["nvidia-smi",
             "--query-gpu=name,utilization.gpu,memory.used,memory.total,temperature.gpu,power.draw",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=2.5, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"available": False, "message": f"nvidia-smi не ответил: {type(exc).__name__}"}
    if result.returncode:
        return {"available": False, "message": "NVIDIA GPU недоступен: " + result.stderr.strip()[:160]}
    rows = list(csv.reader(result.stdout.splitlines()))
    if not rows or len(rows[0]) < 6:
        return {"available": False, "message": "nvidia-smi не вернул полные данные"}
    first = [item.strip() for item in rows[0]]
    used, total = _float(first[2]), _float(first[3])
    return {
        "available": True,
        "name": first[0],
        "utilization_pct": _float(first[1]),
        "vram_used_mib": used,
        "vram_total_mib": total,
        "vram_percent": _percent(used, total) if used is not None and total is not None else None,
        "temperature_c": _float(first[4]),
        "power_w": _float(first[5]),
        "note": "Общие показатели видеокарты, не только Pocket Orchestra",
    }


def _process_rss_mib() -> float | None:
    for line in Path("/proc/self/status").read_text().splitlines():
        if line.startswith("VmRSS:"):
            return round(int(line.split()[1]) / 1024, 1)
    return None


def collect_metrics() -> dict:
    """Return fresh hardware telemetry; report unavailable fields without HTTP 500."""
    global _CPU_LAST, _PROC_LAST
    now = time.monotonic()
    try:
        current = _cpu_snapshot()
        with _LOCK:
            prev = _CPU_LAST
            _CPU_LAST = current
            socket_deltas: dict[int, list[float]] = {}
            overall_total = overall_busy = 0.0
            for cpu, (total, idle) in current.items():
                socket_id = _package_for_cpu(cpu)
                group = socket_deltas.setdefault(socket_id, [0.0, 0.0, 0])
                group[2] += 1
                if cpu in prev:
                    dt = total - prev[cpu][0]
                    di = idle - prev[cpu][1]
                    if dt > 0:
                        busy = max(0, min(dt, dt - di))
                        group[0] += busy
                        group[1] += dt
                        overall_busy += busy
                        overall_total += dt
            cpu_percent = _percent(overall_busy, overall_total)
            sockets = [
                {"socket": socket_id, "logical_threads": int(stat[2]),
                 "percent": _percent(stat[0], stat[1])}
                for socket_id, stat in sorted(socket_deltas.items())
            ]
            process_times = os.times()
            proc_total = process_times.user + process_times.system
            previous_proc = _PROC_LAST
            _PROC_LAST = (now, proc_total)
            proc_pct = None
            if previous_proc and len(current):
                delta_wall = now - previous_proc[0]
                if delta_wall > 0:
                    proc_pct = round(max(0, proc_total - previous_proc[1]) * 100
                                     / (delta_wall * len(current)), 1)
        cpu = {"percent": cpu_percent, "threads": len(current),
               "sockets": sockets, "load_1m": round(os.getloadavg()[0], 2)}
        process = {"cpu_percent_total": proc_pct, "rss_mib": _process_rss_mib(),
                   "note": "Только процесс API; Ollama и дочерние синтезаторы отдельно"}
    except (OSError, ValueError, IndexError) as exc:
        cpu = {"percent": None, "threads": 0, "sockets": [],
               "message": f"/proc/stat недоступен: {type(exc).__name__}"}
        process = {"cpu_percent_total": None, "rss_mib": None}
    try:
        ram = _ram()
    except (OSError, ValueError):
        ram = {"percent": None, "message": "/proc/meminfo недоступен"}
    try:
        disk = shutil.disk_usage("/1tbdisk/muzikfed")
        storage = {
            "used_gib": round(disk.used / 1024**3, 1),
            "total_gib": round(disk.total / 1024**3, 1),
            "percent": _percent(disk.used, disk.total),
            "path": "/1tbdisk/muzikfed",
        }
    except OSError:
        storage = {"percent": None, "message": "Диск /1tbdisk недоступен"}
    return {
        "timestamp": round(time.time()),
        "cpu": cpu, "ram": ram, "gpu": _gpu(),
        "process": process, "storage": storage,
        "sample_seconds": 3,
    }
