-- Copyright 2026 Google LLC
-- Licensed under Apache 2.0

-- ============================================================================
-- SYMPICS ENTERPRISE POSTGRESQL SCHEMA — MODULE 2: CORE PRODUCTION TABLES
-- ============================================================================
-- Purpose:
-- Permanent, deduplicated media repository, pgvector AI embeddings, and
-- multi-modal dataset and case linkage tables.
-- ============================================================================

-- Enable required core extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "vector"; -- pgvector extension

-- ============================================================================
-- 1. CASES / WORKSPACES TABLE
-- ============================================================================
CREATE TABLE IF NOT EXISTS cases (
    case_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    case_number VARCHAR(128) NOT NULL UNIQUE,       -- e.g. 'CASE-2026-001'
    case_name VARCHAR(255) NOT NULL,
    classification_type VARCHAR(64) NOT NULL DEFAULT 'MEDIA_ARCHIVE' 
        CHECK (classification_type IN ('MEDIA_ARCHIVE', 'SERIES_MATCH', 'RESEARCH_DATASET', 'CURATED_COLLECTION', 'GENERAL_MEDIA', 'UNCLASSIFIED', 'MEDIA_EVIDENCE', 'TERRORISM', 'NARCOTICS', 'GENERAL_CRIMINAL', 'EVIDENCE_INTAKE')),
    priority_level VARCHAR(32) NOT NULL DEFAULT 'NORMAL' 
        CHECK (priority_level IN ('LOW', 'NORMAL', 'HIGH', 'CRITICAL', 'CRITICAL_IMMINENT_HARM')),
    status VARCHAR(32) NOT NULL DEFAULT 'ACTIVE' 
        CHECK (status IN ('ACTIVE', 'INACTIVE', 'PENDING_REVIEW', 'ARCHIVED', 'CLOSED', 'CLOSED_COURT')),
    contributing_agency VARCHAR(255) DEFAULT 'Primary Repository',
    case_notes TEXT,
    deleted_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_cases_case_number ON cases(case_number);
CREATE INDEX IF NOT EXISTS idx_cases_status ON cases(status);

-- ============================================================================
-- 2. CANONICAL PHYSICAL MEDIA ASSETS (DEDUPLICATED BY SHA-256)
-- ============================================================================
CREATE TABLE IF NOT EXISTS media_assets (
    asset_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    sha256 CHAR(64) NOT NULL UNIQUE,                -- Canonical immutable primary hash
    md5 CHAR(32) NOT NULL,                           -- Legacy fast-lookup hash
    sha1 CHAR(40),                                   -- Legacy SHA-1 hash
    file_size_bytes BIGINT NOT NULL,
    media_type VARCHAR(32) NOT NULL DEFAULT 'IMAGE' 
        CHECK (media_type IN ('IMAGE', 'VIDEO', 'AUDIO')),
    mime_type VARCHAR(128) NOT NULL,
    width_pixels INTEGER,
    height_pixels INTEGER,
    duration_seconds REAL DEFAULT 0.0,
    frame_rate REAL DEFAULT 0.0,
    storage_rel_path VARCHAR(512) NOT NULL,          -- e.g. "01_Media_Vault/images/3a/7f/3a7f...jpg"
    storage_abs_path TEXT NOT NULL,                  -- Full filesystem path on Storage LAN
    thumb_rel_path VARCHAR(512),                     -- e.g. "02_Keyframe_Vault/thumbs_256px/3a/7f/3a7f..._thumb.webp"
    source_folder VARCHAR(255),                      -- Immediate parent collection / folder name (e.g. "batchA")
    source_rel_path TEXT,                            -- Full origin relative path (e.g. "evidence/20260818/batchA/photo.jpg")
    gps_latitude DOUBLE PRECISION,                   -- EXIF GPS Latitude
    gps_longitude DOUBLE PRECISION,                  -- EXIF GPS Longitude
    gps_altitude DOUBLE PRECISION,                   -- EXIF GPS Altitude (meters)
    is_corrupt BOOLEAN NOT NULL DEFAULT FALSE,
    exif_data JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_media_assets_sha256 ON media_assets(sha256);
CREATE INDEX IF NOT EXISTS idx_media_assets_md5 ON media_assets(md5);
CREATE INDEX IF NOT EXISTS idx_media_assets_sha1 ON media_assets(sha1);
CREATE INDEX IF NOT EXISTS idx_media_assets_source_folder ON media_assets(source_folder);
CREATE INDEX IF NOT EXISTS idx_media_assets_gps ON media_assets(gps_latitude, gps_longitude) WHERE gps_latitude IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_media_assets_exif ON media_assets USING gin(exif_data);

-- ============================================================================
-- 3. AI VECTOR EMBEDDINGS TABLE (PGVECTOR HNSW INDEXED)
-- ============================================================================
CREATE TABLE IF NOT EXISTS media_embeddings (
    embedding_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    asset_id UUID NOT NULL REFERENCES media_assets(asset_id) ON DELETE CASCADE,
    model_name VARCHAR(64) NOT NULL DEFAULT 'siglip',
    model_version VARCHAR(32) NOT NULL DEFAULT 'base-patch16-224',
    dimension_size INTEGER NOT NULL DEFAULT 768,
    embedding_l2 vector NOT NULL,                     -- L2 normalized dense vector
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(asset_id, model_name)
);

CREATE INDEX IF NOT EXISTS idx_media_embeddings_asset ON media_embeddings(asset_id);
CREATE INDEX IF NOT EXISTS idx_media_embeddings_512_hnsw 
    ON media_embeddings USING hnsw ((embedding_l2::vector(512)) vector_cosine_ops) 
    WHERE dimension_size = 512;
CREATE INDEX IF NOT EXISTS idx_media_embeddings_768_hnsw 
    ON media_embeddings USING hnsw ((embedding_l2::vector(768)) vector_cosine_ops) 
    WHERE dimension_size = 768;

-- ============================================================================
-- 4. CASE-SPECIFIC EVIDENCE LINKAGE & PROVENANCE
-- ============================================================================
CREATE TABLE IF NOT EXISTS case_evidence_items (
    evidence_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    case_id UUID NOT NULL REFERENCES cases(case_id) ON DELETE CASCADE,
    asset_id UUID NOT NULL REFERENCES media_assets(asset_id) ON DELETE RESTRICT,
    original_filepath TEXT NOT NULL,                 -- Original file path on seized/legacy drive
    original_filename VARCHAR(512) NOT NULL,        -- Original filename on seized/legacy drive
    source_parent_dir VARCHAR(512),                  -- Original folder name (e.g. "known-files")
    series_tag VARCHAR(255),                         -- Case folder / series tag
    analyst_notes TEXT,
    tags TEXT[],
    custody_status VARCHAR(64) NOT NULL DEFAULT 'INGESTED' 
        CHECK (custody_status IN ('INGESTED', 'TRIAGED', 'CONFIRMED_MATCH', 'CONFIRMED_ACTIONABLE', 'FLAGGED_EXCULPATORY', 'EXCLUDED')),
    ai_suggested_series VARCHAR(255),
    ai_suggested_tags TEXT[],
    ai_match_score FLOAT,
    ai_match_evidence_id UUID REFERENCES case_evidence_items(evidence_id) ON DELETE SET NULL,
    ai_review_status VARCHAR(64) NOT NULL DEFAULT 'NONE'
        CHECK (ai_review_status IN ('NONE', 'PENDING_REVIEW', 'CONFIRMED', 'REJECTED')),
    last_action VARCHAR(64) NOT NULL DEFAULT 'ingested',
    last_action_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    action_history JSONB DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(case_id, original_filepath)
);

CREATE INDEX IF NOT EXISTS idx_case_evidence_case ON case_evidence_items(case_id);
CREATE INDEX IF NOT EXISTS idx_case_evidence_asset ON case_evidence_items(asset_id);
CREATE INDEX IF NOT EXISTS idx_case_evidence_series ON case_evidence_items(series_tag);
CREATE INDEX IF NOT EXISTS idx_case_evidence_tags ON case_evidence_items USING gin(tags);
CREATE INDEX IF NOT EXISTS idx_case_evidence_ai_review ON case_evidence_items(ai_review_status);
CREATE INDEX IF NOT EXISTS idx_case_evidence_action ON case_evidence_items(last_action);
CREATE INDEX IF NOT EXISTS idx_case_evidence_action_time ON case_evidence_items(last_action_at);

-- ============================================================================
-- 5. FORENSIC EVIDENCE ACTION AUDIT TRAIL
-- ============================================================================
CREATE TABLE IF NOT EXISTS case_evidence_actions (
    action_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    evidence_id UUID REFERENCES case_evidence_items(evidence_id) ON DELETE CASCADE,
    asset_id UUID REFERENCES media_assets(asset_id) ON DELETE CASCADE,
    action_type VARCHAR(64) NOT NULL 
        CHECK (action_type IN ('ingested', 'tag-only', 'create-reference-series', 'tag-add', 'tag-delete', 'series-add', 'series-delete', 'notes-add', 'notes-update', 'notes-delete', 'status-change', 'ai-auto-tagged', 'ai-tag-confirmed', 'ai-tag-rejected')),
    original_filename VARCHAR(512),
    sha1 CHAR(40),
    sha256 CHAR(64),
    md5 CHAR(32),
    previous_value TEXT,
    new_value TEXT,
    performed_by VARCHAR(128) DEFAULT 'analyst',
    performed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    details JSONB DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_case_evidence_actions_evidence ON case_evidence_actions(evidence_id);
CREATE INDEX IF NOT EXISTS idx_case_evidence_actions_type ON case_evidence_actions(action_type);
CREATE INDEX IF NOT EXISTS idx_case_evidence_actions_sha256 ON case_evidence_actions(sha256);
CREATE INDEX IF NOT EXISTS idx_case_evidence_actions_sha1 ON case_evidence_actions(sha1);
CREATE INDEX IF NOT EXISTS idx_case_evidence_actions_time ON case_evidence_actions(performed_at);

-- ============================================================================
-- 6. VIDEO KEYFRAMES & TEMPORAL SAMPLES
-- ============================================================================
CREATE TABLE IF NOT EXISTS video_keyframes (
    keyframe_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    asset_id UUID NOT NULL REFERENCES media_assets(asset_id) ON DELETE CASCADE,
    frame_index INTEGER NOT NULL,
    timestamp_seconds REAL NOT NULL,
    storage_rel_path VARCHAR(512) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(asset_id, frame_index)
);
CREATE INDEX IF NOT EXISTS idx_video_keyframes_asset ON video_keyframes(asset_id);

-- ============================================================================
-- 7. KNOWN HASH SETS (REFERENCE CATALOGS, WATCHLISTS, CUSTOM)
-- ============================================================================
CREATE TABLE IF NOT EXISTS known_hash_sets (
    hash_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    hash_value VARCHAR(64) NOT NULL,
    hash_type VARCHAR(16) NOT NULL CHECK (hash_type IN ('MD5', 'SHA1', 'SHA256')),
    series_name VARCHAR(255),
    source_file VARCHAR(255),
    category VARCHAR(64) DEFAULT 'KNOWN_MATCH',
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(hash_value, hash_type)
);
CREATE INDEX IF NOT EXISTS idx_known_hashes_val ON known_hash_sets(hash_value);

