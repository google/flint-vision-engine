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

python scripts\maintenance\download_offline_models.py --target-dir .\models --models all

echo.
echo ===============================================================================
echo  [+] Download complete. Models are stored in .\models\
echo  [+] You can now copy the .\models\ directory to an encrypted USB drive
echo      and transfer it to your air-gapped forensic workstation.
echo ===============================================================================
pause
