"""Read-only status of the real local Ollama model used for note-level AI composition."""
from __future__ import annotations

import json
import urllib.request
import urllib.error

OLLAMA_TAGS = "http://127.0.0.1:11434/api/tags"


def ollama_status(model: str = "qwen3:8b") -> dict:
    """Check availability without loading a model or reserving VRAM."""
    try:
        with urllib.request.urlopen(OLLAMA_TAGS, timeout=2) as reply:
            payload = json.loads(reply.read(2_000_000))
        models = payload.get("models")
        if not isinstance(models, list):
            raise ValueError("Invalid model listing")
        available = [
            entry.get("name", "") for entry in models if isinstance(entry, dict)
        ]
        found = model in available
        return {
            "ollama_running": True, "model_installed": found,
            "model": model,
            "message": ("Qwen установлен и доступен по локальному API"
                        if found else
                        "Ollama отвечает, но нужная модель не найдена: ollama pull " + model),
            "loaded_in_gpu": None,  # installed != resident in VRAM
        }
    except (OSError, ValueError, json.JSONDecodeError, urllib.error.URLError):
        return {
            "ollama_running": False, "model_installed": False,
            "model": model, "loaded_in_gpu": None,
            "message": "Ollama не отвечает на CORE: проверь systemctl status ollama",
        }
