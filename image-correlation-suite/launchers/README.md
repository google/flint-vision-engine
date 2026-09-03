# SYMPICS 1-Click Launchers (Windows)

This directory contains pre-configured 1-click batch scripts for operating the SYMPICS Image Correlation Suite on Windows workstations.

Each launcher automatically resolves virtual environments (`.\venv\Scripts\python.exe`) and sets the execution context to the project root directory.

---

## Available Launchers

| Launcher | Purpose | Description |
| :--- | :--- | :--- |
| **`start_studio.bat`** | Web Studio UI | Starts the PostgreSQL service (if configured), spins up the local Python web server, and opens `http://localhost:8080` in your default browser. |
| **`start_intake_daemon.bat`** | Automated Intake | Starts the background file-watcher daemon monitoring the configured staging directory for newly added media assets. |
| **`open_documentation.bat`** | HTML Documentation | Opens the comprehensive HTML offline documentation suite (`docs\html\index.html`) in your default web browser. |
| **`download_models.bat`** | Offline Model Packager | Downloads all required transformer and embedding model weights into `.\models\` for air-gapped system deployments. |
| **`build_vault.bat`** | Storage Vault Setup | Pre-allocates the 65,536 hexadecimal CAS bucket structure (`00/00` to `ff/ff`) in the target storage directory. |
| **`scan_manifest.bat`** | Phase 1 Discovery | Performs a non-destructive, read-only discovery scan of staged files and catalogs them into the database manifest. |
| **`migrate_vault.bat`** | Phase 2 Vault Ingestion | Computes multi-model vector embeddings, copies files to the content-addressed storage (CAS) vault, and validates readback checksums. |

---

## Notes
- To configure ports, storage paths, or database credentials, edit the `.env` file located in the project root directory.
- For 24/7 background service installation (auto-restart supervisor), see `scripts\windows\install_windows_supervisor_task.bat`.
