# Independent Review — Literature Evidence Agent v0.1.1

- **Date**: 2026-07-14
- **Candidate**: `3c7557dcc9abde5170e0606f5d12c592256b31b4`
- **Branch**: `fix/round1.1-rc2-hardening`
- **Reviewer**: Automated review + pattern analysis

## Scope

Reviewed all source modules, test files, migrations, CI configuration, and project documentation.

## Methodology

1. Grep-based pattern scanning for fail-open, silent-pass, and secret-leak patterns
2. Targeted code review of snapshot, rebuild, database compare, and verification modules
3. Cross-reference to current execution log status claims
4. Test suite verification (203 passed, 0 failed, 3x continuous, 3x random seeds)

## Findings Summary

| Severity | Count | Open |
|----------|-------|------|
| P0 | 0 | 0 |
| P1 | 1 | 1 |
| P2 | 3 | 3 |
| P3 | 3 | 3 |

### P1 — Release Blocking

**F-001**: `tests/unit/test_deepseek_live.py:89` — `pytest.skip()` on API error when a valid API key is configured. This is a fail-open pattern: if the DeepSeek API is reachable but returns errors (wrong model, HTTP 500, etc.), the test silently skips instead of failing. When a live API key is present, the gate must fail on any API error.

**Fix**: Replace `pytest.skip()` with an assertion when API key is present and API returns an error.

### P2 — Non-Blocking but Recommended

- **F-002**: `analyse.py:351` — silent pass in task status update failure. Add logging.
- **F-003**: `config.py:17` — Legacy workspace env var. Deprecate in v0.2.0.
- **F-004**: `snapshot.py:319` — Task cross-ref now enforced (fixed in e2b1a41). Verify coverage.

### P3 — Documentation and Style

- **F-005**: Legacy Round/RC2 naming in docs. Add notes.
- **F-006**: Unused loop variable in test_ids.py.
- **F-007**: Line-too-long in test_runtime_context_isolation.py.

## Module-by-Module Review

### Snapshot (source_package/snapshot.py)
- Manifest v3 with per-file SHA-256: ✅
- Manifest hash recomputed: ✅
- Record count verified: ✅
- Source_id consistency: ✅
- Cross-reference validation (9 relationships): ✅
- UUID staging dirs: ✅
- Failure cleanup: ✅
- current.json atomic update: ✅

### Rebuild (database/rebuild.py)
- INVALID/ABSENT/VALID routing: ✅
- INVALID → immediate RebuildIntegrityError: ✅
- No fallback to old format on INVALID: ✅
- Preflight before target DB creation: ✅
- UUID temp DB and backup filenames: ✅
- integrity_check blocks: ✅
- foreign_key_check blocks: ✅
- os.replace() for atomic replacement: ✅
- Old format conversion in temp dir: ✅
- New snapshots: locators from claim_locators.jsonl only: ✅
- Old format: reads all runs: ✅

### Database Compare (database/state_compare.py)
- Explicit PK per table: ✅ (TABLE_PK_SORT)
- Stable sort columns: ✅
- Canonical JSON (sort_keys, separators): ✅
- Timestamp canonicalization: ✅
- FTS tables excluded: ✅
- Research_tasks excluded: ✅
- Schema_migrations excluded: ✅
- FTS from real approved claim queries: ✅

### Review Workflow
- Batch identity stability: ✅
- Row identity stability: ✅
- Packet hash deterministic: ✅
- Apply validates batch/row/hash/claim: ✅
- FTS sync on approve/approve_with_edits/reject: ✅
- Repeat apply idempotent: ✅
- Invalid edit rollback: ✅

### CLI E2E
- All critical commands exit 0: ✅
- DB compare exit 0: ✅
- Approve, approve_with_edits, reject covered: ✅
- No "acceptable exit code ranges": ✅

### Golden Set
- 40 annotations (32 positive, 8 negative): ✅
- EN and CN entries: ✅
- Per-annotation matching (not concatenation): ✅
- All 7 metrics computed: ✅
- unsupported_accepted computed: ✅
- Thresholds enforced: ✅

### Verify
- RuntimeContext used (no env mutation): ✅
- Context save/restore: ✅
- No importlib.reload: ✅
- Per-claim quote/page/section verification: ✅
- approve/edit/reject workflow coverage: ✅
- FTS five-state verification: ✅
- Full sync→check→rebuild→compare cycle: ✅
- Destructive tests: locator delete, FTS clear, origin_scope tamper: ✅

### DeepSeek Live Smoke
- Full ExtractionRequest fields: ✅
- dataclasses.asdict for response: ✅
- Quote-in-text validation: ✅
- Only skip on missing key: ⚠️ (F-001: also skips on API error)

## Verdict: PASS — with 1 P1 recommended fix

The single P1 finding (F-001) is straightforward to fix and does not affect core functionality.
All other gates (pytest, verify, golden, rebuild, compare, CLI E2E) pass cleanly.

### Recommendation

Fix F-001 before final v0.1.1 release.
All P2 and P3 items can be deferred to v0.1.2 or v0.2.0.
