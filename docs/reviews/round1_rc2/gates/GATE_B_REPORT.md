# Gate B Report — Review, FTS, Task Lifecycle

- **Date**: 2026-07-14
- **Baseline**: fb52729
- **Tests**: 185 passed / 0 failed

## B01: Review Batch Stable Identity ✅

- Migration 005: review integrity indexes (UNIQUE batch_row, claim lookup, run+status)
- `hash_review_row()` / `hash_review_packet()` — deterministic canonical hashing
- Same packet hash → reuse batch/row IDs (idempotent)
- Deterministic ordering: COALESCE(page, 2147483647), claim_type, claim_id
- Batch/row/hash metadata in CSV, JSONL, MD, HTML exports
- 10 passing tests

## B02: Review Packet Context & Safety ✅

- Full JOIN: source_claims, claim_locators, sources, source_assets, source_sections, processing_runs
- `extract_quote_context()` — 240-char radius, exact + normalised match
- HTML escape via `_esc()` helper for all output formats
- Atomic file writes: tmp → flush → fsync → os.replace
- Source_relative_path only (no absolute paths)
- Section heading, page, model/mode, prompt/parser version, code commit in output

## B03: Review Apply Batch Verification ✅

- Batch-aware: validates batch exists, row belongs to batch, hash matches
- Idempotent by (review_batch_id, review_row_id)
- `_update_batch_status()` — auto-derived (applied / partially_applied)
- All-or-nothing transactional apply
- FTS sync after approve/approve_with_edits/reject

## B04: FTS Lifecycle & Safe Queries ✅

- `compile_safe_query()` — strips FTS5 operators, escapes input
- `index_claim()` / `replace_claim()` / `remove_claim()` helpers
- Review-aware: only approved/approved_with_edits indexed
- Richer search results (origin_scope, relative_path, section_heading)

## B05: Task Lifecycle Derivation ✅

- `derive_task_status()` — from claims review states
- `refresh_task_status()` — called after analyse complete and review apply
- Multi-source aware

## Gate B Verdict: PASS
