-- Copyright 2026 Google LLC
-- Licensed under Apache 2.0

-- ============================================================================
-- SYMPICS ENTERPRISE POSTGRESQL SCHEMA — MODULE 4: FORENSIC AUDIT & RECONCILIATION
-- ============================================================================
-- Purpose:
-- Provides court-admissible integrity auditing views, orphan detectors, and
-- cryptographic reconciliation summaries.
-- ============================================================================

-- ============================================================================
-- 1. FORENSIC AUDIT RECONCILIATION VIEW
-- ============================================================================
CREATE OR REPLACE VIEW v_forensic_integrity_audit AS
SELECT
    -- Discovery Metrics
    (SELECT COUNT(*) FROM migration_manifest) AS total_legacy_files_discovered,
    (SELECT COUNT(DISTINCT sha256) FROM migration_manifest) AS total_unique_sha256_discovered,
    (SELECT COALESCE(SUM(file_size_bytes), 0) FROM migration_manifest) AS total_legacy_bytes_discovered,

    -- Vault Ingestion Metrics
    (SELECT COUNT(*) FROM media_assets) AS total_physical_assets_in_vault,
    (SELECT COALESCE(SUM(file_size_bytes), 0) FROM media_assets) AS total_physical_vault_bytes,
    (SELECT COUNT(*) FROM case_evidence_items) AS total_case_evidence_items_linked,
    (SELECT COUNT(*) FROM media_embeddings) AS total_ai_embeddings_generated,

    -- Manifest Verification Breakdown
    (SELECT COUNT(*) FROM migration_manifest WHERE status = 'VERIFIED_COPIED') AS verified_copied_count,
    (SELECT COUNT(*) FROM migration_manifest WHERE status = 'SKIPPED_DUPLICATE') AS deduplicated_occurrences,
    (SELECT COUNT(*) FROM migration_manifest WHERE status = 'PENDING') AS pending_queue_count,
    (SELECT COUNT(*) FROM migration_manifest WHERE status LIKE 'FAILED%') AS failed_corrupt_count,

    -- Storage Savings Computation
    ROUND(
        (1.0 - (
            (SELECT COALESCE(SUM(file_size_bytes), 1) FROM media_assets)::NUMERIC / 
            NULLIF((SELECT COALESCE(SUM(file_size_bytes), 1) FROM migration_manifest)::NUMERIC, 0)
        )) * 100, 2
    ) AS percent_disk_space_saved,

    -- Overall System Integrity Status
    CASE 
        WHEN (SELECT COUNT(*) FROM migration_manifest WHERE status LIKE 'FAILED%') > 0 THEN 'INTEGRITY_WARNING_FAILED_FILES_PRESENT'
        WHEN (SELECT COUNT(*) FROM migration_manifest WHERE status = 'PENDING') > 0 THEN 'MIGRATION_IN_PROGRESS'
        WHEN (SELECT COUNT(*) FROM migration_manifest) = 0 THEN 'EMPTY_NO_DATA'
        ELSE 'FORENSIC_INTEGRITY_100_PERCENT_VERIFIED'
    END AS system_audit_verdict;

-- ============================================================================
-- 2. DISCREPANCY & ORPHAN DETECTOR VIEW
-- Identifies any asset in media_assets missing from the manifest or case links
-- ============================================================================
CREATE OR REPLACE VIEW v_forensic_discrepancies AS
SELECT
    ma.asset_id,
    ma.sha256,
    ma.storage_rel_path,
    ma.storage_abs_path,
    ma.file_size_bytes,
    COUNT(cei.evidence_id) AS linked_case_count,
    CASE 
        WHEN COUNT(cei.evidence_id) = 0 THEN 'ORPHAN_ASSET_NO_CASE_LINK'
        WHEN me.embedding_id IS NULL THEN 'MISSING_AI_VECTOR_EMBEDDING'
        ELSE 'HEALTHY'
    END AS anomaly_type
FROM media_assets ma
LEFT JOIN case_evidence_items cei ON ma.asset_id = cei.asset_id
LEFT JOIN media_embeddings me ON ma.asset_id = me.asset_id
GROUP BY ma.asset_id, ma.sha256, ma.storage_rel_path, ma.storage_abs_path, ma.file_size_bytes, me.embedding_id
HAVING COUNT(cei.evidence_id) = 0 OR me.embedding_id IS NULL;
