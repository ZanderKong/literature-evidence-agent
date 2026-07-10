"""Integration tests: review batches must be tracked in the database.

Current implementation:
- generate_review_packet() reads claims and writes files
- But there is NO review_batches table, NO batch rows
- No dedup by content hash
- No tracking of which batch a decision belongs to
"""

import json

import pytest


class TestReviewBatches:
    """Review batches must be created and tracked with stable hashes."""

    @pytest.fixture
    def setup(self, runtime_context):
        """Setup workspace with a source, run, and pending claims."""
        from evidence_agent.database.connection import get_connection

        with get_connection() as conn:
            conn.execute(
                "INSERT INTO sources (source_id, source_type, title, "
                "original_file_sha256, origin_scope, "
                "scientific_verification_status, created_at, updated_at) "
                "VALUES ('SRC-rb1', 'journal_article', 'Review Batch Test', "
                "'sha256:rb1', 'external', 'unverified', "
                "'2025-01-01T00:00:00', '2025-01-01T00:00:00')"
            )
            conn.execute(
                "INSERT INTO processing_runs (run_id, source_id, module_name, "
                "model_name, input_hash, status, started_at) "
                "VALUES ('RUN-rb1', 'SRC-rb1', 'analyse', 'mock', 'hash:rb1', "
                "'completed', '2025-01-01T00:00:00')"
            )
            conn.execute(
                "INSERT INTO source_claims (claim_id, source_id, claim_type, "
                "source_quote, faithful_paraphrase, evidence_basis_description, "
                "origin_scope, record_review_status, scientific_verification_status, "
                "quote_match_status, created_by_run_id, created_at, updated_at) "
                "VALUES ('CLM-rb1', 'SRC-rb1', 'reported_result', "
                "'Test quote one', 'Para one', 'Evidence one', "
                "'external', 'pending', 'unverified', "
                "'exact', 'RUN-rb1', '2025-01-01T00:00:00', '2025-01-01T00:00:00')"
            )
            conn.execute(
                "INSERT INTO claim_locators (locator_id, claim_id, page, "
                "locator_confidence) VALUES ('LOC-rb1', 'CLM-rb1', 1, 'high')"
            )
            conn.execute(
                "INSERT INTO source_claims (claim_id, source_id, claim_type, "
                "source_quote, faithful_paraphrase, evidence_basis_description, "
                "origin_scope, record_review_status, scientific_verification_status, "
                "quote_match_status, created_by_run_id, created_at, updated_at) "
                "VALUES ('CLM-rb2', 'SRC-rb1', 'author_interpretation', "
                "'Test quote two', 'Para two', 'Evidence two', "
                "'external', 'pending', 'unverified', "
                "'exact', 'RUN-rb1', '2025-01-01T00:00:00', '2025-01-01T00:00:00')"
            )
            conn.execute(
                "INSERT INTO claim_locators (locator_id, claim_id, page, "
                "locator_confidence) VALUES ('LOC-rb2', 'CLM-rb2', 1, 'high')"
            )

        return runtime_context

    def test_review_export_generates_packet(self, setup):
        """Review export should generate a packet with the correct number of rows."""
        from evidence_agent.review.packet import generate_review_packet

        paths = generate_review_packet("RUN-rb1")

        csv_path = paths["csv"]
        import csv
        with open(csv_path, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        assert len(rows) == 2, (
            f"Expected 2 pending claims for RUN-rb1, got {len(rows)}"
        )

    def test_review_batches_table_missing(self, setup):
        """The review_batches table should exist in the schema.
        Currently it does NOT exist — this test captures the gap."""
        from evidence_agent.database.connection import get_connection

        with get_connection(read_only=True) as conn:
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' "
                "AND name='review_batches'"
            )
            exists = cursor.fetchone()

        assert exists is not None, (
            "FLAW: review_batches table does not exist. "
            "Current schema has no batch tracking."
        )

    def test_review_export_does_not_create_batch_records(self, setup):
        """After review export, there should be batch records in DB.
        Currently there are none."""
        from evidence_agent.review.packet import generate_review_packet
        from evidence_agent.database.connection import get_connection

        generate_review_packet("RUN-rb1")

        with get_connection(read_only=True) as conn:
            try:
                cursor = conn.execute("SELECT COUNT(*) as cnt FROM review_batches")
                count = cursor.fetchone()["cnt"]
            except Exception:
                count = -1

        assert count > 0, (
            f"FLAW: review export generated files but created {count} batch records. "
            f"generate_review_packet() does not insert into review_batches table."
        )
