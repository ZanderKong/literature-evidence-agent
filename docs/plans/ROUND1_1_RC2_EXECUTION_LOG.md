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

## Current State Summary (Phase H baseline: 3a077e0)

- **Tests**: 169 passing / 3 failing
- **Ruff**: 24 issues (fixable, addressed in Phase H cleanup)
- **Mypy**: clean
- **Migrations**: 4 versions (001 initial, 002 FTS, 003 constraints, 004 review_batches)
- **Phase H committed**: H00 freeze, H01 .venv-rc2 cleanup, H02 WAL/SHM cleanup

### Remaining Failures (all rebuild, mapped to Phase C)

| # | Test Node | Root Cause | Mapped To |
|---|-----------|-----------|-----------|
| 1 | `test_rebuild_loses_review_decisions` | rebuild doesn't import review_decisions from package | C03 |
| 2 | `test_rebuild_loses_locator_ids` | rebuild regenerates locator IDs | C03 |
| 3 | `test_rebuild_does_not_restore_decisions_and_revisions` | rebuild doesn't restore decisions/revisions | C03 |

### Status Markers

```text
A01 verified
A02 verified
A03 verified
A04 verified
A05 verified
A06 verified
A07 verified

B01 provisional_verified
B02 not_started
B03 provisional_verified
B04 not_started
B05 not_started

C01-C04 not_started
D01 provisional
D02-D04 not_started
E01-E06 not_started
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
| 7 | Package rebuild restores state | ❌ Fail (3 rebuild tests, mapped to Phase C) |
| 8 | verify round1 — real checks | ✅ Pass |
| 9 | E2E with real PDF and strong assertions | ⚠️ To be verified in D02 |
| 10 | Golden Set bilingual | ⚠️ Not yet started (D03) |
| 11 | External data isolation | ✅ Pass |
| 12 | README/logs/reports consistent | ⚠️ Not yet updated (Phase E) |
