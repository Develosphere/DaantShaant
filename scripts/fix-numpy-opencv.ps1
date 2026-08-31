# Fixes corrupted NumPy / OpenCV (ModuleNotFoundError: numpy._utils, cv2 errors)
# Close all terminals running uvicorn before this script.
$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

Write-Host "Stopping Python processes that lock .venv (close uvicorn windows too)..."
Get-Process python, pythonw -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 2

$site = Join-Path (Get-Location) ".venv\Lib\site-packages"
Write-Host "Removing numpy / opencv from site-packages..."
@("numpy", "numpy.libs", "~umpy", "~umpy.libs") | ForEach-Object {
    $p = Join-Path $site $_
    if (Test-Path $p) { Remove-Item -Recurse -Force $p }
}
Get-ChildItem $site -ErrorAction SilentlyContinue | Where-Object {
    $_.Name -match '^numpy' -or $_.Name -match '^~umpy' -or $_.Name -match '^opencv'
} | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue

Write-Host "Installing NumPy 1.26.4..."
.\.venv\Scripts\pip install --no-cache-dir "numpy==1.26.4"
Write-Host "Installing OpenCV 4.9.0.80..."
.\.venv\Scripts\pip install --no-cache-dir "opencv-python-headless==4.9.0.80"
Write-Host "Installing project packages..."
.\.venv\Scripts\pip install -r requirements.txt -c constraints.txt

Write-Host ""
Write-Host "Verify:"
.\.venv\Scripts\python -c "import numpy; import cv2; print('numpy', numpy.__version__); print('cv2', cv2.__version__)"
