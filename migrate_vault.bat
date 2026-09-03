@echo off
:: Copyright 2026 Google LLC
:: Licensed under Apache 2.0

echo ===============================================================================
echo  [*] SYMPICS: PHASE 2 SUPERVISED MIGRATION & AI VECTOR EMBEDDING
echo ===============================================================================
python scripts\filesystem-migration\migrate_vault_worker.py -v future-lan-storage
echo.
pause
