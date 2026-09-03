@echo off
:: Copyright 2026 Google LLC
:: Licensed under Apache 2.0

echo ===============================================================================
echo  [*] SYMPICS: PRE-ALLOCATING 65,536 HEXADECIMAL CAS VAULT BUCKETS
echo ===============================================================================
cd /d "%~dp0\.."

if exist "venv\Scripts\python.exe" (
    set "PYTHON_EXE=venv\Scripts\python.exe"
) else (
    set "PYTHON_EXE=python"
)

"%PYTHON_EXE%" scripts\filesystem-migration\build_hex_vault_structure.py -t future-lan-storage
echo.
pause
