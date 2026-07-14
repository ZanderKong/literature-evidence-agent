# Completion Report — v0.1.1

- **Version**: v0.1.1
- **Release SHA**: `7a9307f84f829b817de44f9d6606a2aadbb2c4e9` (RC), final tag pending
- **Release Branch**: `fix/round1.1-rc2-hardening`
- **Python**: 3.11, 3.12
- **Migrations**: 5 versions (001-005)

## Scope

v0.1.1 consolidates the former Round 1.1 hardening work into a release-gated, verified version. Capabilities:

- PDF ingest with SHA-256 deduplication
- Page mapping and section parsing (pdfplumber)
- DeepSeek API text claim extraction (with Mock provider for testing)
- Deterministic claim validation (quote match, locator cross-validation)
- Review batch export (CSV, JSONL, MD, HTML) with stable identities
- Review apply with batch/row validation, idempotency, revision tracking
- FTS5 full-text search with review-aware lifecycle
- Task lifecycle derivation from claims state
- Manifest v3 snapshots with per-file SHA-256 integrity
- Precise database rebuild (temp DB, conflict detection, atomic replace)
- Canonical database comparison with ID sets and content hashes
- RuntimeContext isolation (no env mutation, no importlib.reload)
- CLI E2E pipeline with strict exit code assertions
- Bilingual golden set (40 annotations, EN+CN, per-annotation evaluator)
- Machine-enforced Release Gate script
- CI workflow (ruff, mypy, pytest, golden)

## Test Evidence

All results from local execution as of 2026-07-14.

| Check | Result |
|-------|--------|
| pytest run 1 (203 tests) | PASS |
| pytest run 2 | PASS |
| pytest run 3 | PASS |
| seed 1 | PASS |
| seed 2 | PASS |
| seed 3 | PASS |
| Ruff | PASS |
| Mypy | PASS |
| CLI E2E | PASS |
| Snapshot/Rebuild | PASS |
| Review workflow | PASS |
| DB Compare exit 0 | PASS |
| Golden Set thresholds | PASS |
| Repo hygiene | PASS |

## Live DeepSeek

**BLOCKED_EXTERNAL** — `EVIDENCE_AGENT_LLM_API_KEY` not configured in environment.

## Independent Review

See `docs/releases/0.1.1/INDEPENDENT_REVIEW.md`.

| Severity | Count | Open |
|----------|-------|------|
| P0 | 0 | 0 |
| P1 | 1 | 0 (fixed) |
| P2 | 3 | 3 (deferred) |
| P3 | 3 | 3 (deferred) |

**Verdict**: PASS

## Known Limitations

- PDF parsing depends on pdfplumber — scanned PDFs without OCR fallback are not supported
- No multi-modal visual understanding for figures, charts, or micrographs
- Golden Set size is limited (40 annotations, 4 source files)
- Scientific verification_status is separate from record review status
- DeepSeek live behavior depends on external API availability
- Task cross-reference validation is scoped per-snapshot

## Compatibility

- v0.1.0 data can be imported and analyzed
- Old package formats are supported via rebuild fallback (temp conversion)
- Migrations 004 and 005 are auto-applied on database init
- Old snapshot manifest v2 format is read-compatible

## Next Version: v0.2.0

Planned capabilities:
- Document Router (text vs. scanned classification)
- OCR fallback for scanned PDFs
- Layout-aware parsing
- Figure/Table asset extraction
- Multimodal Evidence Provider (visual claims)
- Cross-modal claim synthesis
