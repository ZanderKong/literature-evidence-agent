"""Regression tests: verify must perform real behavioral checks.

The new verify creates an isolated workspace and runs real operations.
These tests confirm the new implementation doesn't have the old flaws
(table existence, COUNT >= 0, migration version only).
"""



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
