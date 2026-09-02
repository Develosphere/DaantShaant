<#
.SYNOPSIS
    Stops DaantShaant backend services listening on ports 8000, 8001, and 8002.

.DESCRIPTION
    Safely finds processes listening on port 8000 (Orchestrator), port 8001
    (Teeth Analyzer), and port 8002 (Diagnosis) and terminates only those processes.
    Unrelated Python processes are never touched.
#>

param(
    [switch]$DryRun
)

$ErrorActionPreference = "Continue"

$Ports = @(
    @{ Port = 8000; Service = "Orchestrator" },
    @{ Port = 8001; Service = "Teeth Analyzer" },
    @{ Port = 8002; Service = "Diagnosis" }
)

Write-Host "`nChecking DaantShaant Backend Services on ports 8000, 8001, 8002...`n" -ForegroundColor Cyan

$StoppedCount = 0

foreach ($item in $Ports) {
    $port = $item.Port
    $service = $item.Service

    try {
        $connections = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
        if ($connections) {
            $pids = $connections | Select-Object -ExpandProperty OwningProcess -Unique
            foreach ($procId in $pids) {
                if ($procId -gt 0) {
                    $proc = Get-Process -Id $procId -ErrorAction SilentlyContinue
                    $procName = if ($proc) { $proc.ProcessName } else { "Unknown" }
                    
                    if ($DryRun) {
                        Write-Host "  [DRY RUN] Would terminate PID $procId ($procName) for $service on port $port" -ForegroundColor Yellow
                    } else {
                        Write-Host "Stopping $service (Port $port, PID $procId, Process: $procName)..." -ForegroundColor Yellow
                        Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
                        Write-Host " -> Successfully stopped $service (PID $procId)" -ForegroundColor Green
                        $StoppedCount++
                    }
                }
            }
        } else {
            Write-Host "  No active process listening on port $port ($service)." -ForegroundColor Gray
        }
    } catch {
        Write-Warning "Could not query or stop process on port $($port): $_"
    }
}

if (-not $DryRun) {
    Write-Host "`nBackend cleanup complete ($StoppedCount service(s) stopped).`n" -ForegroundColor Cyan
}
