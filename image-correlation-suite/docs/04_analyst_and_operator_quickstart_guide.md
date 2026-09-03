# SYMPICS Migration & Operations Quickstart Guide
## Step-by-Step Operator Manual for System Administrators & Analysts

---

### Overview

This quickstart guide provides the direct commands, script executions, and troubleshooting procedures needed to operate the SYMPICS Migration Pipeline and monitor the PostgreSQL database.

*For barebones Windows installations without PostgreSQL, refer to the [Windows Workstation Setup Guide](05_windows_workstation_setup_guide.md).*

---

### Complete Operations Command Matrix

| Task | Linux / macOS Command | Windows Command / Shortcut | Output / Expected Result |
| :--- | :--- | :--- | :--- |
| **1. Initialize Storage Vault** | `python3 scripts/filesystem-migration/build_hex_vault_structure.py` | Double-click `launchers\build_vault.bat` | Generates 65,536 hex buckets (`00/00` to `ff/ff`). |
| **2. Initialize PostgreSQL** | `python3 database/init_database.py` | `python database/init_database.py` | Applies core schemas, triggers, and pgvector extension. |
| **3. Start Studio** | `python3 web/server.py` | Double-click `launchers\start_studio.bat` | Launches Web Studio on `http://localhost:8080`. |
| **4. 24/7 Auto-Restart Supervisor** | `systemctl start sympics-watchdog` | Run `scripts\windows\install_windows_supervisor_task.bat` (Admin) | Keeps Web Studio and Intake Daemon alive 24/7 with auto-restart. |
| **5. Run Phase 1 Discovery** | `python3 scripts/filesystem-migration/scan_legacy_manifest.py -s <path>` | Double-click `launchers\scan_manifest.bat` | Read-only scan; catalogs files into `migration_manifest`. |
| **6. Run Phase 2 Ingestion** | `python3 scripts/filesystem-migration/migrate_vault_worker.py -v <path>` | Double-click `launchers\migrate_vault.bat` | Embeds AI vectors, copies to vault, verifies readback. |
| **7. Clean Slate Protocol** | `python3 scripts/clean-slate/clean_slate_protocol.py` | Double-click `scripts\clean-slate\run_clean_slate.bat` | Clears all tables & resets storage vault to pristine state. |

---

### Step-by-Step Execution Walkthrough

#### Step 1: Initialize the Master Storage Vault
Builds the two-layer hexadecimal tree on the target Storage LAN drive:
```bash
python3 scripts/filesystem-migration/build_hex_vault_structure.py -t /path/to/future-lan-storage
```
* **Time:** ~5 to 10 seconds.
* **Output:** Creates `01_Media_Vault/images/`, `01_Media_Vault/videos/`, and `02_Keyframe_Vault/thumbs_256px/`.

---

#### Step 2: Initialize Database Schemas
Creates the PostgreSQL database and tables (`migration_manifest`, `media_assets`, `media_embeddings`, `case_evidence_items`):
```bash
python3 database/init_database.py
```

---

#### Step 3: Launch the Real-Time Web Dashboard
Start the monitoring dashboard to observe ingestion in real time:
```bash
python3 database/dashboard.py
```
* **Local Access:** Open `http://localhost:8085`
* **Remote Workstation Access (SSH Tunnel):**
  ```bash
  ssh -L 8085:localhost:8085 <user>@<server-ip>
  ```
  Then open `http://localhost:8085` in your browser.

---

#### Step 4: Run Phase 1 — Read-Only Discovery
Point the scanner at the legacy media folder:
```bash
python3 scripts/filesystem-migration/scan_legacy_manifest.py -s /path/to/legacy-storage
```
* **Behavior:** 100% read-only. Extracts SHA-256, MD5, SHA-1, sizes, and timestamps.
* **Speed:** ~1,000 to 2,000 files/second.

---

#### Step 5: Run Phase 2 — AI Embedding & Verified Copy
Execute the ingestion worker to safely copy and verify data into the vault:
```bash
python3 scripts/filesystem-migration/migrate_vault_worker.py -v /path/to/future-lan-storage
```
* **Behavior:** Generates 768-dim SigLIP vectors and 256px WebP thumbnails, copies to hex vault, and validates readback SHA-256 before marking `VERIFIED_COPIED`.

---

### Database Audit & Verification Commands

To check database migration status via command line at any time:

```bash
# View Summary Statistics
psql -d sympics_db -c "SELECT * FROM v_migration_summary;"

# View Ingestion Status Breakdown
psql -d sympics_db -c "SELECT status, count(*) FROM migration_manifest GROUP BY status;"

# Check for Any Failed / Corrupt Records
psql -d sympics_db -c "SELECT manifest_id, source_filename, error_message FROM migration_manifest WHERE status LIKE 'FAILED%';"
```

---

### Step 6: Air-Gapped & Offline Model Provisioning

Because secure air-gapped production workstations have no direct internet access, model weights can be pre-downloaded on an internet-connected workstation and transferred via secure storage media.

#### 1. Where to Download Models (Choose Method A or B)

* **Method A: Automated 1-Click Script (Recommended)**
  * On Windows: Double-click `launchers\download_models.bat`
  * On Linux / macOS:
    ```bash
    python3 scripts/maintenance/download_offline_models.py --target-dir ./models --models all
    ```

* **Method B: Manual Hugging Face CLI**
  ```bash
  # 1. SigLIP-2 NaFlex (768-dim)
  huggingface-cli download google/siglip2-base-patch16-naflex --local-dir ./models/siglip2-base-patch16-naflex

  # 2. SigLIP Base (768-dim)
  huggingface-cli download google/siglip-base-patch16-224 --local-dir ./models/siglip-base-patch16-224

  # 3. CLIP ViT-B/32 (512-dim)
  huggingface-cli download openai/clip-vit-base-patch32 --local-dir ./models/clip-vit-base-patch32
  ```

#### 2. Where to Put Models on the Production Server

Copy the downloaded `models/` directory into the **root of the `image-correlation-suite/` project**:

```text
image-correlation-suite/
├── models/                               <-- PLACE MODELS DIRECTORY HERE
│   ├── siglip2-base-patch16-naflex/
│   │   ├── config.json
│   │   ├── model.safetensors
│   │   └── preprocessor_config.json
│   ├── siglip-base-patch16-224/
│   │   ├── config.json
│   │   └── model.safetensors
│   └── clip-vit-base-patch32/
│       ├── config.json
│       └── model.safetensors
├── web/
└── sympics/
```

* **Custom Storage Location (Optional):** If you store models on a separate dedicated drive (e.g. `D:\AI_Models`), simply set the path in `.env`:
  ```ini
  SYMPICS_MODELS_DIR=D:\AI_Models
  ```
* **Offline Verification:** When the web server or intake daemon starts, it scans `./models/` first. If local files are detected, it loads weights strictly offline with `local_files_only=True` (zero internet required).

#### 3. Special Procedure for Meta DINOv3 (Gated Model Approval)

Unlike SigLIP and CLIP (which are completely open-access), **Meta DINOv3** is a gated research model that requires an approved Hugging Face account:

1. **Create or Log In to Hugging Face:** Go to [huggingface.co/join](https://huggingface.co/join).
2. **Request Access from Meta:**
   * Navigate to the repository: [https://huggingface.co/facebook/dinov3-vit-b-16](https://huggingface.co/facebook/dinov3-vit-b-16).
   * Review Meta's License and click **"Acknowledge license / Request access"**.
   * Approval is typically granted automatically or within a few hours.
3. **Generate a Personal Read Token:**
   * In Hugging Face, go to **Settings $\rightarrow$ Access Tokens** ([huggingface.co/settings/tokens](https://huggingface.co/settings/tokens)).
   * Click **"Create new token"**, name it `sympics-downloader`, and select permissions: **`Read`**.
   * Copy your generated token (starts with `hf_...`).
4. **Download DINOv3 Using Your Token:**
   ```bash
   # Using the SYMPICS automated downloader:
   python3 scripts/maintenance/download_offline_models.py --target-dir ./models --models dinov3 --hf-token <YOUR_HF_TOKEN>

   # Or using huggingface-cli:
   huggingface-cli download facebook/dinov3-vit-b-16 --token <YOUR_HF_TOKEN> --local-dir ./models/dinov3-vit-b-16
   ```
   *(Note: The platform functions completely with SigLIP-2, SigLIP Base, and CLIP even if DINOv3 is omitted).*

---

### Step 7: High-Performance Hardware & Database Optimization (128 GB RAM Tier)

To achieve maximum throughput during vector searches and million-file batch ingestion:

1. **Locate your `postgresql.conf`:**
   * **Windows:** `C:\Program Files\PostgreSQL\16\data\postgresql.conf`
   * **Linux:** `/etc/postgresql/16/main/postgresql.conf`
2. **Apply settings from `database/postgresql_tuning_128gb.conf`:**
   ```ini
   # Memory Configuration (Tuned for 128 GB RAM)
   shared_buffers = 32GB          # Keeps active HNSW vector index nodes in RAM
   work_mem = 64MB
   maintenance_work_mem = 4GB     # Ultra-fast parallel HNSW index building
   effective_cache_size = 80GB

   # CPU Concurrency (Tuned for Threadripper / 24+ CPU Threads)
   max_worker_processes = 24
   max_parallel_workers = 16
   max_parallel_maintenance_workers = 6
   max_parallel_workers_per_gather = 4

   # NVMe Storage Optimization
   random_page_cost = 1.1
   effective_io_concurrency = 200
   ```
3. **Restart PostgreSQL** to apply the configuration.


