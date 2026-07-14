-- Migration 005: Review integrity indexes and constraints
-- Adds indexes for review batch lookups and decision uniqueness.

PRAGMA foreign_keys = ON;

-- Index for batch decisions (unique per batch+row)
CREATE UNIQUE INDEX IF NOT EXISTS idx_review_decisions_batch_row
ON review_decisions(review_batch_id, review_row_id)
WHERE review_batch_id IS NOT NULL
AND review_row_id IS NOT NULL;

-- Index for lookup by claim in batch rows
CREATE INDEX IF NOT EXISTS idx_review_batch_rows_claim
ON review_batch_rows(claim_id);

-- Index for filtering batches by run and status
CREATE INDEX IF NOT EXISTS idx_review_batches_run_status
ON review_batches(run_id, status);
