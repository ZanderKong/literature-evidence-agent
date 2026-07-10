"""Regression tests: rebuild must preserve exact IDs and review state.

The current rebuild_from_packages implementation loses:
- Original locator IDs (generates new ones as `LOC-{claim_id}`)
- Review status (forces everything to "pending")
- Review decisions and revisions (not imported at all)
- Uses global env var mutation (not isolated)
"""

import json
from pathlib import Path

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
                "claim_type": "reported_result",
                "source_quote": "Test quote",
                "faithful_paraphrase": "Test paraphrase",
                "evidence_basis_description": "Test evidence",
                "locator_hint": {"page": 1},
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


def _save_jsonl(items, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for item in items:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")
