@echo off
:: Copyright 2026 Google LLC
:: Licensed under Apache 2.0

echo ===============================================================================
echo  [*] SYMPICS: PHASE 1 READ-ONLY DISCOVERY SCAN
echo ===============================================================================
python scripts\filesystem-migration\scan_legacy_manifest.py -s future-lan-storage\03_Ingestion_Staging
echo.
pause
