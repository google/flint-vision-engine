# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

@echo off
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
