# SYMPICS Filesystem Migration & Ingestion Suite

A high-performance 4-phase migration architecture designed to catalog, fingerprint, ingest, and verify multi-terabyte legacy evidence stores.

## Tools

* **`build_hex_vault_structure.py`**:
  * Pre-allocates the two-layer hexadecimal directory hierarchy (`00/00/` through `ff/ff/`, totaling 65,536 buckets) for images, videos, and WebP keyframes.
  * Ensures the target storage drive never suffers directory tree latency or OS filesystem degradation.

* **`scan_legacy_manifest.py`**:
  * **Phase 1 (Discovery & Fingerprinting):** Performs 100% read-only discovery of legacy evidence directories.
  * Calculates cryptographic SHA-256 hashes and populates the `migration_manifest` ledger without moving, modifying, or renaming a single file.

* **`migrate_vault_worker.py`**:
  * **Phase 2 (Supervised Parallel Ingestion):** Consumes `PENDING` records using PostgreSQL `SKIP LOCKED` concurrency.
  * Extracts camera RAW embedded JPEGs in ~150ms, computes AI vector embeddings (SigLIP-2, CLIP, DINOv3), generates 256px WebP thumbnails, copies master files to the CAS vault, and executes destination readback hash verification before committing.

* **`verify_vault_integrity.py`**:
  * **Phase 3 (Forensic Audit):** Performs post-migration byte verification, checking that all records in `migration_manifest` marked `VERIFIED_COPIED` exist on disk with matching SHA-256 checksums.
