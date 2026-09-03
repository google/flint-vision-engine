@echo off
:: Copyright 2026 Google LLC
:: Licensed under Apache 2.0

echo ===============================================================================
echo  [*] INSTALLING SYMPICS SUPERVISOR AUTO-START SERVICE (WINDOWS TASK)
echo ===============================================================================

:: Check for Administrator Privileges
net session >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo [!] ERROR: Administrator privileges required.
    echo     Please right-click this file and select 'Run as Administrator'.
    pause
    exit /b 1
)

set "SCRIPT_PATH=%~dp0sympics_service_supervisor.ps1"

echo  [*] Registering scheduled task to start at Windows boot...
schtasks /create /tn "SYMPICS_Service_Supervisor" /tr "powershell.exe -ExecutionPolicy Bypass -WindowStyle Hidden -File \"%SCRIPT_PATH%\"" /sc onstart /ru SYSTEM /rl HIGHEST /f

if %ERRORLEVEL% equ 0 (
    echo.
    echo  [+] SUCCESS: SYMPICS_Service_Supervisor registered!
    echo  [+] Persistent Behavior:
    echo      1. Starts automatically on Windows boot.
    echo      2. Launches Web Studio and Intake Daemon in background.
    echo      3. Continually health-checks both processes every 5 seconds.
    echo      4. Automatically restarts them if they crash, hang, or stop responding.
    echo.
    echo  [*] Starting the supervisor task now...
    schtasks /run /tn "SYMPICS_Service_Supervisor"
    echo  [+] Active and running. Open http://localhost:8080 in your browser.
) else (
    echo [!] Task creation failed.
)

echo ===============================================================================
pause
