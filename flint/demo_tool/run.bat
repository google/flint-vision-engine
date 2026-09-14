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
rem Copyright 2026 Google LLC
rem Licensed under Apache 2.0
rem FLINT Vision Engine launcher for Windows

cd /d "%~dp0"

echo ==================================================
echo ⚡ Launching FLINT Vision Engine...
echo ==================================================

python -c "import torch, transformers, huggingface_hub" >nul 2>&1
if %errorlevel% neq 0 (
    echo 📦 Checking and installing required dependencies via pip...
    python -m pip install -r requirements.txt
)

python app.py %*
if %errorlevel% neq 0 (
    echo.
    echo ⚠️ Engine stopped with error code: %errorlevel%
    pause
)
