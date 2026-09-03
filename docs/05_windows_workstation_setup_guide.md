# SYMPICS Windows Workstation Setup Guide
## Complete Installation Manual for Barebones Windows Systems

---

### Overview

This guide provides step-by-step instructions for setting up the **SYMPICS Intelligent Media Platform** on a fresh Windows workstation (Windows 10, 11, or Windows Server) that does **not** have PostgreSQL or AI dependencies pre-installed.

---

### Prerequisites Checklist

* **Operating System:** Windows 10 / 11 (64-bit) or Windows Server 2019 / 2022.
* **Hardware:** 16GB+ RAM (128GB recommended for massive scale) + SSD / NVMe drive.
* **Python:** Python 3.10, 3.11, 3.12, or 3.13 (Ensure "Add Python to PATH" is checked during install).
* **NVIDIA GPU (Optional):** NVIDIA RTX GPU with latest drivers for CUDA hardware acceleration.

---

### Method 1: Automated Setup (Fastest / Recommended)

We have provided an automated PowerShell setup script that installs PostgreSQL 16, configures the `pgvector` AI extension, builds your Python virtual environment, and initializes the database in a single run.

#### Step 1: Open PowerShell as Administrator
1. Press the Windows Key and type **PowerShell**.
2. Right-click **Windows PowerShell** and select **Run as administrator**.

#### Step 2: Run the Setup Script
Navigate to the extracted `image-correlation-suite` directory and execute:

```powershell
Set-ExecutionPolicy Bypass -Scope Process -Force
.\scripts\windows\setup_windows_prerequisites.ps1
```

#### What this script does automatically:
1. Checks for and installs **PostgreSQL 16** via `winget` or direct silent installer.
2. Starts the `postgresql-x64-16` Windows service.
3. Downloads and installs the pre-compiled **`pgvector`** Windows binaries into PostgreSQL.
4. Creates a Python virtual environment (`.\venv`) and installs all required dependencies.
5. Runs the schema initialization wizard to create `sympics_db` and vector indexes.

---

### Method 2: Manual Step-by-Step Installation

If your IT policies restrict automated PowerShell package downloads, follow these manual steps:

#### Step 1: Install PostgreSQL 16
1. Download the official installer: [EnterpriseDB PostgreSQL 16 Windows Installer](https://www.enterprisedb.com/downloads/postgres-postgresql-downloads).
2. Run the `.exe` installer.
3. Keep default installation path (`C:\Program Files\PostgreSQL\16`).
4. Select components: **PostgreSQL Server**, **pgAdmin 4**, and **Command Line Tools**.
5. Set a password for the `postgres` superuser (e.g. `sympics_secure_password`). Keep Port at `5432`.
6. Complete the installation.

#### Step 2: Install the `pgvector` AI Extension
Because PostgreSQL for Windows does not include `pgvector` by default:
1. Download the pre-compiled Windows release from GitHub: [pgvector Releases](https://github.com/pgvector/pgvector/releases) (e.g., `pgvector_v0.8.0_pg16_windows_x64.zip`).
2. Extract the ZIP archive.
3. Copy the files into your PostgreSQL directory:
   * Copy `lib\vector.dll` $\rightarrow$ `C:\Program Files\PostgreSQL\16\lib\`
   * Copy `share\extension\vector.control` and `share\extension\vector--*.sql` $\rightarrow$ `C:\Program Files\PostgreSQL\16\share\extension\`

#### Step 3: Setup Python Virtual Environment
Open Command Prompt in `image-correlation-suite`:
```cmd
python -m venv venv
venv\Scripts\activate
pip install -e .
```

#### Step 4: Initialize the Database Schemas
Run the interactive database creation wizard:
```cmd
python database\init_database.py
```
Enter your PostgreSQL password when prompted. The wizard creates the database and tests `pgvector` connectivity.

#### Step 5: Transfer Offline AI Model Weights (Air-Gap Setup)
1. On an internet-connected computer, double-click **`download_models.bat`** (or run `python scripts\maintenance\download_offline_models.py --target-dir models --models all`).
2. Copy the resulting **`models\`** folder to an encrypted USB drive.
3. Paste the **`models\`** folder directly into the root of `image-correlation-suite\` on the target workstation:
   ```text
   image-correlation-suite\
   └── models\
       ├── siglip2-base-patch16-naflex\
       ├── siglip-base-patch16-224\
       └── clip-vit-base-patch32\
   ```
   *(The server and intake daemon will automatically detect and load from `models\` in 100% offline mode).*
   *(Note for Meta DINOv3: DINOv3 is a gated model requiring a Hugging Face token. See [Operations Manual](04_analyst_and_operator_quickstart_guide.md#3-special-procedure-for-meta-dinov3-gated-model-approval) for the 4-step approval instructions. SigLIP-2, SigLIP Base, and CLIP require zero tokens or approval).*

---

### Day-to-Day Operation (1-Click Launchers)

Once installation is complete, operators never need to use terminal commands:

#### 1. Launch Studio (Web UI)
* **Double-click `start_studio.bat`** in the project root folder.
* This automatically checks that PostgreSQL is active, starts the web server, and opens your default browser to **`http://localhost:8080`**.

#### 2. Launch the Automated Intake Daemon (Optional)
* **Double-click `start_intake_daemon.bat`**.
* This monitors your ingestion drop folder (`future-lan-storage/03_Ingestion_Staging`) and automatically processes new files or camera RAW images in real time.

#### 3. Setup Persistent 24/7 Auto-Restarting Daemons (Supervisor Service)
* **Right-click `scripts\windows\install_windows_supervisor_task.bat` and select 'Run as Administrator'**.
* This registers `sympics_service_supervisor.ps1` as a permanent Windows Scheduled Task that:
  1. Starts automatically whenever the Windows workstation boots.
  2. Runs both the Web Server and Intake Daemon in the background.
  3. Actively health-checks both processes every 5 seconds.
  4. Automatically restarts them if they crash, hang, or stop responding.
* To uninstall or disable: Right-click `scripts\windows\uninstall_windows_supervisor_task.bat` and Run as Administrator.

---

### Troubleshooting Windows Deployments

| Issue | Cause | Solution |
| :--- | :--- | :--- |
| **"Python was not found"** | Python is not on system PATH. | Re-run Python installer and ensure **"Add python.exe to PATH"** is checked. |
| **"Could not connect to server"** | PostgreSQL service stopped. | Open Command Prompt as Admin and run: `net start postgresql-x64-16`. |
| **"Extension 'vector' not found"** | `vector.dll` not in PostgreSQL `lib\`. | Verify `vector.dll` is inside `C:\Program Files\PostgreSQL\16\lib\`. |
| **"Permission Denied" in PowerShell** | Windows script execution policy. | Run `Set-ExecutionPolicy Bypass -Scope Process -Force` before running scripts. |
