-- Migration 001: Initial schema
-- Creates all core tables for the literature evidence database.

PRAGMA foreign_keys = ON;

-- Schema migrations tracking
CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    applied_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Research tasks
CREATE TABLE IF NOT EXISTS research_tasks (
    task_id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    user_request TEXT NOT NULL,
    research_background TEXT,
    task_mode TEXT NOT NULL CHECK (
        task_mode IN (
            'analyse_uploaded',
            'source_complete_analysis',
            'evidence_query'
        )
    ),
    analysis_depth TEXT NOT NULL CHECK (
        analysis_depth IN ('task_focused', 'source_complete')
    ),
    status TEXT NOT NULL CHECK (
        status IN ('created', 'running', 'review', 'completed', 'failed')
    ),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- Sources
CREATE TABLE IF NOT EXISTS sources (
    source_id TEXT PRIMARY KEY,
    source_type TEXT NOT NULL CHECK (
        source_type IN (
            'journal_article', 'preprint', 'conference_paper',
            'technical_report', 'product_documentation', 'other'
        )
    ),
    title TEXT,
    authors_json TEXT NOT NULL DEFAULT '[]',
    organisation TEXT,
    publication_date TEXT,
    doi TEXT,
    language TEXT,
    version_label TEXT,
    original_file_sha256 TEXT NOT NULL UNIQUE,
    origin_scope TEXT NOT NULL DEFAULT 'external'
        CHECK (origin_scope = 'external'),
    scientific_verification_status TEXT NOT NULL DEFAULT 'unverified'
        CHECK (scientific_verification_status IN (
            'unverified', 'internally_reproduced',
            'independently_confirmed', 'contradicted'
        )),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- Source assets
CREATE TABLE IF NOT EXISTS source_assets (
    asset_id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL,
    asset_type TEXT NOT NULL CHECK (
        asset_type IN ('main_document', 'supplementary', 'attachment')
    ),
    relative_path TEXT NOT NULL,
    mime_type TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    file_size INTEGER NOT NULL CHECK (file_size >= 0),
    acquired_from TEXT,
    acquired_at TEXT NOT NULL,
    FOREIGN KEY (source_id) REFERENCES sources(source_id) ON DELETE CASCADE,
    UNIQUE (source_id, sha256)
);

-- Source sections
CREATE TABLE IF NOT EXISTS source_sections (
    section_id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL,
    section_type TEXT NOT NULL,
    heading TEXT,
    page_start INTEGER,
    page_end INTEGER,
    sequence_number INTEGER NOT NULL,
    text TEXT NOT NULL,
    parser_name TEXT NOT NULL,
    parser_version TEXT NOT NULL,
    text_sha256 TEXT NOT NULL,
    FOREIGN KEY (source_id) REFERENCES sources(source_id) ON DELETE CASCADE,
    UNIQUE (source_id, sequence_number)
);

-- Source claims (core)
CREATE TABLE IF NOT EXISTS source_claims (
    claim_id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL,
    task_id TEXT,
    claim_type TEXT NOT NULL CHECK (
        claim_type IN (
            'background_statement', 'method_statement',
            'reported_observation', 'reported_result',
            'author_interpretation', 'author_conclusion',
            'author_hypothesis', 'author_limitation',
            'future_work'
        )
    ),
    source_quote TEXT NOT NULL,
    faithful_paraphrase TEXT NOT NULL,
    evidence_basis_description TEXT NOT NULL,
    scope_description TEXT,
    author_hedging TEXT,
    origin_scope TEXT NOT NULL DEFAULT 'external'
        CHECK (origin_scope = 'external'),
    record_review_status TEXT NOT NULL DEFAULT 'pending'
        CHECK (record_review_status IN (
            'pending', 'approved', 'approved_with_edits', 'rejected'
        )),
    scientific_verification_status TEXT NOT NULL DEFAULT 'unverified'
        CHECK (scientific_verification_status IN (
            'unverified', 'internally_reproduced',
            'independently_confirmed', 'contradicted'
        )),
    quote_match_status TEXT NOT NULL CHECK (
        quote_match_status IN ('exact', 'normalised', 'ambiguous', 'not_found')
    ),
    created_by_run_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (source_id) REFERENCES sources(source_id) ON DELETE CASCADE,
    FOREIGN KEY (task_id) REFERENCES research_tasks(task_id) ON DELETE SET NULL
);

-- Claim locators
CREATE TABLE IF NOT EXISTS claim_locators (
    locator_id TEXT PRIMARY KEY,
    claim_id TEXT NOT NULL UNIQUE,
    section_id TEXT,
    page INTEGER,
    paragraph_index INTEGER,
    figure_label TEXT,
    table_label TEXT,
    supplementary_label TEXT,
    character_start INTEGER,
    character_end INTEGER,
    locator_confidence TEXT NOT NULL CHECK (
        locator_confidence IN ('high', 'medium', 'low')
    ),
    FOREIGN KEY (claim_id) REFERENCES source_claims(claim_id) ON DELETE CASCADE,
    FOREIGN KEY (section_id) REFERENCES source_sections(section_id) ON DELETE SET NULL
);

-- Entities
CREATE TABLE IF NOT EXISTS entities (
    entity_id TEXT PRIMARY KEY,
    entity_type TEXT NOT NULL CHECK (
        entity_type IN (
            'material', 'compound', 'product', 'method', 'instrument',
            'property', 'process', 'company', 'author', 'institution', 'application'
        )
    ),
    canonical_name TEXT NOT NULL,
    display_name TEXT NOT NULL,
    normalised_name TEXT NOT NULL,
    aliases_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL,
    UNIQUE (entity_type, normalised_name)
);

-- Claim-entity links
CREATE TABLE IF NOT EXISTS claim_entity_links (
    claim_id TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    role TEXT NOT NULL CHECK (
        role IN ('subject', 'object', 'material', 'method',
                 'property', 'condition', 'application')
    ),
    PRIMARY KEY (claim_id, entity_id, role),
    FOREIGN KEY (claim_id) REFERENCES source_claims(claim_id) ON DELETE CASCADE,
    FOREIGN KEY (entity_id) REFERENCES entities(entity_id) ON DELETE CASCADE
);

-- Processing runs
CREATE TABLE IF NOT EXISTS processing_runs (
    run_id TEXT PRIMARY KEY,
    task_id TEXT,
    source_id TEXT,
    module_name TEXT NOT NULL,
    model_name TEXT,
    model_mode TEXT,
    prompt_version TEXT,
    parser_name TEXT,
    parser_version TEXT,
    code_commit TEXT,
    input_hash TEXT NOT NULL,
    output_hash TEXT,
    status TEXT NOT NULL CHECK (
        status IN ('started', 'completed', 'failed', 'cancelled')
    ),
    error_type TEXT,
    error_message TEXT,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    FOREIGN KEY (task_id) REFERENCES research_tasks(task_id) ON DELETE SET NULL,
    FOREIGN KEY (source_id) REFERENCES sources(source_id) ON DELETE SET NULL
);

-- Review decisions
CREATE TABLE IF NOT EXISTS review_decisions (
    review_id TEXT PRIMARY KEY,
    object_type TEXT NOT NULL CHECK (
        object_type IN ('claim', 'source', 'entity_link')
    ),
    object_id TEXT NOT NULL,
    decision TEXT NOT NULL CHECK (
        decision IN ('approve', 'approve_with_edits', 'reject',
                     'mark_missing', 'needs_followup')
    ),
    original_content_json TEXT NOT NULL,
    edited_content_json TEXT,
    reviewer TEXT NOT NULL,
    review_reason TEXT,
    reviewed_at TEXT NOT NULL
);

-- Claim revisions
CREATE TABLE IF NOT EXISTS claim_revisions (
    revision_id TEXT PRIMARY KEY,
    claim_id TEXT NOT NULL,
    previous_content_json TEXT NOT NULL,
    new_content_json TEXT NOT NULL,
    changed_by TEXT NOT NULL,
    change_reason TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (claim_id) REFERENCES source_claims(claim_id) ON DELETE CASCADE
);
