# SYMPICS Data Ingestion & Intelligence Feed Services

## Overview

This directory contains the **active data ingestion services, automated folder watchers, and intelligence feed catalog importers** for Project SYMPICS / SYMPICS.

Unlike the one-time lift-and-shift tools in `filesystem-migration/`, the scripts in this directory represent **ongoing operational intake pipelines** used during active investigations.

---

## Scripts & Services

| Script | Purpose |
| :--- | :--- |
| **`import_reference_csv.py`** | Imports reference intelligence CSV hash dumps into `reference_catalog_records` and runs real-time collision detection queries against evidence in `media_assets`. |
| **`scripts/daemons/sympics_intake_daemon.py`** | Continuous background daemon monitoring `03_Ingestion_Staging` drop-folders for new evidence, performing automatic hashing, CAS vault placement, thumbnailing, camera RAW extraction, 3-model GPU embeddings, and instant reference collision alerts. |

---

## Usage Guide

### 1. Import Reference Intelligence CSV
```bash
python3 import_reference_csv.py --csv-file ../../sample-data/reference_hashes_fake.csv
```
* **What it does:**
  1. Parses CSV hash records (`MD5`, `SHA-1`, `series_name`, `flag_identified`, `flag_actionable`).
  2. Batch-inserts records into `reference_catalog_records` in PostgreSQL `sympics_db`.
  3. Executes instant collision queries (`v_reference_known_collisions`) against all evidence assets in the vault.
  4. Displays summary statistics and flags matching evidence items with confirmed status flags.
