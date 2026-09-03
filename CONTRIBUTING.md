# SYMPICS Forensic Intelligence Platform — Contributor & Development Guide

---

## 1. Git Branching & Workflow Policy

To maintain repository stability and ensure strict data hygiene, all contributors and client engineers must adhere to the following branching strategy:

### Branch Structure
* **`main`**: Protected production branch. Represents tested, stable platform releases. Direct commits are restricted.
* **`develop`**: Integration branch for ongoing feature consolidation.
* **`feature/<feature-name>`**: Branch for new features or model integrations (e.g. `feature/dinov3-search`).
* **`fix/<bug-name>`**: Branch for defect remediation (e.g. `fix/crop-canvas-scaling`).
* **`docs/<topic>`**: Documentation updates and architecture specifications.

### Pull Request & Review Process
1. **Fork or Branch:** Create a feature branch off `develop` (or `main` for hotfixes).
2. **Local Verification:** Run the test suite (`pytest tests/`) and linter (`ruff check .`) prior to submitting.
3. **Open Pull Request:** Fill out the PR template checklist confirming zero media and zero live database dumps are included.
4. **Code Review:** Requires at least one approving review before merging into `main` or `develop`.

---

## 2. Strict Data Hygiene Policy

Under no circumstances should forensic media, live database credentials, or investigative spreadsheets be committed to this repository.

* **Media Storage:** All media assets must reside exclusively in external/local storage mounts (`future-lan-storage/` or custom LAN paths).
* **Reference Intelligence Data:** Use automated ingestion scripts (`scripts/data-ingestion/`) with mock/anonymized fixtures.
* **Database Configuration:** Copy `database/db_config.example.json` to `database/db_config.json` locally. Do not track `db_config.json`.

---

## 3. Local Development Setup

### Prerequisites
* Python 3.11+
* PostgreSQL 16+ with `pgvector` extension
* `libraw-dev`, `libmagic-dev`, `libheif-dev`

### Environment Bootstrap
```bash
# 1. Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 2. Install dependencies in editable mode with development tools
pip install -e ".[dev]"

# 3. Setup pre-commit hooks
pre-commit install

# 4. Configure local database credentials
cp database/db_config.example.json database/db_config.json
# Edit database/db_config.json with your local PostgreSQL credentials

# 5. Initialize Database Schemas
python3 database/init_database.py

# 6. Run Test Suite
pytest -v tests/
```

---

## 4. Code Standards & Linting

* **Formatting:** Black compatible (line length 100).
* **Linter:** Ruff (`ruff check .` and `ruff format .`).
* **Type Hints:** Standard Python type annotations wherever feasible.
