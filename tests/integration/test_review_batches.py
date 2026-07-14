"""Integration tests: review batches with stable identities.

Batch identity is determined by (run_id, packet_sha256).
Same claims content → same batch/row IDs (idempotent).
Different claims content → new batch.
"""

import csv
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

        with open(paths["csv"], encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        assert len(rows) == 2, (
            f"Expected 2 pending claims for RUN-rb1, got {len(rows)}"
        )

    def test_review_batches_table_exists(self, setup):
        """The review_batches table should exist in the schema."""
        from evidence_agent.database.connection import get_connection

        with get_connection(read_only=True) as conn:
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' "
                "AND name='review_batches'"
            )
            exists = cursor.fetchone()

        assert exists is not None, (
            "FLAW: review_batches table does not exist."
        )

    def test_export_creates_batch_records(self, setup):
        """After review export, there should be batch records in DB."""
        from evidence_agent.database.connection import get_connection
        from evidence_agent.review.packet import generate_review_packet

        generate_review_packet("RUN-rb1")

        with get_connection(read_only=True) as conn:
            cursor = conn.execute("SELECT COUNT(*) as cnt FROM review_batches")
            count = cursor.fetchone()["cnt"]

        assert count > 0, (
            f"FLAW: export generated files but created {count} batch records."
        )

    def test_same_packet_reuses_batch_id(self, setup):
        """Same claims content should reuse the same review_batch_id."""
        from evidence_agent.database.connection import get_connection
        from evidence_agent.review.packet import generate_review_packet

        paths1 = generate_review_packet("RUN-rb1")
        paths2 = generate_review_packet("RUN-rb1")

        assert paths1["batch_id"] == paths2["batch_id"], (
            f"Expected same batch_id for identical content. "
            f"Got {paths1['batch_id']} vs {paths2['batch_id']}"
        )
        assert paths1["packet_sha256"] == paths2["packet_sha256"]

        with get_connection(read_only=True) as conn:
            cursor = conn.execute(
                "SELECT COUNT(*) as cnt FROM review_batches"
            )
            cnt = cursor.fetchone()["cnt"]
        assert cnt == 1, f"Expected 1 batch, found {cnt}"

    def test_same_packet_reuses_row_ids(self, setup):
        """Same claims content should reuse the same review_row_ids."""
        from evidence_agent.review.packet import generate_review_packet

        paths1 = generate_review_packet("RUN-rb1")
        paths2 = generate_review_packet("RUN-rb1")

        # Read CSV to extract row IDs
        def read_csv_batch_info(csv_path):
            with open(csv_path, encoding="utf-8") as f:
                reader = csv.DictReader(f)
                return [(r["claim_id"], r["review_row_id"]) for r in reader]

        rows1 = read_csv_batch_info(paths1["csv"])
        rows2 = read_csv_batch_info(paths2["csv"])

        assert rows1 == rows2, (
            f"Expected same row IDs for identical content. "
            f"Got {rows1} vs {rows2}"
        )

    def test_changed_claim_creates_new_batch(self, setup):
        """Different claims content should create a new batch."""
        from evidence_agent.database.connection import get_connection
        from evidence_agent.review.packet import generate_review_packet

        paths1 = generate_review_packet("RUN-rb1")

        # Change one claim's paraphrase
        with get_connection() as conn:
            conn.execute(
                "UPDATE source_claims SET faithful_paraphrase = 'Changed paraphrase' "
                "WHERE claim_id = 'CLM-rb1'"
            )

        paths2 = generate_review_packet("RUN-rb1")

        assert paths1["batch_id"] != paths2["batch_id"], (
            "Expected different batch_id when claim content changes"
        )
        assert paths1["packet_sha256"] != paths2["packet_sha256"]

    def test_packet_order_is_deterministic(self, setup):
        """Rows in the packet should be deterministically ordered."""
        from evidence_agent.review.packet import generate_review_packet

        paths1 = generate_review_packet("RUN-rb1")
        paths2 = generate_review_packet("RUN-rb1")

        with open(paths1["csv"], encoding="utf-8") as f:
            rows1 = list(csv.DictReader(f))
        with open(paths2["csv"], encoding="utf-8") as f:
            rows2 = list(csv.DictReader(f))

        ids1 = [r["claim_id"] for r in rows1]
        ids2 = [r["claim_id"] for r in rows2]
        assert ids1 == ids2, (
            f"Row order must be deterministic. Got {ids1} vs {ids2}"
        )

    def test_csv_contains_batch_row_hashes(self, setup):
        """CSV must include review_batch_id, review_row_id, and hashes."""
        from evidence_agent.review.packet import generate_review_packet

        paths = generate_review_packet("RUN-rb1")

        with open(paths["csv"], encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        for row in rows:
            assert row.get("review_batch_id"), "Missing review_batch_id in CSV row"
            assert row.get("review_row_id"), "Missing review_row_id in CSV row"
            assert row.get("row_input_sha256"), "Missing row_input_sha256"
            assert row.get("packet_sha256"), "Missing packet_sha256"
            assert row.get("run_id"), "Missing run_id"

    def test_decision_batch_row_unique_constraint(self, setup):
        """UNIQUE(review_batch_id, review_row_id) should be in place."""
        from evidence_agent.database.connection import get_connection

        with get_connection(read_only=True) as conn:
            cursor = conn.execute(
                "SELECT sql FROM sqlite_master WHERE type='index' "
                "AND name='idx_review_decisions_batch_row'"
            )
            idx = cursor.fetchone()

        assert idx is not None, (
            "FLAW: idx_review_decisions_batch_row index not found. "
            "Missing migration 005_or equivalent."
        )

    def test_jsonl_contains_batch_info(self, setup):
        """JSONL rows should include batch and row IDs."""
        from evidence_agent.review.packet import generate_review_packet

        paths = generate_review_packet("RUN-rb1")

        with open(paths["jsonl"], encoding="utf-8") as f:
            for line in f:
                row = json.loads(line)
                assert "review_batch_id" in row, "JSONL row missing review_batch_id"
                assert "review_row_id" in row, "JSONL row missing review_row_id"
                assert "row_input_sha256" in row
                assert "packet_sha256" in row
