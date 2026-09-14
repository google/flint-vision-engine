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
echo  [*] SYMPICS: OFFLINE AI VISION MODEL DOWNLOADER
echo ===============================================================================
echo  This script downloads AI vision transformer weights from Hugging Face
echo  into the local .\models\ directory for air-gapped / offline deployment.
echo ===============================================================================
echo.

cd /d "%~dp0\.."

if exist "venv\Scripts\python.exe" (
    set "PYTHON_EXE=venv\Scripts\python.exe"
) else (
    set "PYTHON_EXE=python"
)

"%PYTHON_EXE%" scripts\maintenance\download_offline_models.py --target-dir .\models --models all

echo.
echo ===============================================================================
echo  [+] Download complete. Models are stored in .\models\
echo  [+] You can now copy the .\models\ directory to an encrypted storage drive
echo      and transfer it to your air-gapped analysis workstation.
echo ===============================================================================
pause
