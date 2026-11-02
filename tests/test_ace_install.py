"""The GPU installer must be REAL, optional, on /1tbdisk and safe by default.

No actual GPU or >10GB model required in CI. Test the real shell parser,
the documented upstream CLI and our user's service constraints.
"""
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "scripts/install-ace-step.sh"
CHECKER = ROOT / "scripts/check-ace-step.sh"


def test_installer_help_is_safe_without_nvidia_or_network():
    r = subprocess.run(["bash", str(INSTALLER), "--help"],
                       text=True, capture_output=True, timeout=5)
    assert r.returncode == 0, r.stderr
    assert "--preflight" in r.stdout
    assert "--skip-download" in r.stdout
    assert "RTX 3060" in r.stdout


def test_engine_is_installed_on_2tb_disk_and_not_autostarted():
    script = INSTALLER.read_text(encoding="utf-8")
    assert 'BASE="/1tbdisk/muzikfed"' in script
    assert 'SOURCE="https://github.com/ace-step/ACE-Step-1.5.git"' in script
    assert '"$UV" sync --python 3.12' in script
    assert "torch.cuda.is_available()" in script
    assert '"$UV" run --no-sync acestep-download' in script
    assert 'acestep-download --model "$LM_MODEL"' in script
    assert "systemctl --user daemon-reload" in script
    assert 'systemctl --user disable "$UNIT"' in script
    assert 'Environment=ACESTEP_API_HOST=127.0.0.1' in script
    assert 'Environment=ACESTEP_API_PORT=8001' in script
    assert 'Environment=ACESTEP_LM_MODEL_PATH=$LM_MODEL' in script
    assert "ExecStart=$UV run --no-sync --project $ENGINE acestep-api" in script
    assert 'systemctl --user enable --now "$UNIT"' not in script
    assert "git pull" not in script
    assert "rm -rf" not in script


def test_installer_diagnostics_do_not_download_or_start_models():
    diag = CHECKER.read_text(encoding="utf-8")
    assert "nvidia-smi" in diag
    assert "systemctl --user is-active" in diag
    assert "127.0.0.1:8001/health" in diag
    assert "acestep-download" not in diag
    assert "systemctl --user start" not in diag
