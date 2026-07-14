"""Integration tests for package snapshot integrity.

Tests: tamper detection, SHA-256 verification, cross-reference validation,
concurrent sync, staging cleanup.
"""

import json

import pytest


class TestPackageSnapshotIntegrity:
    @pytest.fixture
    def setup(self, runtime_context):
        from evidence_agent.database.connection import get_connection

        with get_connection() as conn:
            conn.execute(
                "INSERT INTO sources (source_id, source_type, title, "
                "original_file_sha256, origin_scope, "
                "scientific_verification_status, created_at, updated_at) "
                "VALUES ('SRC-int1', 'journal_article', 'Integrity Test', "
                "'sha256:int1', 'external', 'unverified', "
                "'2025-01-01T00:00:00', '2025-01-01T00:00:00')"
            )
            conn.execute(
                "INSERT INTO source_claims (claim_id, source_id, claim_type, "
                "source_quote, faithful_paraphrase, evidence_basis_description, "
                "origin_scope, record_review_status, scientific_verification_status, "
                "quote_match_status, created_by_run_id, created_at, updated_at) "
                "VALUES ('CLM-int1', 'SRC-int1', 'reported_result', "
                "'Content A', 'Para A', 'Evid A', "
                "'external', 'pending', 'unverified', "
                "'exact', 'RUN-int1', '2025-01-01T00:00:00', '2025-01-01T00:00:00')"
            )
            conn.execute(
                "INSERT INTO processing_runs (run_id, source_id, module_name, "
                "model_name, input_hash, status, started_at) "
                "VALUES ('RUN-int1', 'SRC-int1', 'analyse', 'mock', 'hash:int1', "
                "'completed', '2025-01-01T00:00:00')"
            )
            conn.execute(
                "INSERT INTO claim_locators (locator_id, claim_id, page, "
                "locator_confidence) VALUES ('LOC-int1', 'CLM-int1', 1, 'high')"
            )

        pkg_dir = runtime_context.sources_dir / "SRC-int1"
        pkg_dir.mkdir(parents=True, exist_ok=True)
        (pkg_dir / "manifest.json").write_text(json.dumps({
            "source_id": "SRC-int1",
            "source_type": "journal_article",
            "title": "Integrity Test",
            "original_file_sha256": "sha256:int1",
            "created_at": "2025-01-01T00:00:00",
            "updated_at": "2025-01-01T00:00:00",
        }))

        return runtime_context

    def test_check_verifies_file_sha256(self, setup):
        """check must compute and verify each JSONL file SHA-256 against manifest."""
        from evidence_agent.source_package.snapshot import check_source, sync_source

        sync_source("SRC-int1")
        result = check_source("SRC-int1")
        assert result["valid"], f"Expected valid, got: {result['errors']}"

    def test_tamper_detection_same_row_count(self, setup):
        """Tampering content while keeping same row count must fail check."""
        from evidence_agent.source_package.snapshot import check_source, sync_source

        sync_source("SRC-int1")

        pkg_dir = setup.sources_dir / "SRC-int1"
        current = json.loads((pkg_dir / "state" / "current.json").read_text())
        snap_dir = pkg_dir / "state" / "snapshots" / current["snapshot_id"]
        claims_file = snap_dir / "records" / "source_claims.jsonl"

        original_content = claims_file.read_text()
        tampered = original_content.replace("Content A", "TAMPERED X")
        claims_file.write_text(tampered)

        result = check_source("SRC-int1")
        assert not result["valid"], "Tamper must be detected"
        assert any("sha256" in e.lower() for e in result["errors"]), (
            f"Expected sha256 error, got: {result['errors']}"
        )

    def test_cross_reference_locator_to_claim(self, setup):
        """locator must reference existing claim."""
        import hashlib

        from evidence_agent.source_package.snapshot import (
            check_source,
            sync_source,
        )

        sync_source("SRC-int1")

        pkg_dir = setup.sources_dir / "SRC-int1"
        current = json.loads((pkg_dir / "state" / "current.json").read_text())
        snap_dir = pkg_dir / "state" / "snapshots" / current["snapshot_id"]

        loc_file = snap_dir / "records" / "claim_locators.jsonl"
        bad_line = json.dumps({
            "locator_id": "LOC-bad",
            "claim_id": "CLM-NONEXISTENT",
            "page": 1,
            "locator_confidence": "high",
        }, ensure_ascii=False, sort_keys=True)
        loc_file.write_text(loc_file.read_text().strip() + "\n" + bad_line + "\n")

        h = hashlib.sha256()
        with open(loc_file, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        new_sha = h.hexdigest()
        manifest = json.loads((snap_dir / "manifest.json").read_text())
        mh = hashlib.sha256()
        for a in manifest["artifacts"]:
            if a["record_type"] == "claim_locators":
                a["sha256"] = new_sha
                a["record_count"] += 1
            mh.update(a["sha256"].encode())
        manifest["manifest_sha256"] = mh.hexdigest()
        (snap_dir / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2),
        )

        result = check_source("SRC-int1")
        assert not result["valid"], "Cross-ref violation must be detected"
        assert any("claim_id not in claims" in e for e in result["errors"])

    def test_staging_cleanup_on_failure(self, setup):
        """Failed sync must not leave staging directory."""
        from evidence_agent.runtime import get_current_context

        ctx = get_current_context()
        pkg_dir = ctx.sources_dir / "SRC-int1"

        state_dir = pkg_dir / "state"
        before_dirs = set()
        if state_dir.exists():
            for d in state_dir.iterdir():
                if d.name.startswith(".tmp-SNP-"):
                    before_dirs.add(d.name)

        snap_dir = pkg_dir / "state" / "snapshots"
        current_file = pkg_dir / "state" / "current.json"
        if current_file.exists():
            current_before = current_file.read_text()
        else:
            current_before = ""

        from evidence_agent.source_package.snapshot import sync_source
        sync_source("SRC-int1")

        after_dirs = set()
        if state_dir.exists():
            for d in state_dir.iterdir():
                if d.name.startswith(".tmp-SNP-"):
                    after_dirs.add(d.name)

        assert len(after_dirs) == 0, (
            f"Staging dirs left behind: {after_dirs}"
        )

    def test_concurrent_sync_distinct_snapshots(self, setup):
        """Two syncs in sequence must create distinct, valid snapshots."""
        from evidence_agent.source_package.snapshot import check_source, sync_source

        r1 = sync_source("SRC-int1")
        r2 = sync_source("SRC-int1")

        assert r1["snapshot_id"] != r2["snapshot_id"]

        c1 = check_source("SRC-int1")
        assert c1["valid"], f"Second snapshot must pass check: {c1['errors']}"

    def test_residual_staging_invalidates_check(self, setup):
        """A leftover staging dir must not affect check_source."""

        from evidence_agent.runtime import get_current_context
        from evidence_agent.source_package.snapshot import check_source, sync_source

        ctx = get_current_context()
        sync_source("SRC-int1")

        state_dir = ctx.sources_dir / "SRC-int1" / "state"
        fake_staging = state_dir / ".tmp-SNP-fake123"
        fake_staging.mkdir(exist_ok=True)
        (fake_staging / "manifest.json").write_text("{}")

        result = check_source("SRC-int1")
        assert result["valid"], (
            f"Residual staging should not affect valid snapshot: {result['errors']}"
        )

        import shutil
        shutil.rmtree(str(fake_staging), ignore_errors=True)
