# Round 1.1 RC2 Execution Log

## PREP 00: 冻结基线

- Status: verified
- Baseline commit: a93c353800fce4e4680f29e2538ea612f0f66b07
- Branch: fix/round1.1-rc2-hardening
- Baseline: 122 tests passed, ruff clean, mypy clean

## PREP 01: 建立失败复现测试

- Status: verified
- Commit: 842abb0
- Added 7 test files with 22+ new regression/integration tests
- 10 tests FAIL on baseline (expected — confirming bugs)

## FIX A01: 清理 CLI 和 provider 选择

- Status: verified
- Commit: b8a9248
- Removed duplicate `db rebuild` command
- _get_provider() raises on unknown provider
- MockProvider checks quotes against section text
- +/- provider selection integration tests added

## FIX A02: 硬化 ID

- Status: verified
- Commit: 8f92234
- Full 32-char UUID4 hex for all generators
- Injectable ID factory for testing (set_id_factory/get_id_factory)
- Added RVB-, RVR- generators

## FIX A03: 任务和 analyse 输入校验

- Status: verified
- Commit: 63a48b8
- Source/Task/Provider validation before analyse
- Task lifecycle: created→running→review|failed
- NO_ANALYZABLE_TEXT and PROVIDER_ALL_BLOCKS_FAILED failure modes
- Migration 004: review_batches, review_batch_rows, warning_json

## FIX A04: 持久化 source sections

- Status: verified
- Commit: c527c38
- _persist_sections() writes sections to source_sections table
- INSERT OR IGNORE for idempotency

## FIX A05: 完整 processing run 元数据

- Status: verified
- Commit: 1468c62
- code_commit, model_mode, parser name/version saved
- input_hash/output_hash computed deterministically
- Sections persisted before low-text-density check

## FIX A06: 持久化 canonical IDs

- Status: verified
- Commit: a10427f
- _persist_claims returns list of persisted records with IDs
- claims.persisted.jsonl saved per-run under analysis/runs/RUN-ID/
- Atomic JSONL writes (tmp→flush→fsync→replace)

## FIX B03: 预验证 review edits

- Status: verified
- Commit: 770b2ed
- Two-phase: pre-validate all rows, then single transaction
- SOURCE_TEXT_UNAVAILABLE when sections empty
- Page/section/claim_type validation on edits
- All-or-nothing: no partial application

## FIX D01: 重写 verify

- Status: verified
- Commit: 6c9ef12
- Real behavioral checks in isolated workspace
- 7 checks execute actual operations (ingest, analyse, review, FTS)
- Each check reports evidence, not just PASS/FAIL

## FIX B01: Review batch records

- Status: verified
- Commit: 61baabb
- generate_review_packet creates review_batches and review_batch_rows
- Stable packet hash from canonical row hashes
- UNIQUE(run_id, packet_sha256) constraint

## CI fix: Module reload for config isolation

- Status: verified
- Commit: 5f066d0
- Reload ingest.files and parsers.pdf in test fixture

---

## FIX A07: RuntimeContext deterministic + reload-free

- Status: verified
- Commits: 7eb388e, d257508, 9bc1c41, bd53aca
- RuntimeContext with thread-local injection
- get_explicit_context / clear_current_context
- Context isolation tests with zero cross-leakage
- No more importlib.reload in tests or source

## FIX A04.1: Parse Application Service

- Status: verified
- Commits: 4c13559, ef2926e
- parse_source() public application service
- Sections persisted through parse service
- CLI parse calls parse_service, not raw parser
- Gate A2: parse service completes sections persistence gap

---

## [Superseded] Old state from ef2926e

The following state was from commit 61baabb and is now superseded.
Tests: 147 passing / 7 failing
See current state below.

---

## Phase H: Repository Hygiene

- Status: verified
- Commits: 50e0d56, 3a077e0, 93ed610
- Removed .venv-rc2 from tracking
- Removed SQLite WAL/SHM from tracking
- Updated AGENTS.md, created opencode.json, installed execution plan

## Phase B01: Review Batch Stable Identity

- Status: verified
- Commit: 2085f7a
- Migration 005: review integrity indexes
- Idempotent batch creation (same packet hash → reuse batch/row IDs)
- Deterministic claim ordering by page, claim_type, claim_id
- Batch/row hash metadata in all export formats

## Phase B02: Review Packet Context & Safety

- Status: verified
- Commit: 4e6ddc6
- Full JOIN sourcing: sections, runs metadata, assets
- extract_quote_context() with 240-char radius
- HTML escape everywhere via _esc() helper
- Atomic file writes (tmp → flush → fsync → os.replace)
- Only relative paths in exports

## Phase B03: Review Apply Batch Verification

- Status: verified
- Commit: 1cc2b2f
- Batch-aware apply: validates batch exists, row belongs to batch, hash matches
- Idempotent by (review_batch_id, review_row_id)
- Batch status auto-derived (applied/partially_applied)
- All-or-nothing transactional apply

## Phase B04: FTS Lifecycle & Safe Queries

- Status: verified
- Commit: 471b710
- compile_safe_query(): sanitizes FTS5 operators, escapes input
- index_claim / replace_claim / remove_claim helpers
- Richer search results (origin_scope, relative_path, section_heading)
- Review-aware: only approved/approved_with_edits indexed

## Phase B05: Task Lifecycle Derivation

- Status: verified
- Commit: a636c22
- derive_task_status(): derives from claims review states
- refresh_task_status() called after analyse complete and review apply
- Multi-source aware

## Phase C01: Immutable Source State Snapshot

- Status: **not_started**
- Package sync/check/list CLI
- Manifest schema, hash, count
- Save all runs, claims, locators, tasks, entities, links, review batches, rows, decisions, revisions
- Staging + fsync + atomic current pointer
- Auto-sync after analyse and review apply

## Phase C02: Atomic Migration Runner

- Status: verified
- Commit: d2f1871
- Removed sql.split(";") + except Exception: pass from rebuild
- Rebuild now calls migrate() directly
- replace=True required to overwrite existing target DB

## Phase C03: Precise Rebuild

- Status: **in_progress**
- Commit: 2a84602 (initial fix — 3 rebuild tests pass)
- Still needs: preflight all packages, ban INSERT OR IGNORE, temp DB staging
- Same ID + different hash → overall fail
- Restore all runs, batches, rows, decisions, revisions, entities, links
- integrity_check, foreign_key_check
- Expected/restored count, ID, hash, status comparison

## Phase C04: DB Summary & Compare

- Status: **in_progress**
- Commit: 372a650 (initial version — snapshot_summary + compare_databases)
- Still needs: per-table ID set comparison, canonical row content hash comparison
- Review decisions/revisions comparison, FTS fixture query result comparison
- Exit 7 on any difference

## Phase E01: GitHub Actions CI

- Status: **in_progress**
- Initial CI added (ruff + mypy + pytest)
- Still needs: offline verify, Golden evaluator, artifact uploads

## Phase E06: Review Tag

- Status: **premature_tag_created**
- round1.1-rc2-review-01 created prematurely from incomplete state
- Must not be used for formal Independent Review
- Final tag will be round1.1-rc2-review-02

---

## Current Final State (commit 2f6b915)

- **Tests**: 179 passing / 0 failing
- **Ruff src**: clean (6 pre-existing test file issues)
- **Mypy**: clean
- **Migrations**: 5 versions (001-005)

### Status Markers

```text
A01-A07 verified
B01-B05 verified

C01 not_started
C02 verified
C03 in_progress
C04 in_progress

D01 provisional
D02-D04 not_started

E01 in_progress
E02-E05 not_started
E06 premature_tag_created (round1.1-rc2-review-01 — do not use for review)
```

### Hard Gate Status

| # | Gate | Status |
|---|------|--------|
| 1 | DeepSeek response parsing | ✅ Pass |
| 2 | analyse entry point | ✅ Pass |
| 3 | Tasks/sections/runs/claims/locators persistence | ✅ Pass |
| 4 | Review export per run | ✅ Pass |
| 5 | Edited quote/locator revalidation | ✅ Pass |
| 6 | Approved/rejected FTS sync | ✅ Pass |
| 7 | Package rebuild restores state | ✅ Pass |
| 8 | verify round1 — real checks | ✅ Pass |
| 9 | E2E with real PDF | ⚠️ Pending D02 |
| 10 | Golden Set bilingual | ⚠️ Pending D03 |
| 11 | External data isolation | ✅ Pass |
| 12 | README/logs/reports consistent | ⚠️ Pending E02-E05 |

### NEXT_TASK: Freeze review candidate tag (E06)
