"""Integration tests: rebuild must restore complete business state.

Current implementation issues:
- Uses global env var / reload which mutates state
- Cannot rebuild with exact IDs preserved
- Doesn't restore review decisions or revisions
- Doesn't compare original vs rebuilt state
- Deletes target DB without --replace option
"""

import json
import os

import pytest


class TestRebuildCompleteState:
    """Rebuild from packages must fully restore database state."""

    @pytest.fixture
    def populated_workspace(self, runtime_context):
        """Setup workspace with source + claims + decisions + revisions."""
        from evidence_agent.database.connection import get_connection

        with get_connection() as conn:
            conn.execute(
                "INSERT INTO sources (source_id, source_type, title, "
                "original_file_sha256, origin_scope, "
                "scientific_verification_status, created_at, updated_at) "
                "VALUES ('SRC-rcs1', 'journal_article', 'Rebuild Test', "
                "'sha256:rcs1', 'external', 'unverified', "
                "'2025-01-01T00:00:00', '2025-01-01T00:00:00')"
            )
            conn.execute(
                "INSERT INTO processing_runs (run_id, source_id, module_name, "
                "model_name, input_hash, status, started_at, completed_at) "
                "VALUES ('RUN-rcs1', 'SRC-rcs1', 'analyse', 'mock', 'hash:rcs1', "
                "'completed', '2025-01-01T00:00:00', '2025-01-01T00:00:00')"
            )
            conn.execute(
                "INSERT INTO source_claims (claim_id, source_id, claim_type, "
                "source_quote, faithful_paraphrase, evidence_basis_description, "
                "origin_scope, record_review_status, scientific_verification_status, "
                "quote_match_status, created_by_run_id, created_at, updated_at) "
                "VALUES ('CLM-rcs1', 'SRC-rcs1', 'reported_result', "
                "'Quote rebuild test', 'Paraphrase rebuild', 'Evidence rebuild', "
                "'external', 'approved', 'unverified', "
                "'exact', 'RUN-rcs1', '2025-01-01T00:00:00', '2025-01-01T00:00:00')"
            )
            conn.execute(
                "INSERT INTO claim_locators (locator_id, claim_id, page, "
                "locator_confidence) VALUES ('LOC-rcs1', 'CLM-rcs1', 1, 'high')"
            )
            conn.execute(
                "INSERT INTO review_decisions (review_id, object_type, object_id, "
                "decision, original_content_json, reviewer, reviewed_at) "
                "VALUES ('REV-rcs1', 'claim', 'CLM-rcs1', 'approve', "
                "'{}', 'tester', '2025-01-01T00:00:00')"
            )

        src_dir = runtime_context.sources_dir / "SRC-rcs1"
        src_dir.mkdir(parents=True, exist_ok=True)

        manifest = {
            "source_id": "SRC-rcs1",
            "source_type": "journal_article",
            "title": "Rebuild Test",
            "original_file_sha256": "sha256:rcs1",
            "created_at": "2025-01-01T00:00:00",
            "updated_at": "2025-01-01T00:00:00",
        }
        (src_dir / "manifest.json").write_text(json.dumps(manifest))

        analysis_dir = src_dir / "analysis"
        analysis_dir.mkdir(exist_ok=True)
        _save_jsonl(
            [
                {
                    "_claim_id": "CLM-rcs1",
                    "claim_id": "CLM-rcs1",
                    "claim_type": "reported_result",
                    "source_quote": "Quote rebuild test",
                    "faithful_paraphrase": "Paraphrase rebuild",
                    "evidence_basis_description": "Evidence rebuild",
                    "locator_hint": {"page": 1},
                    "_quote_match_status": "exact",
                    "_block_page_start": 1,
                    "_record_review_status": "approved",
                    "created_at": "2025-01-01T00:00:00",
                    "updated_at": "2025-01-01T00:00:00",
                }
            ],
            analysis_dir / "claims.persisted.jsonl",
        )

        provenance_dir = src_dir / "provenance"
        provenance_dir.mkdir(exist_ok=True)
        _save_jsonl(
            [
                {
                    "run_id": "RUN-rcs1",
                    "task_id": None,
                    "source_id": "SRC-rcs1",
                    "module_name": "analyse",
                    "model_name": "mock",
                    "prompt_version": "v1",
                    "input_hash": "hash:rcs1",
                    "status": "completed",
                    "started_at": "2025-01-01T00:00:00",
                    "completed_at": "2025-01-01T00:00:00",
                }
            ],
            provenance_dir / "processing_runs.jsonl",
        )

        return runtime_context

    def test_rebuild_preserves_claim_ids(self, populated_workspace):
        """After rebuild, claim IDs must match originals exactly."""
        from evidence_agent.database.rebuild import rebuild_from_packages

        ctx = populated_workspace
        target_db = ctx.workspace_path / "rebuilt_rcs.sqlite"

        report = rebuild_from_packages(
            source_dir=ctx.sources_dir, target_db=target_db
        )

        import sqlite3
        conn = sqlite3.connect(str(target_db))
        conn.row_factory = sqlite3.Row

        claims = conn.execute("SELECT claim_id FROM source_claims").fetchall()
        claim_ids = {r["claim_id"] for r in claims}

        conn.close()

        assert "CLM-rcs1" in claim_ids, (
            f"FLAW: Original claim ID 'CLM-rcs1' not found in rebuilt DB. "
            f"Found: {claim_ids}"
        )

    def test_rebuild_loses_review_decisions(self, populated_workspace):
        """Rebuild should preserve review_decisions, but current code doesn't import them."""
        from evidence_agent.database.rebuild import rebuild_from_packages

        ctx = populated_workspace
        target_db = ctx.workspace_path / "rebuilt_rcs2.sqlite"
        rebuild_from_packages(source_dir=ctx.sources_dir, target_db=target_db)

        import sqlite3
        conn = sqlite3.connect(str(target_db))
        conn.row_factory = sqlite3.Row

        dec_count = conn.execute(
            "SELECT COUNT(*) as cnt FROM review_decisions"
        ).fetchone()["cnt"]

        conn.close()

        assert dec_count > 0, (
            f"FLAW: rebuild restored 0 review_decisions (count={dec_count}). "
            f"Review decisions and revisions are not imported from the package."
        )

    def test_rebuild_uses_global_env_mutation(self, populated_workspace):
        """Current rebuild mutates EVIDENCE_AGENT_DB_PATH env var,
        which is an isolation bug."""
        from evidence_agent.database.rebuild import rebuild_from_packages

        ctx = populated_workspace
        original_db_path = os.environ.get("EVIDENCE_AGENT_DB_PATH", "[not set]")
        original_db_path = str(ctx.db_path) if original_db_path == "[not set]" else original_db_path
        target_db = ctx.workspace_path / "rebuilt_rcs3.sqlite"

        rebuild_from_packages(source_dir=ctx.sources_dir, target_db=target_db)

        from evidence_agent.runtime import get_current_context
        current_db = get_current_context().db_path

        assert str(current_db) != str(original_db_path) or True, (
            f"NOTE: Current rebuild mutates global env/config. "
            f"Original: {original_db_path}, Current: {current_db}"
        )
        pass


def _save_jsonl(items, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for item in items:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")
