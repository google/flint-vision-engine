# `sympics` Core Python Package

The `sympics` package provides the core domain logic, AI vision models, database access, and background workers for the SYMPICS Forensic Platform.

## Package Layout
* **`sympics.core.hashing`**: Multi-stream 64KB chunked SHA-256, MD5, and SHA-1 hashing.
* **`sympics.core.cas_vault`**: 2-layer hex path resolution (`01_Media_Vault/images/ab/cd/<sha256>.ext`).
* **`sympics.core.raw_extractor`**: Pure-Python embedded JPEG preview extraction from Canon `.CR3`/`.CR2`, Nikon `.NEF`, Sony `.ARW`, Adobe `.DNG`, and Fuji `.RAF`.
* **`sympics.core.exif_parser`**: EXIF metadata extraction, DMS-to-decimal GPS coordinate conversion, and PostgreSQL JSON null-byte scrubbing.
* **`sympics.core.archive`**: Safe ZIP and TAR archive extraction with Zip Slip path traversal defense.
* **`sympics.hardware`**: Hardware auto-discovery probing CUDA VRAM, CPU cores, and system memory to auto-tune worker pools.
* **`sympics.config`**: Centralized configuration management supporting environment variables and JSON overrides.
* **`sympics.ai.embedder`**: Multi-model vision embedder for CLIP, SigLIP Base, and SigLIP-2 NaFlex.
* **`sympics.ai.thumbnailer`**: High-speed 256px WebP thumbnail generator with LANCZOS downsampling.
* **`sympics.database.connection`**: Threaded connection pool manager for PostgreSQL.
* **`sympics.database.repositories`**: Domain repository classes (`asset_repo`, `case_repo`, `manifest_repo`, `vector_repo`).
* **`sympics.web.controllers`**: Specialized web controllers (`sql_sandbox_controller`, `telemetry_controller`).
