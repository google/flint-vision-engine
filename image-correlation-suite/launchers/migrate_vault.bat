@echo off
:: Copyright 2026 Google LLC
:: Licensed under Apache 2.0

echo ===============================================================================
echo  [*] SYMPICS: PHASE 2 SUPERVISED MIGRATION & AI VECTOR EMBEDDING
echo ===============================================================================
cd /d "%~dp0\.."

if exist "venv\Scripts\python.exe" (
    set "PYTHON_EXE=venv\Scripts\python.exe"
) else (
    set "PYTHON_EXE=python"
)

"%PYTHON_EXE%" scripts\filesystem-migration\migrate_vault_worker.py -v future-lan-storage
echo.
pause
