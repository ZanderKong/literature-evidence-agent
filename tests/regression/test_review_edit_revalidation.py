"""Regression tests: review edit revalidation must check all provenance fields.

Current issues:
- Edited quote check is skipped when source_sections is empty
- edited_page is not validated
- edited_section is not validated
- figure_label is not validated for edited claims
- Individual row errors allow partial application (no batch rollback)
"""

import csv
from pathlib import Path

import pytest


class TestReviewEditRevalidation:
    """Review apply must thoroughly validate edited fields."""

    @pytest.fixture
    def setup_db(self, runtime_context):
        """Setup a migrated database with a claim and sections."""
        from evidence_agent.database.connection import get_connection

        with get_connection() as conn:
            conn.execute(
                "INSERT INTO sources (source_id, source_type, title, "
                "original_file_sha256, origin_scope, "
                "scientific_verification_status, created_at, updated_at) "
                "VALUES ('SRC-test', 'journal_article', 'Test', 'sha256:test', "
                "'external', 'unverified', '2025-01-01T00:00:00', '2025-01-01T00:00:00')"
            )

            conn.execute(
                "INSERT INTO source_sections (section_id, source_id, section_type, "
                "heading, page_start, page_end, sequence_number, text, "
                "parser_name, parser_version, text_sha256) "
                "VALUES ('SEC-test', 'SRC-test', 'body', 'Results', 1, 1, 1, "
                "'The tensile strength increased from 250 MPa to 320 MPa after heat treatment. "
                "Figure 2 shows the stress-strain curve.', 'pdfplumber', '1.0', 'sha256:sec')"
            )

            conn.execute(
                "INSERT INTO source_claims (claim_id, source_id, claim_type, "
                "source_quote, faithful_paraphrase, evidence_basis_description, "
                "origin_scope, record_review_status, scientific_verification_status, "
                "quote_match_status, created_by_run_id, created_at, updated_at) "
                "VALUES ('CLM-test', 'SRC-test', 'reported_result', "
                "'strength increased from 250 MPa to 320 MPa', 'strength increase', "
                "'based on tensile test', 'external', 'pending', 'unverified', "
                "'exact', 'RUN-test', '2025-01-01T00:00:00', '2025-01-01T00:00:00')"
            )

            conn.execute(
                "INSERT INTO claim_locators (locator_id, claim_id, section_id, page, "
                "figure_label, locator_confidence) "
                "VALUES ('LOC-test', 'CLM-test', 'SEC-test', 1, 'Figure 2', 'high')"
            )

        return runtime_context

    def _make_csv(self, tmp_path: Path, rows: list[dict]) -> Path:
        csv_path = tmp_path / "review.csv"
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=[
                "claim_id", "decision", "edited_source_quote",
                "edited_faithful_paraphrase", "edited_evidence_basis_description",
                "edited_claim_type", "edited_page", "edited_section",
                "review_reason", "reviewer",
            ])
            w.writeheader()
            for row in rows:
                w.writerow(row)
        return csv_path

    def test_edited_quote_not_found_in_source_should_fail(self, setup_db, tmp_path):
        """An edited quote that doesn't exist anywhere in source_sections must be rejected."""
        from evidence_agent.review.decisions import apply_review_csv

        csv_path = self._make_csv(tmp_path, [
            {
                "claim_id": "CLM-test",
                "decision": "approve_with_edits",
                "edited_source_quote": "This text does not exist anywhere in the source",
                "edited_faithful_paraphrase": "",
                "edited_evidence_basis_description": "",
                "edited_claim_type": "reported_result",
                "edited_page": "",
                "edited_section": "",
                "review_reason": "",
                "reviewer": "tester",
            }
        ])

        report = apply_review_csv(csv_path)

        assert len(report["errors"]) > 0, (
            f"FLAW: edited quote not in source was accepted. "
            f"report={report}"
        )

    def test_edited_page_should_be_validated(self, setup_db, tmp_path):
        """Editing a page that doesn't exist must be caught."""
        from evidence_agent.review.decisions import apply_review_csv

        csv_path = self._make_csv(tmp_path, [
            {
                "claim_id": "CLM-test",
                "decision": "approve_with_edits",
                "edited_source_quote": "strength increased from 250 MPa to 320 MPa",
                "edited_faithful_paraphrase": "",
                "edited_evidence_basis_description": "",
                "edited_claim_type": "reported_result",
                "edited_page": "999",  # Non-existent page
                "edited_section": "",
                "review_reason": "",
                "reviewer": "tester",
            }
        ])

        report = apply_review_csv(csv_path)

        assert len(report["errors"]) > 0 or report["edited"] == 0, (
            f"FLAW: edited page=999 (non-existent) was accepted without error. "
            f"report={report}"
        )

    def test_empty_source_sections_should_fail_edit(self, setup_db, tmp_path):
        """When source_sections is empty, approve_with_edits must FAIL.
        The current code skips validation when section_text is empty."""
        from evidence_agent.database.connection import get_connection

        # Delete all sections to trigger the bypass
        with get_connection() as conn:
            conn.execute("DELETE FROM source_sections")

        from evidence_agent.review.decisions import apply_review_csv

        csv_path = self._make_csv(tmp_path, [
            {
                "claim_id": "CLM-test",
                "decision": "approve_with_edits",
                "edited_source_quote": "any text",
                "edited_faithful_paraphrase": "",
                "edited_evidence_basis_description": "",
                "edited_claim_type": "reported_result",
                "edited_page": "",
                "edited_section": "",
                "review_reason": "",
                "reviewer": "tester",
            }
        ])

        report = apply_review_csv(csv_path)

        # When sections are empty, the current code skips quote validation:
        #   if section_text: ... match_quote ...
        # This means ANY edited quote passes.
        assert len(report["errors"]) > 0, (
            f"FLAW: edit was accepted even though source_sections is empty. "
            f"The current code skips validation when section_text is falsy. "
            f"report={report}"
        )
