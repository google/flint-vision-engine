# SYMPICS Windows Deployment & Supervisor Tools

This directory contains native Windows administration, setup, and process supervisor tools.

## Tools

* **`setup_windows_prerequisites.ps1`**:
  * Automated 1-command bootstrapper for Windows workstations.
  * Installs PostgreSQL 16 silently via `winget` or direct installer.
  * Deploys pre-compiled `pgvector` binaries (`vector.dll`, `vector.control`, `vector--*.sql`) into PostgreSQL `lib/` and `share/extension/`.
  * Creates Python virtual environment (`.\venv`) and installs the `sympics` package.
  * Initializes the `sympics_db` database and vector HNSW indexes.

* **`sympics_service_supervisor.ps1`**:
  * Native Windows process watchdog and health supervisor.
  * Monitors both the Web Studio server (`web/server.py`) and Intake Daemon (`scripts/daemons/sympics_intake_daemon.py`).
  * Performs active HTTP GET health probes on `http://127.0.0.1:8080/`.
  * Automatically restarts either process if it crashes, hangs, or stops responding.

* **`install_windows_supervisor_task.bat`**:
  * Registers `sympics_service_supervisor.ps1` as a Windows Scheduled Task running at system startup (`/sc onstart`) with `SYSTEM` / `HIGHEST` privileges.
  * Guarantees 24/7 autonomous persistence and self-healing across reboots.

* **`uninstall_windows_supervisor_task.bat`**:
  * Cleanly unregisters the supervisor scheduled task.
