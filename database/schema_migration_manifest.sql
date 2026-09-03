-- Copyright 2026 Google LLC
-- Licensed under Apache 2.0

-- ============================================================================
-- SYMPICS ENTERPRISE POSTGRESQL SCHEMA — MODULE 1: MIGRATION MANIFEST
-- ============================================================================
-- Purpose:
-- Forensically sound, byte-for-byte tracking ledger used to discover, hash,
-- process, copy, and verify legacy evidence files into the new 2-layer hex vault.
--
-- Guarantees:
-- 1. Zero data loss during transition from legacy dumping grounds.
-- 2. Complete cryptographic provenance (SHA-256, MD5, SHA-1).
-- 3. Readback hash verification on destination storage before marking complete.
-- ============================================================================

-- Enable required core extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ============================================================================
-- 1. MIGRATION MANIFEST TABLE
-- ============================================================================
CREATE TABLE IF NOT EXISTS migration_manifest (
    manifest_id BIGSERIAL PRIMARY KEY,

    -- Source Legacy File Provenance
    source_filepath TEXT NOT NULL UNIQUE,          -- Exact absolute path on legacy storage
    source_filename VARCHAR(512) NOT NULL,         -- Base filename (e.g. "PHOTO-2024-04-18.jpg")
    source_parent_dir VARCHAR(512),                -- Immediate folder name (e.g. "Case_102")
    file_size_bytes BIGINT NOT NULL,               -- Exact byte count on source disk
    file_extension VARCHAR(32) NOT NULL,           -- Normalized lowercase extension (e.g. ".jpg")
    source_created_at TIMESTAMPTZ,                 -- Source filesystem creation timestamp
    source_modified_at TIMESTAMPTZ,                -- Source filesystem last modified timestamp

    -- Cryptographic Fingerprints
    sha256 CHAR(64) NOT NULL,                      -- Canonical immutable 256-bit hash (lowercase)
    md5 CHAR(32) NOT NULL,                         -- Legacy MD5 hash for backward lookup
    sha1 CHAR(40),                                 -- Legacy SHA-1 hash

    -- Migration & Forensic Verification Status
    status VARCHAR(32) NOT NULL DEFAULT 'PENDING' 
        CHECK (status IN (
            'PENDING',              -- Discovered, waiting to be processed
            'SCANNING',             -- Currently hashing / reading
            'EMBEDDING',            -- Generating PyTorch AI vector
            'COPIED',               -- Copied to destination, awaiting readback verification
            'VERIFIED_COPIED',      -- Cryptographically verified on destination disk (100% Match)
            'SKIPPED_DUPLICATE',    -- Physical file already exists in vault, provenance linked
            'FAILED_CORRUPT',       -- Source file is truncated or unreadable
            'FAILED_ERROR'          -- Encountered I/O or unexpected error
        )),

    -- Destination Vault Storage Resolution
    destination_rel_path VARCHAR(512),             -- Relative path: e.g. "01_Media_Vault/images/3a/7f/3a7f9c...jpg"
    destination_abs_path TEXT,                     -- Full path on new Storage LAN
    destination_size_bytes BIGINT,                 -- Readback byte size from destination disk
    destination_sha256 CHAR(64),                   -- Readback SHA-256 computed from destination disk

    -- AI Embedding & Video Processing State
    is_video BOOLEAN NOT NULL DEFAULT FALSE,
    keyframes_extracted_count INTEGER DEFAULT 0,
    embedding_status VARCHAR(32) NOT NULL DEFAULT 'PENDING' 
        CHECK (embedding_status IN ('PENDING', 'EMBEDDED', 'SKIPPED', 'FAILED')),

    -- Worker Traceability & Performance Metrics
    worker_id VARCHAR(128),                        -- Machine hostname / worker process ID
    processing_time_ms INTEGER,                    -- Total milliseconds to hash, embed, and copy
    retry_count INTEGER NOT NULL DEFAULT 0,
    error_message TEXT,                            -- Detailed error message or traceback if failed

    -- Audit Timestamps
    scanned_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    migrated_at TIMESTAMPTZ,
    verified_at TIMESTAMPTZ
);

-- ============================================================================
-- 2. HIGH-PERFORMANCE INDEXES
-- ============================================================================
-- Fast lookup by cryptographic hash (for instant deduplication checks)
CREATE INDEX IF NOT EXISTS idx_manifest_sha256 ON migration_manifest(sha256);
CREATE INDEX IF NOT EXISTS idx_manifest_md5 ON migration_manifest(md5);

-- Fast queue filtering for migration workers
CREATE INDEX IF NOT EXISTS idx_manifest_status ON migration_manifest(status);
CREATE INDEX IF NOT EXISTS idx_manifest_embedding_status ON migration_manifest(embedding_status);
CREATE INDEX IF NOT EXISTS idx_manifest_scanned_at ON migration_manifest(scanned_at DESC);

-- Fast lookup by parent directory (for case / folder grouping)
CREATE INDEX IF NOT EXISTS idx_manifest_parent_dir ON migration_manifest(source_parent_dir);

-- ============================================================================
-- 3. MIGRATION RECONCILIATION SUMMARY VIEW
-- ============================================================================
-- Provides a real-time progress and verification summary
CREATE OR REPLACE VIEW v_migration_summary AS
SELECT
    COUNT(*) AS total_files_discovered,
    COUNT(DISTINCT sha256) AS total_unique_assets,
    COUNT(CASE WHEN status = 'VERIFIED_COPIED' THEN 1 END) AS verified_copied,
    COUNT(CASE WHEN status = 'SKIPPED_DUPLICATE' THEN 1 END) AS skipped_duplicates,
    COUNT(CASE WHEN status = 'PENDING' THEN 1 END) AS pending,
    COUNT(CASE WHEN status IN ('FAILED_CORRUPT', 'FAILED_ERROR') THEN 1 END) AS failed,
    COALESCE(SUM(file_size_bytes), 0) AS total_source_bytes,
    COALESCE(SUM(CASE WHEN status = 'VERIFIED_COPIED' THEN file_size_bytes ELSE 0 END), 0) AS verified_bytes_migrated,
    ROUND(
        (COUNT(CASE WHEN status IN ('VERIFIED_COPIED', 'SKIPPED_DUPLICATE') THEN 1 END)::NUMERIC / 
        NULLIF(COUNT(*), 0)::NUMERIC) * 100, 2
    ) AS percent_complete
FROM migration_manifest;
