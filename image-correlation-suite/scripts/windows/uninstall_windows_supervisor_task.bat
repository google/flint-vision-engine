@REM Copyright 2026 Google LLC
@REM
@REM Licensed under the Apache License, Version 2.0 (the "License");
@REM you may not use this file except in compliance with the License.
@REM You may obtain a copy of the License at
@REM
@REM     https://www.apache.org/licenses/LICENSE-2.0
@REM
@REM Unless required by applicable law or agreed to in writing, software
@REM distributed under the License is distributed on an "AS IS" BASIS,
@REM WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
@REM See the License for the specific language governing permissions and
@REM limitations under the License.

@echo off
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
