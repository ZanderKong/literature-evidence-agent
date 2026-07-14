"""Integration tests for package snapshot sync, check, and list."""

import json

import pytest


class TestPackageSnapshot:
    """Source state snapshots must be atomic, complete, and verifiable."""

    @pytest.fixture
    def setup(self, runtime_context):
        """Setup workspace with source, run, claims, locators, review data."""
        from evidence_agent.database.connection import get_connection

        with get_connection() as conn:
            conn.execute(
                "INSERT INTO sources (source_id, source_type, title, "
                "original_file_sha256, origin_scope, "
                "scientific_verification_status, created_at, updated_at) "
                "VALUES ('SRC-ps1', 'journal_article', 'Snapshot Test', "
                "'sha256:ps1', 'external', 'unverified', "
                "'2025-01-01T00:00:00', '2025-01-01T00:00:00')"
            )
            conn.execute(
                "INSERT INTO source_assets (asset_id, source_id, asset_type, "
                "relative_path, mime_type, sha256, file_size, acquired_at) "
                "VALUES ('AST-ps1', 'SRC-ps1', 'main_document', 'test.pdf', "
                "'application/pdf', 'sha:ps1', 1000, '2025-01-01T00:00:00')"
            )
            conn.execute(
                "INSERT INTO processing_runs (run_id, source_id, module_name, "
                "model_name, input_hash, status, started_at) "
                "VALUES ('RUN-ps1', 'SRC-ps1', 'analyse', 'mock', 'hash:ps1', "
                "'completed', '2025-01-01T00:00:00')"
            )
            conn.execute(
                "INSERT INTO source_claims (claim_id, source_id, claim_type, "
                "source_quote, faithful_paraphrase, evidence_basis_description, "
                "origin_scope, record_review_status, scientific_verification_status, "
                "quote_match_status, created_by_run_id, created_at, updated_at) "
                "VALUES ('CLM-ps1', 'SRC-ps1', 'reported_result', "
                "'Snapshot quote', 'Snapshot para', 'Snapshot evidence', "
                "'external', 'pending', 'unverified', "
                "'exact', 'RUN-ps1', '2025-01-01T00:00:00', '2025-01-01T00:00:00')"
            )
            conn.execute(
                "INSERT INTO claim_locators (locator_id, claim_id, page, "
                "locator_confidence) VALUES ('LOC-ps1', 'CLM-ps1', 1, 'high')"
            )

        pkg_dir = runtime_context.sources_dir / "SRC-ps1"
        pkg_dir.mkdir(parents=True, exist_ok=True)
        manifest = {
            "source_id": "SRC-ps1",
            "source_type": "journal_article",
            "title": "Snapshot Test",
            "original_file_sha256": "sha256:ps1",
            "created_at": "2025-01-01T00:00:00",
            "updated_at": "2025-01-01T00:00:00",
        }
        (pkg_dir / "manifest.json").write_text(json.dumps(manifest))

        return runtime_context

    def test_sync_creates_snapshot(self, setup):
        """sync should create a snapshot with manifest and records."""
        from evidence_agent.source_package.snapshot import sync_source

        result = sync_source("SRC-ps1")

        assert result["snapshot_id"].startswith("SNP-")
        assert result["source_id"] == "SRC-ps1"
        assert result["record_counts"]["sources"] == 1
        assert result["record_counts"]["source_assets"] == 1
        assert result["record_counts"]["source_claims"] == 1
        assert result["record_counts"]["claim_locators"] == 1
        assert result["record_counts"]["processing_runs"] == 1

    def test_sync_idempotent(self, setup):
        """Two syncs should create two distinct snapshots."""
        from evidence_agent.source_package.snapshot import sync_source

        r1 = sync_source("SRC-ps1")
        r2 = sync_source("SRC-ps1")

        assert r1["snapshot_id"] != r2["snapshot_id"]
        assert r1["record_counts"] == r2["record_counts"]

    def test_check_valid_snapshot(self, setup):
        """check should pass on a valid snapshot."""
        from evidence_agent.source_package.snapshot import sync_source, check_source

        sync_source("SRC-ps1")
        result = check_source("SRC-ps1")

        assert result["valid"], f"Expected valid, got: {result['errors']}"
        assert result["record_counts"]["sources"] == 1
        assert result["record_counts"]["source_claims"] == 1

    def test_list_shows_snapshots(self, setup):
        """list should show all snapshots for a source."""
        from evidence_agent.source_package.snapshot import sync_source, list_snapshots

        sync_source("SRC-ps1")
        snapshots = list_snapshots("SRC-ps1")

        assert len(snapshots) == 1
        assert snapshots[0]["snapshot_id"].startswith("SNP-")

    def test_check_no_snapshot(self, setup):
        """check should fail when there is no snapshot."""
        from evidence_agent.source_package.snapshot import check_source

        result = check_source("SRC-ps1")

        assert not result["valid"]
        assert any("not found" in e.lower() for e in result["errors"])

    def test_current_json_points_to_latest(self, setup):
        """current.json should point to the latest snapshot."""
        from evidence_agent.source_package.snapshot import sync_source
        from pathlib import Path

        r1 = sync_source("SRC-ps1")
        r2 = sync_source("SRC-ps1")

        pkg_dir = setup.sources_dir / "SRC-ps1"
        current = json.loads((pkg_dir / "state" / "current.json").read_text())

        assert current["snapshot_id"] == r2["snapshot_id"]
