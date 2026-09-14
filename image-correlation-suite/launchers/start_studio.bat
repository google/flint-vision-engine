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
setlocal enabledelayedexpansion

title SYMPICS Correlation Studio

echo ===============================================================================
echo  [*] STARTING SYMPICS CORRELATION STUDIO
echo ===============================================================================

:: 1. Navigate to Project Root Directory
cd /d "%~dp0\.."

:: 2. Check and start PostgreSQL Service if present
sc query "postgresql-x64-16" >nul 2>&1
if %ERRORLEVEL% equ 0 (
    net start postgresql-x64-16 >nul 2>&1
)

:: 3. Select Python Executable (Virtual environment preferred)
if exist "venv\Scripts\python.exe" (
    set "PYTHON_EXE=venv\Scripts\python.exe"
) else (
    set "PYTHON_EXE=python"
)

:: 4. Verify Python is Available
"%PYTHON_EXE%" --version >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo [!] ERROR: Python was not found on your system PATH or in .\venv.
    echo     Please install Python 3.10+ or run scripts\windows\setup_windows_prerequisites.ps1
    pause
    exit /b 1
)

:: 5. Detect Port from .env or default to 8080
set "PORT=8080"
if exist ".env" (
    for /f "usebackq tokens=1,2 delims==" %%a in (".env") do (
        if /i "%%a"=="SYMPICS_WEB_PORT" set "PORT=%%b"
    )
)

:: 6. Open Web Browser to Studio after brief pause
start "" cmd /c "timeout /t 3 /nobreak >nul & start http://localhost:!PORT!"

:: 7. Launch SYMPICS Web Server
echo  [+] Web Server starting on port !PORT!...
echo  [+] Opening http://localhost:!PORT! in your default browser...
echo.
echo  Press Ctrl+C in this window to stop the server when done.
echo ===============================================================================
"%PYTHON_EXE%" web\server.py --port !PORT!

pause
