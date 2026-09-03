@echo off
:: Copyright 2026 Google LLC
:: Licensed under Apache 2.0

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
