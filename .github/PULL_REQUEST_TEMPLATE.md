## Pull Request Summary

### Description of Changes
<!-- Provide a clear, concise summary of the changes made and the problem being solved. -->

---

### Type of Change
- [ ] New feature (non-breaking change adding functionality)
- [ ] Bug fix (non-breaking change fixing an issue)
- [ ] Performance optimization / indexing enhancement
- [ ] Documentation update
- [ ] CI/CD / Build configuration

---

### Security & Data Hygiene Verification Checklist
- [ ] **ZERO Media:** Verified no raw images (`*.jpg`, `*.cr3`, `*.tif`, etc.) or videos (`*.mp4`, `*.mov`) are committed.
- [ ] **ZERO Spreadsheets / Reference Watchlist Data:** Verified no `.csv`, `.tsv`, `.xlsx`, or tabular case data is committed.
- [ ] **ZERO Secrets / Credentials:** Verified no `.env` files or production database passwords in `db_config.json` are committed.
- [ ] **Database & Migrations:** Verified schema scripts in `database/` are idempotent and tested.
- [ ] **Automated Tests:** All unit and integration tests pass via `pytest tests/`.
- [ ] **Linting & Formatting:** Code adheres to Ruff and Black standards.
