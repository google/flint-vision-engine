# SYMPICS Background Daemons & Services

This directory contains continuous background daemons that automate data ingestion and system monitoring.

## Daemons

* **`sympics_intake_daemon.py`**:
  * Watches `03_Ingestion_Staging/` for dropped evidence files and unpacked archives.
  * Enforces stability delay before processing to ensure complete network copies.
  * Automatically calculates simultaneous SHA-256/MD5/SHA-1 hashes, parses EXIF/GPS, extracts camera RAW embedded previews, generates 256px WebP thumbnails, and embeds tri-vector AI embeddings.
  * Copies verified assets into the Content-Addressable Storage (CAS) vault and moves corrupted files to `_quarantine/`.

* **`sympics_watchdog.py`**:
  * Linux daemon supervisor.
  * Actively monitors PID liveness and HTTP health checks on `http://127.0.0.1:8080/api/telemetry`.
  * Automatically restarts services upon crash, hang, or unhandled termination with exponential backoff protection.

## Systemd Service Units (Linux)

* **`sympics-web.service`**: Systemd unit for managing the Web Studio server.
* **`sympics-intake.service`**: Systemd unit for managing the automated intake daemon.
* **`sympics-watchdog.service`**: Systemd unit for the watchdog process.
