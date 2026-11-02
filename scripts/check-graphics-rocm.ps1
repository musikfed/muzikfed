# Read-only AMD RX 7600 XT / Windows 11 ACE-Step compatibility preflight.
# Run in PowerShell on GRAPHICS .103; does NOT install packages or change drivers.
$ErrorActionPreference = "Continue"
Write-Host "GRAPHICS .103 - ROCm GPU feasibility check (no installation)"
Get-CimInstance Win32_VideoController | Select-Object Name, DriverVersion, AdapterRAM | Format-Table -AutoSize
Write-Host "Installed Python versions:"
py --list
Write-Host "Python 3.12 PyTorch/ROCm diagnostic:"
$py12 = & py -3.12 -c "import sys; print(sys.version)" 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Warning "Python 3.12 unavailable. ROCm on Windows currently needs Python 3.12."
    exit 2
}
Write-Host $py12
& py -3.12 -c "import importlib.util; print('torch installed:', bool(importlib.util.find_spec('torch'))); import torch; print('torch:', torch.__version__); print('HIP:', torch.version.hip); print('GPU available:', torch.cuda.is_available()); print('GPU:', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'not detected')" 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Warning "PyTorch missing or ROCm device not detected. This is NOT proof that RX 7600 XT is compatible."
}
Write-Host "Official Windows ROCm 7.2.1 Radeon supported list does not include RX 7600 XT (gfx1102)."
Write-Host "Do not migrate ACE-Step from working CORE .100 based on VRAM alone."
Write-Host "See docs/GRAPHICS_AMD_EXPERIMENT.md"
