@echo off
:: Copyright 2026 Google LLC
:: Licensed under Apache 2.0

echo ===============================================================================
echo  [*] SYMPICS: PHASE 1 READ-ONLY DISCOVERY SCAN
echo ===============================================================================
cd /d "%~dp0\.."

if exist "venv\Scripts\python.exe" (
    set "PYTHON_EXE=venv\Scripts\python.exe"
) else (
    set "PYTHON_EXE=python"
)

"%PYTHON_EXE%" scripts\filesystem-migration\scan_legacy_manifest.py -s future-lan-storage\03_Ingestion_Staging
echo.
pause
