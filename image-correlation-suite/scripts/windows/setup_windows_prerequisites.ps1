# Copyright 2026 Google LLC
# Licensed under Apache 2.0

<#
.SYNOPSIS
    Automated Windows Setup: PostgreSQL 16 + pgvector + SYMPICS Environment.
.DESCRIPTION
    Installs and configures PostgreSQL 16, pgvector extension binaries, Python
    virtual environment, and initializes the SYMPICS database schemas.
.NOTES
    Run from an Administrator PowerShell console.
#>

param(
    [string]$SuperPassword = "sympics_secure_password",
    [int]$Port = 5432,
    [string]$PgVersion = "16.4-1"
)

$ErrorActionPreference = "Stop"

Write-Host "===============================================================================" -ForegroundColor Cyan
Write-Host " [*] SYMPICS WINDOWS PREREQUISITE SETUP & DATABASE BOOTSTRAPPER" -ForegroundColor Cyan
Write-Host "===============================================================================" -ForegroundColor Cyan

# 1. Verify Administrator Privileges
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Host "[!] ERROR: This script must be run as Administrator." -ForegroundColor Red
    Write-Host "    Right-click PowerShell -> 'Run as Administrator', then execute this script again."
    Exit 1
}

# 2. Determine Installation State
$pgInstalledPath = "C:\Program Files\PostgreSQL\16"
$pgService = Get-Service -Name "postgresql-x64-16" -ErrorAction SilentlyContinue

if ($null -eq $pgService -and -not (Test-Path "$pgInstalledPath\bin\postgres.exe")) {
    Write-Host "`n[1/4] Installing PostgreSQL 16..." -ForegroundColor Green
    
    # Try via winget first if available
    $winget = Get-Command "winget.exe" -ErrorAction SilentlyContinue
    $installedViaWinget = $false

    if ($null -ne $winget) {
        Write-Host "      - Found Windows Package Manager (winget). Installing PostgreSQL 16..."
        try {
            winget install --id PostgreSQL.PostgreSQL.16 --silent --accept-package-agreements --accept-source-agreements --exact
            $installedViaWinget = $true
        } catch {
            Write-Host "      - winget install returned non-zero, falling back to direct installer..." -ForegroundColor Yellow
        }
    }

    if (-not $installedViaWinget) {
        # Direct unattended download from EnterpriseDB
        $installerUrl = "https://get.enterprisedb.com/postgresql/postgresql-$PgVersion-windows-x64.exe"
        $installerPath = "$env:TEMP\postgresql-installer.exe"
        
        Write-Host "      - Downloading official PostgreSQL installer from EnterpriseDB..."
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
        Invoke-WebRequest -Uri $installerUrl -OutFile $installerPath -UseBasicParsing
        
        Write-Host "      - Running unattended silent installation..."
        $installArgs = @(
            "--mode", "unattended",
            "--superpassword", $SuperPassword,
            "--servicepassword", $SuperPassword,
            "--serverport", "$Port",
            "--enable-components", "server,commandlinetools"
        )
        Start-Process -FilePath $installerPath -ArgumentList $installArgs -Wait
        Remove-Item -Path $installerPath -Force -ErrorAction SilentlyContinue
    }
} else {
    Write-Host "`n[1/4] PostgreSQL 16 is already installed on this machine." -ForegroundColor Green
}

# 3. Ensure PostgreSQL Service is Running
Write-Host "`n[2/4] Starting PostgreSQL Service..." -ForegroundColor Green
$pgService = Get-Service -Name "postgresql-x64-16" -ErrorAction SilentlyContinue
if ($null -ne $pgService) {
    if ($pgService.Status -ne "Running") {
        Start-Service -Name "postgresql-x64-16"
        Start-Sleep -Seconds 3
    }
    Write-Host "      [+] PostgreSQL 16 service is active and running." -ForegroundColor Green
} else {
    Write-Host "      [!] Note: If running portable or custom service name, verify PostgreSQL is running on port $Port." -ForegroundColor Yellow
}

# 4. Install pgvector Binaries if Missing
Write-Host "`n[3/4] Checking and Installing pgvector Extension..." -ForegroundColor Green
$vectorDll = "$pgInstalledPath\lib\vector.dll"
if (-not (Test-Path $vectorDll)) {
    Write-Host "      - Downloading precompiled pgvector Windows binaries..."
    $pgvectorZipUrl = "https://github.com/pgvector/pgvector/releases/download/v0.8.0/pgvector_v0.8.0_pg16_windows_x64.zip"
    $zipPath = "$env:TEMP\pgvector.zip"
    $extractPath = "$env:TEMP\pgvector_extracted"
    
    try {
        Invoke-WebRequest -Uri $pgvectorZipUrl -OutFile $zipPath -UseBasicParsing
        Expand-Archive -Path $zipPath -DestinationPath $extractPath -Force
        
        # Copy DLL and control/sql files
        Copy-Item -Path "$extractPath\lib\vector.dll" -Destination "$pgInstalledPath\lib\" -Force
        Copy-Item -Path "$extractPath\share\extension\vector*" -Destination "$pgInstalledPath\share\extension\" -Force
        
        Remove-Item -Path $zipPath -Force -ErrorAction SilentlyContinue
        Remove-Item -Path $extractPath -Recurse -Force -ErrorAction SilentlyContinue
        Write-Host "      [+] pgvector binaries successfully installed into PostgreSQL 16." -ForegroundColor Green
    } catch {
        Write-Host "      [!] Could not auto-download pgvector: $_" -ForegroundColor Yellow
        Write-Host "          Please manually copy vector.dll into $pgInstalledPath\lib\"
    }
} else {
    Write-Host "      [+] pgvector binaries already present in $pgInstalledPath\lib\." -ForegroundColor Green
}

# 5. Initialize Python Environment and Schemas
Write-Host "`n[4/4] Setting up Python Environment & Database Schemas..." -ForegroundColor Green
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Resolve-Path "$ScriptDir\..\.."
Set-Location $ProjectRoot

# Create venv if not present
if (-not (Test-Path "$ProjectRoot\venv")) {
    Write-Host "      - Creating Python virtual environment (venv)..."
    python -m venv venv
}

# Install dependencies
Write-Host "      - Installing SYMPICS Python package in virtual environment..."
& "$ProjectRoot\venv\Scripts\pip.exe" install --upgrade pip -q
& "$ProjectRoot\venv\Scripts\pip.exe" install -e . -q

# Initialize Database
Write-Host "      - Running database initialization wizard..."
$env:SYMPICS_DB_PASSWORD = $SuperPassword
$env:PGPASSWORD = $SuperPassword
& "$ProjectRoot\venv\Scripts\python.exe" "$ProjectRoot\database\init_database.py"

Write-Host "`n===============================================================================" -ForegroundColor Cyan
Write-Host " [+] WINDOWS SETUP COMPLETE!" -ForegroundColor Green
Write-Host "===============================================================================" -ForegroundColor Cyan
Write-Host " To start SYMPICS Studio at any time, simply double-click:"
Write-Host "   $ProjectRoot\launchers\start_studio.bat" -ForegroundColor Yellow
Write-Host "==============================================================================="
