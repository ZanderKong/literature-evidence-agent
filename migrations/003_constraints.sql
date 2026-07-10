-- Migration 003: Indexes and constraints
-- Creates performance indexes for common query patterns.

-- Source indexes
CREATE INDEX IF NOT EXISTS idx_sources_doi ON sources(doi);
CREATE INDEX IF NOT EXISTS idx_sources_created_at ON sources(created_at);

-- Section indexes
CREATE INDEX IF NOT EXISTS idx_sections_source_sequence
    ON source_sections(source_id, sequence_number);

-- Claim indexes
CREATE INDEX IF NOT EXISTS idx_claims_source ON source_claims(source_id);
CREATE INDEX IF NOT EXISTS idx_claims_task ON source_claims(task_id);
CREATE INDEX IF NOT EXISTS idx_claims_review_status
    ON source_claims(record_review_status);
CREATE INDEX IF NOT EXISTS idx_claims_type ON source_claims(claim_type);

-- Run indexes
CREATE INDEX IF NOT EXISTS idx_runs_source ON processing_runs(source_id);

-- Review indexes
CREATE INDEX IF NOT EXISTS idx_reviews_object
    ON review_decisions(object_type, object_id);
