"""Optional high-quality MP3 sharing copy; WAV remains lossless master for MIDI/DAW work."""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess


def create_mp3(wav: Path, target: Path, *, bitrate: str = "256k") -> bool:
    """Encode locally with ffmpeg if available; never remove or modify master WAV."""
    executable = shutil.which("ffmpeg")
    if executable is None:
        return False
    temporary = target.with_suffix(".mp3.pending")
    try:
        result = subprocess.run(
            [executable, "-hide_banner", "-nostdin", "-loglevel", "error",
             "-y", "-i", str(wav), "-vn", "-c:a", "libmp3lame",
             "-b:a", bitrate, "-f", "mp3", str(temporary)],
            check=False, capture_output=True, timeout=180,
        )
        if result.returncode or not temporary.is_file() or temporary.stat().st_size < 1024:
            return False
        os.replace(temporary, target)
        return True
    except (OSError, subprocess.TimeoutExpired):
        return False
    finally:
        temporary.unlink(missing_ok=True)
