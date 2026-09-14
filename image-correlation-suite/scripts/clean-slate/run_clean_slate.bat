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
