-- Migration 002: Full-text search (FTS5)
-- Creates virtual tables for full-text search on source content and claims.

-- Source FTS
CREATE VIRTUAL TABLE IF NOT EXISTS source_fts USING fts5(
    source_id UNINDEXED,
    title,
    section_text,
    tokenize = 'unicode61'
);

-- Claim FTS
CREATE VIRTUAL TABLE IF NOT EXISTS claim_fts USING fts5(
    claim_id UNINDEXED,
    source_id UNINDEXED,
    source_quote,
    faithful_paraphrase,
    evidence_basis_description,
    tokenize = 'unicode61'
);
