"""Integration tests for claim persistence."""

from pathlib import Path

from evidence_agent.application.analyse import _persist_claims
from evidence_agent.database.connection import get_connection
from evidence_agent.ingest.files import import_pdf

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures"


class TestPersistClaims:
    """Test that claims are correctly written to database."""

    def test_persist_validated_claims(self, migrated_workspace):
        """Persist claims and verify they appear in the database."""
        # Import a source first
        pdf_path = FIXTURES_DIR / "sample_article.pdf"
        result = import_pdf(pdf_path)
        source_id = result["source_id"]

        run_id = "RUN-TEST-PERSIST"
        claims = [
            {
                "claim_type": "reported_result",
                "source_quote": "The solubility increased from 1.0 to 5.2 mg/mL.",
                "faithful_paraphrase": "溶解度从 1.0 增加到 5.2 mg/mL。",
                "evidence_basis_description": "Based on Figure 1.",
                "scope_description": None,
                "author_hedging": None,
                "locator_hint": {"page": 1, "figure_label": "Figure 1"},
                "_quote_match_status": "exact",
                "_block_page_start": 1,
            },
            {
                "claim_type": "author_interpretation",
                "source_quote": "This suggests hydrogen bonding plays a key role.",
                "faithful_paraphrase": "作者认为氢键起关键作用。",
                "evidence_basis_description": "Based on FT-IR data.",
                "scope_description": None,
                "author_hedging": "suggests",
                "locator_hint": {"page": 2},
                "_quote_match_status": "exact",
                "_block_page_start": 2,
            },
            {
                "claim_type": "reported_result",
                "source_quote": "This quote was not found in the source.",
                "faithful_paraphrase": "转述",
                "evidence_basis_description": "basis",
                "locator_hint": {"page": 1},
                "_quote_match_status": "not_found",
                "_block_page_start": 1,
            },
        ]

        count = _persist_claims(claims, source_id, None, run_id)
        assert count == 2  # Only exact/normalised persisted

        # Verify in database
        with get_connection(read_only=True) as conn:
            cursor = conn.execute(
                "SELECT COUNT(*) FROM source_claims WHERE source_id = ?",
                (source_id,),
            )
            assert cursor.fetchone()[0] == 2

            cursor = conn.execute(
                "SELECT COUNT(*) FROM claim_locators"
            )
            assert cursor.fetchone()[0] == 2

            # Check review status is pending
            cursor = conn.execute(
                "SELECT DISTINCT record_review_status FROM source_claims"
            )
            statuses = {row[0] for row in cursor.fetchall()}
            assert statuses == {"pending"}

    def test_empty_claims(self, migrated_workspace):
        pdf_path = FIXTURES_DIR / "sample_article.pdf"
        result = import_pdf(pdf_path)
        count = _persist_claims([], result["source_id"], None, "RUN-EMPTY")
        assert count == 0
