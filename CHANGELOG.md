# Changelog

## v0.1.2 (next)

- Release engineering and documentation: no core behavior changes
- Deterministic offline golden evaluation (fixture + pipeline-smoke modes)
- Isolated README smoke test in temporary workspace
- Fixed F-002: task status update failure now logged
- Fixed F-006, F-007: lint cleanup in test files
- Removed legacy Round/RC2/branch naming from active docs
- Release gate now runs golden fixture, pipeline-smoke, and readme-smoke
- CI uses deterministic release gate; live DeepSeek via workflow_dispatch
- Release records reconciled for v0.1.1

## v0.1.1

- Initial stable release
- Full pipeline: ingest, parse, analyse, review, FTS, rebuild, compare, verify
- Golden set with 40 annotated claims
- Machine-enforced release gate
