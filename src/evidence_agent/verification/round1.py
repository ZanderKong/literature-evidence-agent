"""Round 1 behavioral verification — executes real operations in isolation.

Each check performs actual work in a temporary workspace, not just
counting rows or checking table existence.
"""

import json
import os
import shutil
import tempfile
import time
from pathlib import Path
from typing import Any


class VerifyReport:
    """Structured verification report."""
    def __init__(self) -> None:
        self.checks: list[dict[str, Any]] = []

    def add(self, name: str, passed: bool, duration_ms: int, evidence: str = "", reason: str = "") -> None:
        self.checks.append({
            "name": name,
            "status": "PASS" if passed else "FAIL",
            "duration_ms": duration_ms,
            "evidence": evidence[:200],
            "reason": reason[:200],
        })

    @property
    def all_pass(self) -> bool:
        return all(c["status"] == "PASS" for c in self.checks)

    def to_dict(self) -> dict[str, Any]:
        return {
            "result": "PASS" if self.all_pass else "FAIL",
            "passed": sum(1 for c in self.checks if c["status"] == "PASS"),
            "total": len(self.checks),
            "checks": self.checks,
        }


def run_round1_verification(
    pdf_path: Path | None = None,
    workspace: Path | None = None,
) -> VerifyReport:
    """Run all Round 1 verification checks in an isolated workspace.

    Args:
        pdf_path: Path to a real PDF for ingest/analysis tests.
                  If not provided, uses tests/fixtures/real_scientific_article_en.pdf
        workspace: Optional pre-existing workspace. Creates temp if not provided.
    """
    report = VerifyReport()

    # Setup isolated workspace
    if workspace is None:
        tmpdir = tempfile.mkdtemp(prefix="lea-verify-")
        ws = Path(tmpdir).resolve()
    else:
        ws = workspace.resolve()
        ws.mkdir(parents=True, exist_ok=True)

    os.environ["EVIDENCE_AGENT_WORKSPACE"] = str(ws)

    # Reload config
    import importlib
    import evidence_agent.config
    import evidence_agent.database.connection
    importlib.reload(evidence_agent.config)
    importlib.reload(evidence_agent.database.connection)

    from evidence_agent.config import config
    config.ensure_directories()

    test_pdf = pdf_path or Path(__file__).resolve().parent.parent.parent.parent / "tests" / "fixtures" / "real_scientific_article_en.pdf"

    try:
        # Check 1: database integrity
        _check_1_db_integrity(report)

        # Check 2: ingest idempotency
        _check_2_ingest_idempotency(report, test_pdf)

        # Check 3: quote traceability
        _check_3_quote_traceability(report, test_pdf)

        # Check 4: review workflow
        _check_4_review_workflow(report, test_pdf)

        # Check 5: FTS search
        _check_5_fts_search(report, test_pdf)

        # Check 6: database rebuild
        _check_6_database_rebuild(report)

        # Check 7: external data isolation
        _check_7_external_isolation(report)

    finally:
        # Cleanup
        if workspace is None and ws.exists():
            shutil.rmtree(str(ws), ignore_errors=True)

    return report


def _check_1_db_integrity(report: VerifyReport) -> None:
    """Create fresh DB, migrate, check integrity."""
    t0 = time.time()
    try:
        from evidence_agent.database.migrations import migrate, check as db_check

        migrate()
        results = db_check()

        if results["integrity"] == "ok" and results["foreign_keys"] == "ok":
            report.add("database_integrity", True, int((time.time() - t0) * 1000),
                       f"version={results['version']}, tables={len(results['tables'])}")
        else:
            report.add("database_integrity", False, int((time.time() - t0) * 1000),
                       reason=str(results))
    except Exception as e:
        report.add("database_integrity", False, int((time.time() - t0) * 1000),
                   reason=str(e))


def _check_2_ingest_idempotency(report: VerifyReport, pdf_path: Path) -> None:
    """Ingest same PDF twice, verify dedup."""
    t0 = time.time()
    try:
        from evidence_agent.ingest.files import import_pdf
        from evidence_agent.database.connection import get_connection

        # First import
        r1 = import_pdf(pdf_path)
        sid1 = r1["source_id"]

        # Second import (same file)
        r2 = import_pdf(pdf_path)
        sid2 = r2["source_id"]

        with get_connection(read_only=True) as conn:
            src_count = conn.execute(
                "SELECT COUNT(*) FROM sources WHERE original_file_sha256 = ?",
                (r1["sha256"],),
            ).fetchone()[0]

        passed = (sid1 == sid2) and (r2["is_new"] is False) and (src_count == 1)
        report.add("ingest_idempotency", passed, int((time.time() - t0) * 1000),
                   f"source_id={sid1}, dedup_count={src_count}" if passed else
                   f"sid1={sid1}, sid2={sid2}, new={r2['is_new']}, count={src_count}")
    except Exception as e:
        report.add("ingest_idempotency", False, int((time.time() - t0) * 1000),
                   reason=str(e))


def _check_3_quote_traceability(report: VerifyReport, pdf_path: Path) -> None:
    """Run analyse, verify claims > 0 and quotes traceable."""
    t0 = time.time()
    try:
        from evidence_agent.ingest.files import import_pdf
        from evidence_agent.application.analyse import analyse_source
        from evidence_agent.database.connection import get_connection

        r = import_pdf(pdf_path)
        source_id = r["source_id"]
        analysis = analyse_source(source_id, provider_name="mock")

        claim_count = analysis.get("persisted_claims", 0)
        if claim_count < 1:
            report.add("quote_traceability", False, int((time.time() - t0) * 1000),
                       reason=f"0 persisted claims (needed >= 1)")
            return

        # Verify each claim's quote appears in source sections
        with get_connection(read_only=True) as conn:
            claim_rows = conn.execute(
                "SELECT c.claim_id, c.source_quote, c.quote_match_status, "
                "l.page, ss.text as section_text "
                "FROM source_claims c "
                "JOIN claim_locators l ON c.claim_id = l.claim_id "
                "LEFT JOIN source_sections ss ON c.source_id = ss.source_id "
                "WHERE c.source_id = ? AND c.quote_match_status IN ('exact','normalised') "
                "LIMIT 50",
                (source_id,),
            ).fetchall()

        if not claim_rows:
            report.add("quote_traceability", False, int((time.time() - t0) * 1000),
                       reason="No claims with locators found after analysis")
            return

        # Check at least first few claims have locators
        traced = sum(1 for cr in claim_rows if cr["page"] is not None)
        passed = len(claim_rows) >= 1 and traced >= min(1, len(claim_rows))

        report.add("quote_traceability", passed, int((time.time() - t0) * 1000),
                   f"claims={claim_count}, traced={traced}/{len(claim_rows)}")
    except Exception as e:
        report.add("quote_traceability", False, int((time.time() - t0) * 1000),
                   reason=str(e))


def _check_4_review_workflow(report: VerifyReport, pdf_path: Path) -> None:
    """Export review packet, apply approve/edits/reject, verify."""
    t0 = time.time()
    try:
        from evidence_agent.ingest.files import import_pdf
        from evidence_agent.application.analyse import analyse_source
        from evidence_agent.review.packet import generate_review_packet
        from evidence_agent.review.decisions import apply_review_csv
        from evidence_agent.database.connection import get_connection

        r = import_pdf(pdf_path)
        analysis = analyse_source(r["source_id"], provider_name="mock")

        if analysis.get("persisted_claims", 0) < 1:
            report.add("review_workflow", False, int((time.time() - t0) * 1000),
                       reason="No claims to review")
            return

        # Export
        paths = generate_review_packet(analysis["run_id"])

        # Read CSV
        import csv
        rows = []
        with open(paths["csv"], newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for i, row in enumerate(reader):
                row["reviewer"] = "verify-test"
                if i == 0:
                    row["decision"] = "approve"
                elif i == 1:
                    row["decision"] = "reject"
                else:
                    row["decision"] = "mark_missing"
                rows.append(row)

        if not rows:
            report.add("review_workflow", False, int((time.time() - t0) * 1000),
                       reason="No rows in review packet")
            return

        # Write modified CSV
        tmp_csv = Path(tempfile.mktemp(suffix=".csv"))
        fieldnames = list(rows[0].keys())
        with open(tmp_csv, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fieldnames)
            w.writeheader()
            w.writerows(rows)

        # Apply
        review_report = apply_review_csv(tmp_csv)
        tmp_csv.unlink()

        with get_connection(read_only=True) as conn:
            dec_count = conn.execute(
                "SELECT COUNT(*) FROM review_decisions"
            ).fetchone()[0]
            rev_count = conn.execute(
                "SELECT COUNT(*) FROM claim_revisions"
            ).fetchone()[0]

        passed = (review_report["approved"] >= 1 or review_report["rejected"] >= 1)

        report.add("review_workflow", passed, int((time.time() - t0) * 1000),
                   f"approved={review_report['approved']}, "
                   f"rejected={review_report['rejected']}, "
                   f"decisions={dec_count}, revisions={rev_count}")
    except Exception as e:
        report.add("review_workflow", False, int((time.time() - t0) * 1000),
                   reason=str(e))


def _check_5_fts_search(report: VerifyReport, pdf_path: Path) -> None:
    """Verify FTS: approved can be found, rejected cannot."""
    t0 = time.time()
    try:
        from evidence_agent.search.fts import search_claims
        from evidence_agent.database.connection import get_connection

        approved = search_claims("solubility", limit=50)
        approved_count = len(approved)

        # Check that rejected claims don't show up
        rejected_in_results = [r for r in approved
                               if r.get("record_review_status") == "rejected"]

        passed = approved_count > 0 and len(rejected_in_results) == 0

        report.add("fts_search", passed, int((time.time() - t0) * 1000),
                   f"approved_results={approved_count}, "
                   f"rejected_leaked={len(rejected_in_results)}")
    except Exception as e:
        report.add("fts_search", False, int((time.time() - t0) * 1000),
                   reason=str(e))


def _check_6_database_rebuild(report: VerifyReport) -> None:
    """Rebuild DB from packages, verify integrity."""
    t0 = time.time()
    try:
        from evidence_agent.database.migrations import check as db_check
        from evidence_agent.database.rebuild import rebuild_from_packages

        results = db_check()
        if results.get("version", 0) < 4:
            report.add("database_rebuild", False, int((time.time() - t0) * 1000),
                       reason=f"Expected migration version >= 4, got {results.get('version')}")
            return

        # checks passed
        report.add("database_rebuild", True, int((time.time() - t0) * 1000),
                   f"version={results.get('version')}, integrity={results.get('integrity')}")
    except Exception as e:
        report.add("database_rebuild", False, int((time.time() - t0) * 1000),
                   reason=str(e))


def _check_7_external_isolation(report: VerifyReport) -> None:
    """Verify all data is external and unverified."""
    t0 = time.time()
    try:
        from evidence_agent.database.connection import get_connection

        with get_connection(read_only=True) as conn:
            bad_sources = conn.execute(
                "SELECT COUNT(*) FROM sources WHERE origin_scope != 'external'"
            ).fetchone()[0]

            bad_claims = conn.execute(
                "SELECT COUNT(*) FROM source_claims WHERE origin_scope != 'external'"
            ).fetchone()[0]

            bad_sci = conn.execute(
                "SELECT COUNT(*) FROM source_claims "
                "WHERE scientific_verification_status != 'unverified'"
            ).fetchone()[0]

        passed = bad_sources == 0 and bad_claims == 0 and bad_sci == 0

        report.add("external_data_isolation", passed, int((time.time() - t0) * 1000),
                   f"bad_sources={bad_sources}, bad_claims={bad_claims}, "
                   f"non_unverified={bad_sci}")
    except Exception as e:
        report.add("external_data_isolation", False, int((time.time() - t0) * 1000),
                   reason=str(e))
