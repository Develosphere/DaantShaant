<#
.SYNOPSIS
    Starts all three DaantShaant backend services on Windows.

.DESCRIPTION
    Starts:
    1. Orchestrator (Port 8000)
    2. Teeth Analyzer (Port 8001)
    3. Diagnosis (Port 8002)

    PYTHON ENVIRONMENT:
    Intentionally uses 'orchestrator\.venv\Scripts\python.exe' for ALL three services
    because it contains the verified OpenCV build without MinGW crashes.

    RELOAD POLICY:
    --reload is intentionally disabled to ensure stability and avoid high memory usage.
#>

param(
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"
$RepoRoot = $PSScriptRoot

$PythonExe = Join-Path $RepoRoot "orchestrator\.venv\Scripts\python.exe"

if (-not (Test-Path $PythonExe)) {
    Write-Error "Python executable not found at: $PythonExe`nPlease ensure the orchestrator virtual environment is created."
    exit 1
}

# Service definitions
# Port 8000: Orchestrator (FastAPI orchestration, auth, chat, RAG, recommendations)
# Port 8001: Teeth Analyzer (Clinical vision & quality gating)
# Port 8002: Diagnosis (Deterministic clinical screening triage)
$Services = @(
    @{
        Name      = "Orchestrator"
        Port      = 8000
        AppDir    = "orchestrator/src"
        AppModule = "orchestrator.main:app"
        Title     = "DaantShaant - Orchestrator :8000"
        HealthUrl = "http://127.0.0.1:8000/health"
    },
    @{
        Name      = "Teeth Analyzer"
        Port      = 8001
        AppDir    = "services/teeth_analyzer/src"
        AppModule = "teeth_analyzer.main:app"
        Title     = "DaantShaant - Teeth Analyzer :8001"
        HealthUrl = "http://127.0.0.1:8001/health"
    },
    @{
        Name      = "Diagnosis"
        Port      = 8002
        AppDir    = "services/diagnosis/src"
        AppModule = "diagnosis.main:app"
        Title     = "DaantShaant - Diagnosis :8002"
        HealthUrl = "http://127.0.0.1:8002/health"
    }
)

function Test-PortInUse([int]$Port) {
    try {
        $conn = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
        return ($null -ne $conn)
    } catch {
        try {
            $tcp = New-Object System.Net.Sockets.TcpClient
            $asyncResult = $tcp.BeginConnect("127.0.0.1", $Port, $null, $null)
            $wait = $asyncResult.AsyncWaitHandle.WaitOne(300, $false)
            if ($wait -and $tcp.Connected) {
                $tcp.EndConnect($asyncResult)
                $tcp.Close()
                return $true
            }
            $tcp.Close()
            return $false
        } catch {
            return $false
        }
    }
}

if ($DryRun) {
    Write-Host "`n[DRY RUN] Generated Backend Service Commands (No processes will be started):`n" -ForegroundColor Cyan
    foreach ($svc in $Services) {
        $cmd = "& `"$PythonExe`" -m uvicorn $($svc.AppModule) --app-dir $($svc.AppDir) --host 127.0.0.1 --port $($svc.Port)"
        Write-Host "[$($svc.Name) - Port $($svc.Port)]" -ForegroundColor Yellow
        Write-Host "Working Directory: $RepoRoot"
        Write-Host "Command: $cmd`n"
    }
    exit 0
}

Write-Host "`nStarting DaantShaant Backend Services...`n" -ForegroundColor Cyan

$LaunchedCount = 0

foreach ($svc in $Services) {
    $port = $svc.Port
    $name = $svc.Name
    $title = $svc.Title

    if (Test-PortInUse -Port $port) {
        Write-Warning "Port $port is already in use. Skipping start for $name to avoid duplicate process."
        continue
    }

    $windowCmd = "`$host.UI.RawUI.WindowTitle = '$title'; Write-Host '$title' -ForegroundColor Cyan; & '$PythonExe' -m uvicorn $($svc.AppModule) --app-dir $($svc.AppDir) --host 127.0.0.1 --port $port"

    Start-Process powershell.exe -ArgumentList "-NoExit", "-Command", $windowCmd -WorkingDirectory $RepoRoot
    Write-Host " -> Launched $name on http://127.0.0.1:$port" -ForegroundColor Green
    $LaunchedCount++
    Start-Sleep -Milliseconds 600
}

Write-Host "`nDaantShaant backend stack started.`n" -ForegroundColor Green
Write-Host "Orchestrator:"
Write-Host "http://127.0.0.1:8000" -ForegroundColor Yellow
Write-Host "`nTeeth Analyzer:"
Write-Host "http://127.0.0.1:8001" -ForegroundColor Yellow
Write-Host "`nDiagnosis:"
Write-Host "http://127.0.0.1:8002" -ForegroundColor Yellow

if ($LaunchedCount -gt 0) {
    Write-Host "`nWaiting 3 seconds before checking health endpoints..." -ForegroundColor Gray
    Start-Sleep -Seconds 3

    Write-Host "`nService Health Status:" -ForegroundColor Cyan
    foreach ($svc in $Services) {
        try {
            $resp = Invoke-RestMethod -Uri $svc.HealthUrl -Method Get -TimeoutSec 3 -ErrorAction Stop
            Write-Host "  [OK] $($svc.Name) ($($svc.HealthUrl))" -ForegroundColor Green
        } catch {
            Write-Warning "  [UNAVAILABLE] $($svc.Name) ($($svc.HealthUrl)) - Service may still be initializing."
        }
    }
}
