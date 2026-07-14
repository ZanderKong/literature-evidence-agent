# Gate C Report — Package Snapshot, Atomic Migration, Precise Rebuild, DB Compare

- **Date**: 2026-07-14
- **Baseline**: fb52729
- **Tests**: 185 passed / 0 failed

## C01: Immutable Source State Snapshot ✅

- `sync_source()` — complete DB state → JSONL records in atomic snapshot
- `check_source()` — validates manifest, record counts, file presence
- `list_snapshots()` — all snapshots for a source
- Snapshots under: SRC-ID/state/snapshots/SNP-ID/records/*.jsonl
- 13 tables: tasks, sources, assets, sections, runs, claims, locators, entities, links, batches, rows, decisions, revisions
- Staging tmp dir → fsync → rename, atomic current.json pointer
- Auto-sync after analyse complete and review apply

## C02: Atomic Migration Runner ✅

- Removed `sql.split(";")` + `except Exception: pass` from rebuild
- Rebuild calls `migrate()` directly
- `replace=True` required to overwrite existing target DB

## C03: Precise Rebuild ✅

- Preflight all packages — detect RESTORE_CONFLICT (same ID, different content)
- Temp DB staging (`.tmp.sqlite`) — verify integrity before atomic replace
- Backup of existing DB when replace=True
- No `INSERT OR IGNORE` anywhere
- Restores: tasks, sources, assets, sections, runs, claims, locators, entities, links, batches, rows, decisions, revisions
- Tables imported in dependency order (respecting FK constraints)
- Backward compatible with old package structure
- `PRAGMA integrity_check` + `PRAGMA foreign_key_check` after rebuild
- All 6 rebuild tests pass (up from 3 failing)

## C04: Database Summary & Compare ✅

- `snapshot_summary()` — per-table counts, ID set hashes, content hashes
- `compare_databases()` — comprehensive comparison of two DBs
- FTS query result comparison (hash of claim_id sets for test/quote/approve)
- Review distribution comparison
- Exit codes: identical=0, different=7, invalid=3

## Gate C Verdict: PASS
