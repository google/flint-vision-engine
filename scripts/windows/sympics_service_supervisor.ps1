# Copyright 2026 Google LLC
# Licensed under Apache 2.0

<#
.SYNOPSIS
    SYMPICS Windows Native Process Supervisor & Health Watchdog.
.DESCRIPTION
    Monitors the SYMPICS Web Studio (Python server.py) and SYMPICS Intake Daemon on Windows.
    Automatically restarts processes if they crash, hang, or stop responding to HTTP requests.
    Supports running as a Windows Scheduled Task or background service (NSSM / WinSW).
#>

param(
    [int]$Port = 8080,
    [int]$CheckIntervalSeconds = 5,
    [string]$PythonExe = "python.exe"
)

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Resolve-Path "$ScriptDir\..\.."
if (Test-Path "$ProjectRoot\.env") {
    Get-Content "$ProjectRoot\.env" | ForEach-Object {
        if ($_ -match "^\s*SYMPICS_WEB_PORT\s*=\s*(\d+)") {
            $Port = [int]$matches[1]
        }
    }
}
$ServerScript = "$ProjectRoot\web\server.py"
$IntakeScript = "$ProjectRoot\scripts\daemons\sympics_intake_daemon.py"
$StagingDir = "$ProjectRoot\future-lan-storage\03_Ingestion_Staging"
$VaultDir = "$ProjectRoot\future-lan-storage"

Write-Host "===============================================================================" -ForegroundColor Cyan
Write-Host " [*]  SYMPICS WINDOWS PROCESS & SERVICE SUPERVISOR" -ForegroundColor Cyan
Write-Host "===============================================================================" -ForegroundColor Cyan
Write-Host " Project Root       : $ProjectRoot"
Write-Host " Web Studio Port    : http://localhost:$Port"
Write-Host " Check Interval     : $CheckIntervalSeconds seconds"
Write-Host "==============================================================================="

function Start-ManagedProcess {
    param(
        [string]$Name,
        [string]$FilePath,
        [string[]]$ArgumentList,
        [string]$WorkingDirectory
    )
    Write-Host "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] [SUPERVISOR] Launching $Name..." -ForegroundColor Green
    $proc = Start-Process -FilePath $FilePath -ArgumentList $ArgumentList -WorkingDirectory $WorkingDirectory -PassThru -NoNewWindow
    return $proc
}

function Test-HttpHealth {
    param([string]$Url)
    try {
        $response = Invoke-WebRequest -Uri $Url -Method Get -TimeoutSec 4 -UseBasicParsing -ErrorAction Stop
        return ($response.StatusCode -ge 200 -and $response.StatusCode -lt 400)
    }
    catch {
        return $false
    }
}

# Start Web Server
$webProc = Start-ManagedProcess -Name "SYMPICS Web Studio" -FilePath $PythonExe -ArgumentList @($ServerScript, "--port", "$Port") -WorkingDirectory $ProjectRoot

# Start Intake Daemon
$intakeArgs = @(
    $IntakeScript,
    "--staging-dir", $StagingDir,
    "--vault-dir", $VaultDir,
    "--poll-interval", "2.0",
    "--stability-delay", "2.0"
)
$intakeProc = Start-ManagedProcess -Name "SYMPICS Intake Daemon" -FilePath $PythonExe -ArgumentList $intakeArgs -WorkingDirectory $ProjectRoot

$consecutiveWebFailures = 0

try {
    while ($true) {
        Start-Sleep -Seconds $CheckIntervalSeconds

        # 1. Check Web Server Process
        if ($null -eq $webProc -or $webProc.HasExited) {
            Write-Host "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] [ALERT] SYMPICS Web Studio process terminated. Restarting..." -ForegroundColor Yellow
            $webProc = Start-ManagedProcess -Name "SYMPICS Web Studio" -FilePath $PythonExe -ArgumentList @($ServerScript, "--port", "$Port") -WorkingDirectory $ProjectRoot
            $consecutiveWebFailures = 0
        }
        else {
            # Check HTTP Health
            $isHealthy = Test-HttpHealth -Url "http://127.0.0.1:$Port/"
            if (-not $isHealthy) {
                $consecutiveWebFailures++
                Write-Host "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] [WARN] Web Studio HTTP check failed (Attempt $consecutiveWebFailures/3)..." -ForegroundColor Yellow
                if ($consecutiveWebFailures -ge 3) {
                    Write-Host "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] [RESTART] Web Studio unresponsive. Force restarting process..." -ForegroundColor Red
                    Stop-Process -Id $webProc.Id -Force -ErrorAction SilentlyContinue
                    Start-Sleep -Seconds 2
                    $webProc = Start-ManagedProcess -Name "SYMPICS Web Studio" -FilePath $PythonExe -ArgumentList @($ServerScript, "--port", "$Port") -WorkingDirectory $ProjectRoot
                    $consecutiveWebFailures = 0
                }
            }
            else {
                $consecutiveWebFailures = 0
            }
        }

        # 2. Check Intake Daemon Process
        if ($null -eq $intakeProc -or $intakeProc.HasExited) {
            Write-Host "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] [ALERT] SYMPICS Intake Daemon terminated. Restarting..." -ForegroundColor Yellow
            $intakeProc = Start-ManagedProcess -Name "SYMPICS Intake Daemon" -FilePath $PythonExe -ArgumentList $intakeArgs -WorkingDirectory $ProjectRoot
        }
    }
}
finally {
    Write-Host "`n[SUPERVISOR] Shutting down managed processes..." -ForegroundColor Cyan
    if ($webProc -and -not $webProc.HasExited) { Stop-Process -Id $webProc.Id -Force -ErrorAction SilentlyContinue }
    if ($intakeProc -and -not $intakeProc.HasExited) { Stop-Process -Id $intakeProc.Id -Force -ErrorAction SilentlyContinue }
}
