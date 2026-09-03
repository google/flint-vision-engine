# SYMPICS Forensic Web Studio & REST API

The web tier hosting the investigative user interface, REST API endpoints, and CAS static asset streaming.

## Components
* **`server.py`**: Multi-threaded HTTP server (Port 8080) with CORS protection, path traversal defenses, static documentation serving (`/docs/`), and health probes (`/healthz`, `/readyz`, `/api/telemetry`).
* **`api_service.py`**: Core REST API business logic for natural language search, reverse-image search, series management, case linking, and sandboxed SQL queries.
* **`index.html`**: Zero-dependency, self-contained Forensic Studio single-page application with dark-mode UI, image gallery grid, bounding-box crop tool, multi-model matrix, and case organizer.
