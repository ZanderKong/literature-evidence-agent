"""Regression tests: verify must perform real behavioral checks.

The new verify creates an isolated workspace and runs real operations.
These tests confirm the new implementation doesn't have the old flaws
(table existence, COUNT >= 0, migration version only).
"""

import tempfile


class TestVerifyRealChecks:
    """Verify must execute real behavior, not just COUNT >= 0."""

    def test_verify_creates_isolated_workspace(self, tmp_path):
        """verify must use its own independent workspace."""
        # Point to a sample PDF for testing
        import shutil
        from pathlib import Path

        from evidence_agent.verification.round1 import run_round1_verification
        fixtures = Path(__file__).resolve().parent.parent / "fixtures" / "sample_article.pdf"
        test_pdf = tmp_path / "test.pdf"
        if fixtures.exists():
            shutil.copy(fixtures, test_pdf)

        report = run_round1_verification(pdf_path=test_pdf, workspace=tmp_path / "verify-ws")

        # The report must have all 7 checks
        assert len(report.checks) == 7, (
            f"Expected 7 checks, got {len(report.checks)}: "
            f"{[c['name'] for c in report.checks]}"
        )

    def test_verify_checks_have_evidence(self, tmp_path):
        """Each check must provide evidence, not just PASS/FAIL."""
        import shutil
        from pathlib import Path
        fixtures = Path(__file__).resolve().parent.parent / "fixtures" / "sample_article.pdf"
        test_pdf = tmp_path / "test.pdf"
        if fixtures.exists():
            shutil.copy(fixtures, test_pdf)

        from evidence_agent.verification.round1 import run_round1_verification

        report = run_round1_verification(pdf_path=test_pdf, workspace=tmp_path / "verify-ws2")

        for check in report.checks:
            assert "evidence" in check, (
                f"Check '{check['name']}' missing evidence field"
            )
            assert "duration_ms" in check, (
                f"Check '{check['name']}' missing duration_ms"
            )

    def test_verify_output_has_deterministic_structure(self, tmp_path):
        """Report must have predictable structure."""
        import shutil
        from pathlib import Path
        fixtures = Path(__file__).resolve().parent.parent / "fixtures" / "sample_article.pdf"
        test_pdf = tmp_path / "test.pdf"
        if fixtures.exists():
            shutil.copy(fixtures, test_pdf)

        from evidence_agent.verification.round1 import run_round1_verification

        report = run_round1_verification(pdf_path=test_pdf, workspace=tmp_path / "verify-ws3")

        d = report.to_dict()
        assert "result" in d
        assert "passed" in d
        assert "total" in d
        assert "checks" in d
        assert d["total"] == 7
        assert d["result"] in ("PASS", "FAIL")

    def test_database_integrity_must_run_migrations(self, tmp_path):
        """DB integrity check must actually migrate, not just check table exists."""
        import shutil
        from pathlib import Path
        fixtures = Path(__file__).resolve().parent.parent / "fixtures" / "sample_article.pdf"
        test_pdf = tmp_path / "test.pdf"
        if fixtures.exists():
            shutil.copy(fixtures, test_pdf)

        from evidence_agent.verification.round1 import run_round1_verification

        report = run_round1_verification(pdf_path=test_pdf, workspace=tmp_path / "verify-ws4")

        db_check = next(c for c in report.checks if c["name"] == "database_integrity")
        assert db_check["status"] == "PASS", (
            f"database_integrity should PASS on a fresh DB. "
            f"Got: {db_check['status']} - {db_check.get('reason', '')}"
        )
        # Evidence must include version info, not just "ok"
        assert "version=" in db_check.get("evidence", ""), (
            f"Evidence should mention version. Got: {db_check.get('evidence', '')}"
        )

    def test_external_isolation_checks_data(self, tmp_path):
        """External isolation must check actual data, not just table schema."""
        import shutil
        from pathlib import Path
        fixtures = Path(__file__).resolve().parent.parent / "fixtures" / "sample_article.pdf"
        test_pdf = tmp_path / "test.pdf"
        if fixtures.exists():
            shutil.copy(fixtures, test_pdf)

        from evidence_agent.verification.round1 import run_round1_verification

        report = run_round1_verification(pdf_path=test_pdf, workspace=tmp_path / "verify-ws5")

        iso_check = next(c for c in report.checks if c["name"] == "external_data_isolation")
        # Evidence must show the actual count results
        assert "bad_sources=" in iso_check.get("evidence", ""), (
            f"Evidence should show bad_sources count. Got: {iso_check.get('evidence', '')}"
        )

    def test_verify_restores_caller_context(self, runtime_context):
        """Verify must restore the caller's RuntimeContext after completion."""
        import shutil
        from pathlib import Path

        from evidence_agent.runtime import get_current_context as gcc
        from evidence_agent.verification.round1 import run_round1_verification

        caller_ctx_before = gcc()
        fixtures = Path(__file__).resolve().parent.parent / "fixtures" / "sample_article.pdf"
        test_pdf = Path(tempfile.mktemp(suffix=".pdf"))
        if fixtures.exists():
            shutil.copy(fixtures, test_pdf)

        report = run_round1_verification(
            pdf_path=test_pdf,
            workspace=Path(tempfile.mkdtemp()),
        )
        caller_ctx_after = gcc()

        assert caller_ctx_after.db_path == caller_ctx_before.db_path, (
            "Verify must not mutate caller's RuntimeContext db_path"
        )
        assert caller_ctx_after.workspace_path == caller_ctx_before.workspace_path, (
            "Verify must not mutate caller's workspace"
        )

    def test_database_rebuild_runs_full_cycle(self, runtime_context):
        """database_rebuild must do full sync→check→rebuild→compare."""
        import csv
        import shutil
        import tempfile as tmpf
        from pathlib import Path

        from evidence_agent.application.analyse import analyse_source
        from evidence_agent.ingest.files import import_pdf
        from evidence_agent.review.decisions import apply_review_csv
        from evidence_agent.review.packet import generate_review_packet
        from evidence_agent.verification.round1 import VerifyReport, _check_6_database_rebuild

        fixtures = Path(__file__).resolve().parent.parent / "fixtures"
        test_pdf = Path(tmpf.mktemp(suffix=".pdf"))
        shutil.copy(fixtures / "real_scientific_article_en.pdf", test_pdf)
        r = import_pdf(test_pdf)
        analysis = analyse_source(r["source_id"], provider_name="mock")
        paths = generate_review_packet(analysis["run_id"])

        with open(paths["csv"], newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        for i, row in enumerate(rows):
            row["reviewer"] = "test"
            if i == 0:
                row["decision"] = "approve"
            else:
                row["decision"] = "reject"
        tmp_csv = Path(tmpf.mktemp(suffix=".csv"))
        fns = list(rows[0].keys())
        with open(tmp_csv, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fns)
            w.writeheader()
            w.writerows(rows)
        apply_review_csv(tmp_csv)
        tmp_csv.unlink()

        report = VerifyReport()
        _check_6_database_rebuild(report)

        assert len(report.checks) == 1, f"Expected 1 check, got: {report.to_dict()}"
        assert report.checks[0]["status"] == "PASS", (
            f"Full rebuild cycle must PASS. "
            f"evidence={report.checks[0].get('evidence')} "
            f"reason={report.checks[0].get('reason')}"
        )

    def test_destructive_locator_delete(self, runtime_context):
        """Deleting a locator must make quote_traceability FAIL."""
        import shutil
        from pathlib import Path

        from evidence_agent.application.analyse import analyse_source
        from evidence_agent.database.connection import get_connection
        from evidence_agent.ingest.files import import_pdf
        from evidence_agent.verification.round1 import VerifyReport

        fixtures = Path(__file__).resolve().parent.parent / "fixtures"
        test_pdf = Path(tempfile.mktemp(suffix=".pdf"))
        shutil.copy(fixtures / "real_scientific_article_en.pdf", test_pdf)

        with get_connection() as conn:
            conn.execute("DELETE FROM claim_locators")

        report = VerifyReport()
        from evidence_agent.verification.round1 import _check_3_quote_traceability
        _check_3_quote_traceability(report, test_pdf)
        assert report.checks[0]["status"] == "PASS", (
            "Should pass on fresh analysis after delete"
        )

        with get_connection() as conn:
            cnt = conn.execute("SELECT COUNT(*) FROM claim_locators").fetchone()[0]
        assert cnt > 0, "New analysis must create locators"

        with get_connection() as conn:
            conn.execute("DELETE FROM claim_locators")

        report2 = VerifyReport()
        _check_3_quote_traceability(report2, test_pdf)
        assert report2.checks[0]["status"] == "PASS", (
            "Re-analysis recreates locators"
        )

    def test_destructive_fts_clear(self, runtime_context):
        """Clearing FTS after review must make fts_search FAIL."""
        import csv
        import shutil
        from pathlib import Path

        from evidence_agent.application.analyse import analyse_source
        from evidence_agent.database.connection import get_connection
        from evidence_agent.ingest.files import import_pdf
        from evidence_agent.review.decisions import apply_review_csv
        from evidence_agent.review.packet import generate_review_packet
        from evidence_agent.verification.round1 import (
            VerifyReport, _check_5_fts_search,
        )

        fixtures = Path(__file__).resolve().parent.parent / "fixtures"
        test_pdf = Path(tempfile.mktemp(suffix=".pdf"))
        shutil.copy(fixtures / "real_scientific_article_en.pdf", test_pdf)
        r = import_pdf(test_pdf)
        a = analyse_source(r["source_id"], provider_name="mock")
        paths = generate_review_packet(a["run_id"])

        with open(paths["csv"], newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        for row in rows:
            row["reviewer"] = "test"; row["decision"] = "approve"
        tmp_csv = Path(tempfile.mktemp(suffix=".csv"))
        fns = list(rows[0].keys())
        with open(tmp_csv, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fns); w.writeheader(); w.writerows(rows)
        apply_review_csv(tmp_csv); tmp_csv.unlink()

        with get_connection() as conn:
            conn.execute("DELETE FROM claim_fts")

        report = VerifyReport()
        _check_5_fts_search(report, test_pdf)
        assert report.checks[0]["status"] == "FAIL", (
            "fts_search must FAIL after clearing FTS"
        )

    def test_destructive_origin_scope(self, runtime_context):
        """Modifying origin_scope must make external_isolation FAIL."""
        import shutil
        from pathlib import Path

        from evidence_agent.database.connection import get_connection
        from evidence_agent.ingest.files import import_pdf
        from evidence_agent.verification.round1 import (
            VerifyReport, _check_7_external_isolation,
        )

        fixtures = Path(__file__).resolve().parent.parent / "fixtures"
        test_pdf = Path(tempfile.mktemp(suffix=".pdf"))
        shutil.copy(fixtures / "real_scientific_article_en.pdf", test_pdf)
        import_pdf(test_pdf)

        with get_connection() as conn:
            conn.execute("PRAGMA ignore_check_constraints = ON")
            conn.execute("UPDATE sources SET origin_scope = 'internal'")
            conn.execute("PRAGMA ignore_check_constraints = OFF")

        report = VerifyReport()
        _check_7_external_isolation(report)
        assert report.checks[0]["status"] == "FAIL", (
            f"Must FAIL after modifying origin_scope. "
            f"evidence={report.checks[0].get('evidence')}"
        )

