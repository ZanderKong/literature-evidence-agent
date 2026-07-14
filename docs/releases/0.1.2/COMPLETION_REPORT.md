# Completion Report — v0.1.2

- **Version**: v0.1.2
- **RC tag**: v0.1.2-rc.1 (pending CI verification)
- **Release scope**: Release engineering and documentation
- **Base version**: v0.1.1 (`6aff4e6c`)

## Scope

v0.1.2 is a release engineering and documentation release. No core evidence-processing behavior has been changed.

### Changes

- Golden evaluation is now deterministic offline conformance (fixture + pipeline-smoke modes)
- README smoke test runs in isolated temporary workspace
- Fixed F-002: task status update failure now logged
- Fixed F-006, F-007: lint cleanup in test files
- Removed legacy Round/RC2/branch naming from active docs
- Release gate runs golden fixture, pipeline-smoke, and readme-smoke
- CI uses deterministic release gate; live DeepSeek via workflow_dispatch
- v0.1.1 release records reconciled

### No Changes

- No core module modifications (rebuild, state_compare, snapshot, review, FTS, migrations)
- No new features (OCR, multimodal, vector DB, web UI)
- No new database tables or migrations
- No new claim types or review decisions

## Verification

| Check | Result |
|-------|--------|
| pytest 3x | 206 passed, 0 failed |
| Random seeds 1/2/3 | PASS |
| Ruff | PASS |
| Mypy | PASS |
| Verify | PASS |
| Golden fixture | PASS (all thresholds) |
| CLI E2E | PASS |
| Release gate | PENDING remote CI |

## Live DeepSeek

BLOCKED_EXTERNAL — key not configured.

## CI

Local verification passes. Remote GitHub Actions evidence pending.

## Known Limitations

- PDF scanning without OCR fallback not supported
- No multi-modal visual/micrograph analysis
- Golden evaluation is deterministic offline conformance, not live model quality assessment
