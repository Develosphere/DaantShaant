# Nuclear option: fresh virtualenv when numpy cannot be repaired (Access denied / _utils missing)
$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

Write-Host "Stopping Python..."
Get-Process python, pythonw -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 2

if (Test-Path .venv) {
    Write-Host "Removing old .venv..."
    Remove-Item -Recurse -Force .venv
}

Write-Host "Creating new .venv..."
python -m venv .venv
.\.venv\Scripts\pip install --upgrade pip
.\.venv\Scripts\pip install -r requirements.txt -c constraints.txt

Write-Host ""
Write-Host "Verify:"
.\.venv\Scripts\python -c "import numpy; import cv2; print('numpy', numpy.__version__); print('cv2', cv2.__version__)"
Write-Host "Done. Run: .\scripts\start-services.ps1"
