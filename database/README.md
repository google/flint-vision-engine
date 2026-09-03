# Database Schema & Data Access Layer

This directory contains the PostgreSQL DDL schemas, `pgvector` index definitions, connection management, and hardware acceleration utilities for `sympics_db`.

## Core Schemas
* **`schema_core_tables.sql`**: Defines `cases`, `media_assets`, `media_embeddings` (with 512d & 768d vector columns and HNSW cosine indexes), and `case_evidence_items`.
* **`schema_migration_manifest.sql`**: Defines `migration_manifest` for Phase 1 read-only cataloging and dynamic multi-worker batch distribution (`FOR UPDATE SKIP LOCKED`).
* **`schema_reference_catalog.sql`**: Known Series and reference intelligence hash collision tables.
* **`schema_verification_audit.sql`**: Forensic audit log and evidence tracking.

## Utilities & Configuration
* **`init_database.py`**: Automated database bootstrapper; creates `sympics_db`, enables `vector` extension, and applies all SQL schemas in order.
* **`db.py`**: PostgreSQL connection pooling, schema initialization, and transactional batch checkout.
* **`hardware_acceleration.py`**: Hardware probe and worker auto-tuning engine.
* **`embedder_service.py`**: Model weight loader and batch inference engine.
* **`dashboard.py`**: Terminal-based live migration progress monitor.
* **`forensic_identity.py`**: Digital fingerprint and session provenance generator.
* **`postgresql_tuning_128gb.conf`**: Optimized configuration template for 128 GB RAM + NVMe + Multi-Core workstations.

