# v0.1.2 Release Baseline

- **Date**: 2026-07-14
- **Base version**: v0.1.1

## Reference SHA

| Ref | SHA |
|-----|-----|
| main | `6aff4e6c7a5f9f5b9114571fd77da4dff62231ad` |
| dev | `6aff4e6c7a5f9f5b9114571fd77da4dff62231ad` |
| origin/main | `6aff4e6c7a5f9f5b9114571fd77da4dff62231ad` |
| origin/dev | `6aff4e6c7a5f9f5b9114571fd77da4dff62231ad` |
| v0.1.1 tag | `6aff4e6c7a5f9f5b9114571fd77da4dff62231ad` |

## Project Version

- pyproject.toml: `0.1.1`
- importlib.metadata: `0.1.1`

## Scope for v0.1.2

- Release engineering and documentation only
- No core evidence-processing behavior changes
- Golden evaluation becomes deterministic offline conformance
- README smoke test in isolated workspace
- CI hardening (release gate, artifacts, live DeepSeek)
- Closure of deferred v0.1.1 findings

## Forbidden Changes

- No core module modifications (rebuild, state_compare, snapshot, review, FTS, migrations)
- No new features (OCR, multimodal, vector DB, web UI)
- No new database tables or migrations
- No new claim types or review decisions
