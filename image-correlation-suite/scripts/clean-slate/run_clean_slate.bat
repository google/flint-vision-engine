@echo off
:: Copyright 2026 Google LLC
:: Licensed under Apache 2.0

echo ===============================================================================
echo  [!] WARNING: SYMPICS CLEAN SLATE PROTOCOL
echo ===============================================================================
echo  This operation will IRREVERSIBLY WIPE:
echo    1. All media assets and vector embeddings in PostgreSQL (sympics_db).
echo    2. All case evidence containers and audit logs.
echo    3. All physical files in future-lan-storage/ (Media Vault, Thumbnails).
echo ===============================================================================
echo.
set /p CONFIRM="Are you absolutely sure you want to proceed? (Type YES to confirm): "

if /i "%CONFIRM%"=="YES" (
    echo.
    echo [*] Executing Clean Slate Protocol...
    python "%~dp0clean_slate_protocol.py"
) else (
    echo.
    echo [-] Clean Slate Protocol cancelled by user. No data was modified.
)

echo.
pause
