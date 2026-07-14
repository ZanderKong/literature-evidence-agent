-- Migration 004: Review batches, run metadata, and task lifecycle
-- Adds review_batches, review_batch_rows, warning_json, and batch tracking.

PRAGMA foreign_keys = ON;

-- Review batches (tracks packet exports)
CREATE TABLE IF NOT EXISTS review_batches (
    review_batch_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    source_id TEXT NOT NULL,
    packet_sha256 TEXT NOT NULL,
    status TEXT NOT NULL CHECK (
        status IN (
            'exported',
            'partially_applied',
            'applied',
            'invalid'
        )
    ),
    exported_at TEXT NOT NULL,
    completed_at TEXT,
    FOREIGN KEY (run_id)
        REFERENCES processing_runs(run_id) ON DELETE CASCADE,
    FOREIGN KEY (source_id)
        REFERENCES sources(source_id) ON DELETE CASCADE,
    UNIQUE (run_id, packet_sha256)
);

-- Review batch rows (individual claims in a batch)
CREATE TABLE IF NOT EXISTS review_batch_rows (
    review_row_id TEXT PRIMARY KEY,
    review_batch_id TEXT NOT NULL,
    claim_id TEXT NOT NULL,
    row_sequence INTEGER NOT NULL,
    row_input_sha256 TEXT NOT NULL,
    applied_at TEXT,
    FOREIGN KEY (review_batch_id)
        REFERENCES review_batches(review_batch_id) ON DELETE CASCADE,
    FOREIGN KEY (claim_id)
        REFERENCES source_claims(claim_id) ON DELETE CASCADE,
    UNIQUE (review_batch_id, claim_id),
    UNIQUE (review_batch_id, row_sequence)
);

-- Add warning_json to processing_runs (may already exist from prior run)
ALTER TABLE processing_runs ADD COLUMN warning_json TEXT;

-- Add review_batch_id and review_row_id to review_decisions
ALTER TABLE review_decisions ADD COLUMN review_batch_id TEXT;
ALTER TABLE review_decisions ADD COLUMN review_row_id TEXT;

-- Add artifact_schema_version to processing_runs
ALTER TABLE processing_runs ADD COLUMN artifact_schema_version TEXT;

-- Add created_by_run_id FK constraint (best-effort, SQLite needs FK enabled)
-- Already enforced at application level
