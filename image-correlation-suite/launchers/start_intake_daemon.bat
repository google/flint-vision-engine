@echo off
:: Copyright 2026 Google LLC
:: Licensed under Apache 2.0

setlocal enabledelayedexpansion

title SYMPICS Automated Ingestion Daemon

echo ===============================================================================
echo  [*] STARTING SYMPICS INTAKE DAEMON (WATCHING STAGING FOLDER)
echo ===============================================================================

cd /d "%~dp0\.."

if exist "venv\Scripts\python.exe" (
    set "PYTHON_EXE=venv\Scripts\python.exe"
) else (
    set "PYTHON_EXE=python"
)

echo  [+] Drop files or folders into your staging directory to auto-process.
echo  [+] Press Ctrl+C in this window to stop the intake daemon.
echo ===============================================================================
"%PYTHON_EXE%" scripts\daemons\sympics_intake_daemon.py

pause
