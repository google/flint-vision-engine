@echo off
:: Copyright 2026 Google LLC
:: Licensed under Apache 2.0

echo ===============================================================================
echo  [*] UNINSTALLING SYMPICS SUPERVISOR WINDOWS TASK
echo ===============================================================================

net session >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo [!] ERROR: Administrator privileges required.
    echo     Please right-click this file and select 'Run as Administrator'.
    pause
    exit /b 1
)

schtasks /delete /tn "SYMPICS_Service_Supervisor" /f
if %ERRORLEVEL% equ 0 (
    echo  [+] Successfully removed SYMPICS_Service_Supervisor task.
) else (
    echo  [!] Task not found or already removed.
)

echo ===============================================================================
pause
