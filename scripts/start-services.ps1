# Start backend services (run from repo root after pip install -r requirements.txt)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot

Write-Host "Starting Teeth Analyzer on :8001..."
Start-Process powershell -ArgumentList @(
    "-NoExit", "-Command",
    "cd '$root'; .\.venv\Scripts\uvicorn teeth_analyzer.main:app --host 0.0.0.0 --port 8001 --reload --reload-dir '$root\services\teeth_analyzer\src'"
)

Start-Sleep -Seconds 2

Write-Host "Starting Diagnosis on :8002..."
Start-Process powershell -ArgumentList @(
    "-NoExit", "-Command",
    "cd '$root'; .\.venv\Scripts\uvicorn diagnosis.main:app --host 0.0.0.0 --port 8002 --reload --reload-dir '$root\services\diagnosis\src'"
)

Start-Sleep -Seconds 2

Write-Host "Starting Orchestrator on :8000..."
Start-Process powershell -ArgumentList @(
    "-NoExit", "-Command",
    "cd '$root'; .\.venv\Scripts\uvicorn orchestrator.main:app --host 0.0.0.0 --port 8000 --reload --reload-dir '$root\orchestrator\src'"
)

Write-Host ""
Write-Host "Backend ready. Start frontend:"
Write-Host "  cd apps\web"
Write-Host "  npm run dev"
Write-Host ""
Write-Host "Open http://localhost:3000"
