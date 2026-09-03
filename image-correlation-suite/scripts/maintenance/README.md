# SYMPICS Maintenance & Integrity Tools

Maintenance utilities for long-term vault preservation, model provisioning, offline documentation generation, and database vector indexing.

## Tools

* **`scrub_vault_integrity.py`**:
  * Periodically scans physical files in `01_Media_Vault/` and recalculates cryptographic SHA-256 checksums.
  * Validates hashes against the `media_assets` database ledger to detect bit rot, silent disk corruption, or unauthorized tampering.
  * Supports full vault scrubs or random sampling (`--sample 100`).

* **`backfill_embeddings.py`**:
  * Scans `media_assets` for any images or keyframes that lack complete multi-model vector embeddings.
  * Automatically invokes `sympics.ai.ensemble` across SigLIP-2, CLIP, and DINOv3 to generate and commit missing embeddings into `media_embeddings`.

* **`download_offline_models.py`**:
  * Air-gap provisioning utility for sealed forensic laboratories.
  * Downloads model checkpoints (SigLIP-2 NaFlex, SigLIP Base, CLIP ViT-B/32, DINOv3) on an internet-connected workstation and packages them into an air-gapped tarball (`--create-tar sympics-models-airgap.tar.gz`).

* **`generate_html_docs.py`**:
  * Offline documentation compiler.
  * Parses all Markdown documentation in `docs/` and `README.md` and compiles them into a standalone, air-gapped HTML portal (`docs/html/`) with responsive navigation.

* **`migrate_to_halfvec.sql`**:
  * PostgreSQL performance migration script.
  * Converts 32-bit `vector(768)` columns to 16-bit `halfvec(768)` with HNSW cosine indexing, cutting vector RAM requirements in half with zero loss in search accuracy.
