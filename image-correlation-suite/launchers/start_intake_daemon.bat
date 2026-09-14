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
