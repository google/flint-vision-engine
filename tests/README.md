# SYMPICS Automated Test Suite

Comprehensive unit and integration test suite using `pytest`.

## Running Tests
```bash
# Run all tests
pytest -v

# Run unit tests only
pytest tests/unit/ -v

# Run integration tests only
pytest tests/integration/ -v
```

## Coverage
* **Unit Tests (`tests/unit/`):** Cryptographic hashing, CAS path formatting, Camera RAW preview extraction, EXIF/GPS coordinate parsing, Zip Slip path traversal defenses, hardware auto-discovery.
* **Integration Tests (`tests/integration/`):** PostgreSQL `SKIP LOCKED` batch concurrency, Web REST APIs, `/healthz`/`/readyz` probes, and SQL Explorer security sandboxing.
