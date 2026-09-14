-- Copyright 2026 Google LLC
--
-- Licensed under the Apache License, Version 2.0 (the "License");
-- you may not use this file except in compliance with the License.
-- You may obtain a copy of the License at
--
--     https://www.apache.org/licenses/LICENSE-2.0
--
-- Unless required by applicable law or agreed to in writing, software
-- distributed under the License is distributed on an "AS IS" BASIS,
-- WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
-- See the License for the specific language governing permissions and
-- limitations under the License.

-- ============================================================================
-- SYMPICS ENTERPRISE POSTGRESQL SCHEMA — MODULE 3: REFERENCE INTELLIGENCE CATALOG
-- ============================================================================
-- Purpose:
-- Stores standardized reference intelligence hash exports, known series lists,
-- priority indicators, and media classification metadata.
-- ============================================================================

CREATE TABLE IF NOT EXISTS reference_catalog_records (
    record_id BIGSERIAL PRIMARY KEY,
    
    -- Cryptographic Fingerprints & Perceptual Hashes
    md5 CHAR(32) NOT NULL,
    sha1 CHAR(40) NOT NULL,
    zz40 VARCHAR(64),
    photodna TEXT,
    lace TEXT,
    
    -- Reference Identifiers & Status Flags
    identifier VARCHAR(128) NOT NULL,                 -- e.g. "REF-90000001/V1"
    is_distributed BOOLEAN NOT NULL DEFAULT FALSE,   -- Y/N -> TRUE/FALSE
    flag_identified BOOLEAN NOT NULL DEFAULT FALSE,  -- Y/N -> TRUE/FALSE
    flag_actionable BOOLEAN NOT NULL DEFAULT FALSE,  -- Y/N -> TRUE/FALSE
    
    -- Case & Intelligence Series Context
    series_name VARCHAR(512),                       -- e.g. "SERIES-ALPHA/TARGET 1"
    investigation_name VARCHAR(512),                -- e.g. "ALPHA-INV"
    contributing_agency VARCHAR(512),               -- e.g. "Agency A, Agency B"
    number_of_submissions INTEGER DEFAULT 1,
    file_available BOOLEAN NOT NULL DEFAULT FALSE,  -- True/False
    media_type VARCHAR(32) DEFAULT 'Image',         -- Image / Video
    is_baseline BOOLEAN NOT NULL DEFAULT FALSE,     -- Yes/No -> TRUE/FALSE
    
    -- Ingestion Metadata
    imported_batch_id UUID,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    
    -- Constraint: Uniqueness on primary hashes / identifier
    CONSTRAINT uq_reference_image_md5 UNIQUE (md5, identifier)
);

-- ============================================================================
-- HIGH PERFORMANCE FAST-COLLISION INDEXES
-- ============================================================================
CREATE INDEX IF NOT EXISTS idx_reference_md5 ON reference_catalog_records(md5);
CREATE INDEX IF NOT EXISTS idx_reference_sha1 ON reference_catalog_records(sha1);
CREATE INDEX IF NOT EXISTS idx_reference_identifier ON reference_catalog_records(identifier);
CREATE INDEX IF NOT EXISTS idx_reference_series_name ON reference_catalog_records(series_name);
CREATE INDEX IF NOT EXISTS idx_reference_flag_id ON reference_catalog_records(flag_identified);
CREATE INDEX IF NOT EXISTS idx_reference_flag_act ON reference_catalog_records(flag_actionable);

-- ============================================================================
-- REFERENCE INTELLIGENCE COLLISION VIEW
-- Instantly cross-references media_assets in the vault against the reference catalog
-- ============================================================================
CREATE OR REPLACE VIEW v_reference_known_collisions AS
SELECT
    ma.asset_id,
    ma.sha256 AS vault_sha256,
    ma.md5 AS vault_md5,
    ma.storage_rel_path,
    ma.thumb_rel_path,
    cei.original_filename,
    cei.source_parent_dir,
    ref.identifier AS reference_id,
    ref.series_name AS reference_series,
    ref.flag_identified,
    ref.flag_actionable,
    ref.is_distributed,
    ref.contributing_agency,
    ref.created_at AS reference_import_date
FROM media_assets ma
JOIN case_evidence_items cei ON ma.asset_id = cei.asset_id
JOIN reference_catalog_records ref ON ma.md5 = ref.md5 OR ma.sha1 = ref.sha1;
