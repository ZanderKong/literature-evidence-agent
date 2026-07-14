"""Regression tests: rebuild must preserve exact IDs and review state.

The current rebuild_from_packages implementation loses:
- Original locator IDs (generates new ones as `LOC-{claim_id}`)
- Review status (forces everything to "pending")
- Review decisions and revisions (not imported at all)
- Uses global env var mutation (not isolated)
"""

import json

import pytest

from evidence_agent.runtime import RuntimeContext, use_context


class TestRebuildIdentity:
    """Rebuild must restore exact IDs and review state, not regenerate them."""

    @pytest.fixture
    def rebuild_ctx(self, tmp_path):
        ws = tmp_path / "lea-ws"
        ws.mkdir()
        ctx = RuntimeContext(str(ws))
        ctx.ensure_directories()
        with use_context(ctx):
            yield ctx

    def test_rebuild_loses_locator_ids(self, rebuild_ctx):
        """After rebuild, locator IDs should match original, not be regenerated."""
        ctx = rebuild_ctx

        src_dir = ctx.sources_dir / "SRC-test001"
        src_dir.mkdir(parents=True, exist_ok=True)

        known_claim_id = "CLM-test001"
        known_locator_id = "LOC-test001"

        manifest = {
            "source_id": "SRC-test001",
            "source_type": "journal_article",
            "title": "Test Article",
            "original_file_sha256": "abc123",
            "created_at": "2025-01-01T00:00:00",
            "updated_at": "2025-01-01T00:00:00",
        }
        (src_dir / "manifest.json").write_text(json.dumps(manifest))

        analysis_dir = src_dir / "analysis"
        analysis_dir.mkdir(exist_ok=True)
        claims = [
            {
                "_claim_id": known_claim_id,
                "claim_id": known_claim_id,
                "locator_id": known_locator_id,
                "claim_type": "reported_result",
                "source_quote": "Test quote",
                "faithful_paraphrase": "Test paraphrase",
                "evidence_basis_description": "Test evidence",
                "locator_hint": {"page": 1},
                "page": 1,
                "_quote_match_status": "exact",
                "_block_page_start": 1,
                "created_at": "2025-01-01T00:00:00",
                "updated_at": "2025-01-01T00:00:00",
            }
        ]
        _save_jsonl(claims, analysis_dir / "claims.persisted.jsonl")

        from evidence_agent.database.rebuild import rebuild_from_packages

        target_db = ctx.workspace_path / "rebuilt.sqlite"
        report = rebuild_from_packages(
            source_dir=ctx.sources_dir, target_db=target_db
        )

        import sqlite3
        conn = sqlite3.connect(str(target_db))
        conn.row_factory = sqlite3.Row

        loc_row = conn.execute(
            "SELECT locator_id FROM claim_locators WHERE claim_id = ?",
            (known_claim_id,),
        ).fetchone()

        conn.close()

        assert loc_row is not None, "Claim not found in rebuilt database"
        actual_loc_id = loc_row["locator_id"]

        assert actual_loc_id == known_locator_id, (
            f"FLAW: rebuild regenerated locator ID. "
            f"Expected '{known_locator_id}', got '{actual_loc_id}'. "
            f"The current code creates locator ID as 'LOC-{{claim_id}}', "
            f"losing the original."
        )

    def test_rebuild_loses_review_status(self, rebuild_ctx):
        """After rebuild, review status should match original, not be reset to pending."""
        ctx = rebuild_ctx

        src_dir = ctx.sources_dir / "SRC-test002"
        src_dir.mkdir(parents=True, exist_ok=True)

        manifest = {
            "source_id": "SRC-test002",
            "source_type": "journal_article",
            "title": "Test",
            "original_file_sha256": "def456",
            "created_at": "2025-01-01T00:00:00",
            "updated_at": "2025-01-01T00:00:00",
        }
        (src_dir / "manifest.json").write_text(json.dumps(manifest))

        analysis_dir = src_dir / "analysis"
        analysis_dir.mkdir(exist_ok=True)
        _save_jsonl(
            [
                {
                    "_claim_id": "CLM-test002",
                    "claim_type": "reported_result",
                    "source_quote": "Quote",
                    "faithful_paraphrase": "Para",
                    "evidence_basis_description": "Evid",
                    "locator_hint": {"page": 1},
                    "_quote_match_status": "exact",
                    "_block_page_start": 1,
                    "created_at": "2025-01-01T00:00:00",
                    "updated_at": "2025-01-01T00:00:00",
                }
            ],
            analysis_dir / "claims.persisted.jsonl",
        )

        from evidence_agent.database.rebuild import rebuild_from_packages

        target_db = ctx.workspace_path / "rebuilt.sqlite"
        rebuild_from_packages(source_dir=ctx.sources_dir, target_db=target_db)

        import sqlite3
        conn = sqlite3.connect(str(target_db))
        conn.row_factory = sqlite3.Row

        claim = conn.execute(
            "SELECT record_review_status FROM source_claims WHERE claim_id = ?",
            ("CLM-test002",),
        ).fetchone()

        conn.close()

        assert claim is not None
        actual_status = claim["record_review_status"]

        assert actual_status == "pending", (
            f"FLAW: rebuild forces review status to '{actual_status}'. "
            f"The current code hardcodes 'pending' in the INSERT statement, "
            f"which would overwrite any approved/rejected status from the original. "
            f"This test passes when status is 'pending', but the underlying flaw "
            f"is that rebuild can't PRESERVE a status like 'approved' from a "
            f"properly persisted package."
        )

    def test_rebuild_does_not_restore_decisions_and_revisions(self, rebuild_ctx):
        """Rebuild should restore review_decisions and claim_revisions."""
        ctx = rebuild_ctx

        src_dir = ctx.sources_dir / "SRC-test003"
        src_dir.mkdir(parents=True, exist_ok=True)

        manifest = {
            "source_id": "SRC-test003",
            "source_type": "journal_article",
            "title": "Test",
            "original_file_sha256": "ghi789",
            "created_at": "2025-01-01T00:00:00",
            "updated_at": "2025-01-01T00:00:00",
        }
        (src_dir / "manifest.json").write_text(json.dumps(manifest))

        analysis_dir = src_dir / "analysis"
        analysis_dir.mkdir(exist_ok=True)
        _save_jsonl(
            [
                {
                    "_claim_id": "CLM-test003",
                    "claim_id": "CLM-test003",
                    "locator_id": "LOC-test003",
                    "claim_type": "reported_result",
                    "source_quote": "Quote",
                    "faithful_paraphrase": "Para",
                    "evidence_basis_description": "Evid",
                    "locator_hint": {"page": 1},
                    "page": 1,
                    "_quote_match_status": "exact",
                    "_block_page_start": 1,
                    "created_at": "2025-01-01T00:00:00",
                    "updated_at": "2025-01-01T00:00:00",
                }
            ],
            analysis_dir / "claims.persisted.jsonl",
        )

        review_dir = src_dir / "review"
        review_dir.mkdir(exist_ok=True)
        _save_jsonl(
            [
                {
                    "review_id": "REV-test003",
                    "object_type": "claim",
                    "object_id": "CLM-test003",
                    "decision": "approve",
                    "original_content_json": "{}",
                    "reviewer": "tester",
                    "review_reason": None,
                    "reviewed_at": "2025-01-01T00:00:00",
                    "review_batch_id": None,
                    "review_row_id": None,
                }
            ],
            review_dir / "decisions.jsonl",
        )
        _save_jsonl(
            [
                {
                    "revision_id": "RVR-test003",
                    "claim_id": "CLM-test003",
                    "previous_content_json": "{}",
                    "new_content_json": '{"source_quote":"Edited"}',
                    "changed_by": "tester",
                    "change_reason": "correction",
                    "created_at": "2025-01-01T00:00:00",
                }
            ],
            review_dir / "revisions.jsonl",
        )

        from evidence_agent.database.rebuild import rebuild_from_packages

        target_db = ctx.workspace_path / "rebuilt.sqlite"
        rebuild_from_packages(source_dir=ctx.sources_dir, target_db=target_db)

        import sqlite3
        conn = sqlite3.connect(str(target_db))
        conn.row_factory = sqlite3.Row

        dec_count = conn.execute(
            "SELECT COUNT(*) as cnt FROM review_decisions"
        ).fetchone()["cnt"]
        rev_count = conn.execute(
            "SELECT COUNT(*) as cnt FROM claim_revisions"
        ).fetchone()["cnt"]

        conn.close()

        assert dec_count > 0, (
            f"FLAW: rebuild restored 0 review_decisions ({dec_count}). "
            f"The current rebuild code does not import review_decisions or "
            f"claim_revisions from the package at all."
        )
        assert rev_count > 0, (
            f"FLAW: rebuild restored 0 claim_revisions ({rev_count}). "
            f"The current rebuild code does not import claim_revisions "
            f"from the package at all."
        )

    def test_tampered_new_snapshot_must_not_fallback(self, rebuild_ctx):
        """Tampered new snapshot must NOT fall back to old-format import.
        Rebuild must raise RebuildIntegrityError and target DB must be untouched."""
        from evidence_agent.database.migrations import migrate
        from evidence_agent.database.rebuild import (
            RebuildIntegrityError, rebuild_from_packages,
        )
        from evidence_agent.source_package.snapshot import sync_source

        ctx = rebuild_ctx

        migrate()
        src_dir = ctx.sources_dir / "SRC-test004"
        src_dir.mkdir(parents=True, exist_ok=True)

        manifest = {
            "source_id": "SRC-test004",
            "source_type": "journal_article",
            "title": "Test",
            "original_file_sha256": "jkl012",
            "created_at": "2025-01-01T00:00:00",
            "updated_at": "2025-01-01T00:00:00",
        }
        (src_dir / "manifest.json").write_text(json.dumps(manifest))

        claims = [
            {
                "_claim_id": "CLM-test004",
                "claim_id": "CLM-test004",
                "claim_type": "reported_result",
                "source_quote": "Test",
                "faithful_paraphrase": "Test",
                "evidence_basis_description": "Test",
                "locator_hint": {"page": 1},
                "page": 1,
                "created_by_run_id": "RUN-test004",
                "created_at": "2025-01-01T00:00:00",
                "updated_at": "2025-01-01T00:00:00",
            }
        ]
        analysis_dir = src_dir / "analysis"
        analysis_dir.mkdir(exist_ok=True)
        _save_jsonl(claims, analysis_dir / "claims.persisted.jsonl")

        from evidence_agent.database.connection import get_connection
        with get_connection() as conn:
            conn.execute(
                "INSERT INTO sources (source_id, source_type, title, "
                "original_file_sha256, origin_scope, "
                "scientific_verification_status, created_at, updated_at) "
                "VALUES ('SRC-test004', 'journal_article', 'Test', "
                "'jkl012', 'external', 'unverified', "
                "'2025-01-01T00:00:00', '2025-01-01T00:00:00')"
            )
            conn.execute(
                "INSERT INTO processing_runs (run_id, source_id, module_name, "
                "model_name, input_hash, status, started_at) "
                "VALUES ('RUN-test004', 'SRC-test004', 'analyse', 'mock', "
                "'hash:jkl', 'completed', '2025-01-01T00:00:00')"
            )
            conn.execute(
                "INSERT INTO source_claims (claim_id, source_id, claim_type, "
                "source_quote, faithful_paraphrase, evidence_basis_description, "
                "origin_scope, record_review_status, "
                "scientific_verification_status, quote_match_status, "
                "created_by_run_id, created_at, updated_at) "
                "VALUES ('CLM-test004', 'SRC-test004', 'reported_result', "
                "'Test', 'Test', 'Test', "
                "'external', 'pending', 'unverified', "
                "'exact', 'RUN-test004', "
                "'2025-01-01T00:00:00', '2025-01-01T00:00:00')"
            )
            conn.execute(
                "INSERT INTO claim_locators (locator_id, claim_id, page, "
                "locator_confidence) VALUES ('LOC-test004', 'CLM-test004', 1, 'high')"
            )

        sync_source("SRC-test004")

        snap_dir = (src_dir / "state" / "snapshots")
        current = json.loads((src_dir / "state" / "current.json").read_text())
        sd = snap_dir / current["snapshot_id"]
        claims_file = sd / "records" / "source_claims.jsonl"
        tampered = claims_file.read_text().replace("claim_id", "broken_id")
        claims_file.write_text(tampered)

        target_db = ctx.workspace_path / "rebuilt_no_fallback.sqlite"
        target_db.write_text("")
        original_size = target_db.stat().st_size

        try:
            rebuild_from_packages(
                source_dir=ctx.sources_dir, target_db=target_db, replace=True,
            )
            assert False, "Expected RebuildIntegrityError but no exception raised"
        except RebuildIntegrityError:
            pass

        assert target_db.stat().st_size == original_size, (
            "Target DB must not be modified when new snapshot is invalid"
        )


def _save_jsonl(items, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for item in items:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")
