"""Regression checks: the CORE server must always deploy to the mounted 2 TB disk.

These are static checks; they run in GitHub Actions and do NOT connect to CORE.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = "/1tbdisk/muzikfed"


def test_fixed_deploy_location():
    deploy = (ROOT / "scripts/deploy-to-core.sh").read_text(encoding="utf-8")
    assert 'DEST="/1tbdisk/muzikfed"' in deploy
    assert 'git clone --branch main "$REPO" "$DEST"' in deploy
    assert 'git -C "$DEST" pull --ff-only origin main' in deploy
    assert "contains non-Git files" in deploy
    assert 'DEST="$HOME/pocket-orchestra"' not in deploy
    assert 'MOUNT_TARGET' in deploy  # Do not write to the OS disk if the mount is missing.


def test_install_venv_and_outputs_are_on_disk():
    install = (ROOT / "scripts/install-core.sh").read_text(encoding="utf-8")
    assert 'EXPECTED_DIR="/1tbdisk/muzikfed"' in install
    assert 'UV_PROJECT_ENVIRONMENT="$PROJECT_DIR/.venv"' in install
    assert 'UV_CACHE_DIR="$PROJECT_DIR/.cache/uv"' in install
    assert 'Environment=POCKET_ORCHESTRA_OUTPUT=$PROJECT_DIR/outputs' in install
    assert 'WorkingDirectory=$PROJECT_DIR' in install
    assert 'Environment=POCKET_ORCHESTRA_PORT=9095' in install


def test_update_is_disk_scoped():
    update = (ROOT / "scripts/update-core.sh").read_text(encoding="utf-8")
    assert 'PROJECT_DIR="/1tbdisk/muzikfed"' in update
    assert "git pull --ff-only origin main" in update


def test_git_ignores_disk_generated_files():
    ignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "outputs/" in ignore
    assert ".venv/" in ignore
    assert ".cache/" in ignore
    assert "/uv.lock" in ignore
