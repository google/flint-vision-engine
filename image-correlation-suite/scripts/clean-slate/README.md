# SYMPICS Clean Slate Protocol

## Overview

The **Clean Slate Protocol** (`clean_slate_protocol.py`) is an administrative reset utility designed to purge all operational case records, vector embeddings, and media vault files, returning the SYMPICS platform to a pristine initial baseline.

---

## What It Does

When executed, the Clean Slate Protocol performs two destructive operations:

### 1. Database Table Truncation (`sympics_db`)
Executes `TRUNCATE TABLE ... RESTART IDENTITY CASCADE` across all operational evidence tables:
* `media_assets` & `media_embeddings` (All images, videos, and multi-model vector embeddings)
* `cases` & `case_evidence_items` (All investigative case containers and tagged evidence)
* `case_evidence_actions` & `comparison_matches` (Investigative correlation logs)
* `video_keyframes` (Extracted video scene changes and timestamps)
* `migration_manifest` (Phase 1 & Phase 2 legacy ingestion ledger)
* `verification_audit_log` (Evidence audit events)

*(Reference catalog tables, such as pre-imported reference/intelligence hash lists, are preserved unless manually truncated).*

### 2. File Storage Vault Reset (`future-lan-storage/`)
Purges all physical files and subfolders within the storage root and regenerates the canonical folder skeleton:
* `01_Media_Vault/images/`
* `01_Media_Vault/videos/`
* `02_Keyframe_Vault/thumbs_256px/`
* `02_Keyframe_Vault/thumbs_512px/`
* `03_Ingestion_Staging/`
* `04_Forensic_Exports/`
* `05_Audit_Logs/`

---

## When to Use the Clean Slate Protocol

The Clean Slate Protocol is intended **only** for specific administrative milestones:

1. **Pre-Production Handover (Recommended):**
   * Before deploying the server to active investigative units, run Clean Slate to wipe all developer test images, synthetic mock data, and test cases.
2. **Initial Ingestion Dry-Run Reset:**
   * If an initial legacy data migration was run with incorrect parameters (e.g. wrong directory paths or test batches) and you need to start the migration from scratch.
3. **Lab / Server Re-allocation:**
   * When re-purposing the forensic workstation for a different squad, unit, or testing environment.
4. **Court-Mandated Evidence Decommissioning:**
   * After a closed case archive has been sealed, verified, and transferred to long-term cold custody, and the local operational server must be sanitized.

---

## When NEVER to Use the Clean Slate Protocol

> [!CAUTION]
> **DO NOT USE DURING ACTIVE INVESTIGATIONS!**
> 
> * This operation is **irreversible**.
> * It will permanently delete all ingested media, generated thumbnails, AI vectors, and active case notes.
> * If active evidence exists on this server, ensure a complete, verified external backup is made prior to execution.

---

## How to Execute

### Windows Systems
Double-click `scripts\clean-slate\run_clean_slate.bat` *(includes interactive confirmation prompt)*.

Or execute manually via Command Prompt / PowerShell:
```cmd
python scripts\clean-slate\clean_slate_protocol.py
```

### Linux / macOS Systems
```bash
python3 scripts/clean-slate/clean_slate_protocol.py
```
