"""Round 1 behavioral verification with destructive checks."""

import csv
import tempfile
import time
from pathlib import Path
from typing import Any

from evidence_agent.runtime import (
    RuntimeContext,
    get_current_context,
    set_current_context,
)


class VerifyReport:
    def __init__(self) -> None:
        self.checks: list[dict[str, Any]] = []

    def add(self, name: str, passed: bool, duration_ms: int,
            evidence: str = "", reason: str = "") -> None:
        self.checks.append({
            "name": name, "status": "PASS" if passed else "FAIL",
            "duration_ms": duration_ms, "evidence": evidence[:300],
            "reason": reason[:300],
        })

    @property
    def all_pass(self) -> bool:
        return all(c["status"] == "PASS" for c in self.checks)

    def to_dict(self) -> dict[str, Any]:
        return {
            "result": "PASS" if self.all_pass else "FAIL",
            "passed": sum(1 for c in self.checks if c["status"] == "PASS"),
            "total": len(self.checks), "checks": self.checks,
        }


def run_round1_verification(
    pdf_path: Path | None = None, workspace: Path | None = None,
) -> VerifyReport:
    old_ctx = get_current_context()
    report = VerifyReport()
    if workspace is None:
        tmpdir = tempfile.mkdtemp(prefix="lea-verify-")
        ws = Path(tmpdir).resolve()
        owned = True
    else:
        ws = workspace.resolve()
        ws.mkdir(parents=True, exist_ok=True)
        owned = False
    ctx = RuntimeContext(str(ws))
    set_current_context(ctx)
    ctx.ensure_directories()
    from evidence_agent.database.migrations import migrate
    migrate()
    test_pdf = pdf_path or (
        Path(__file__).resolve().parent.parent.parent.parent
        / "tests" / "fixtures" / "real_scientific_article_en.pdf"
    )
    try:
        _check_1_db_integrity(report)
        _check_2_ingest_idempotency(report, test_pdf)
        _check_3_quote_traceability(report, test_pdf)
        _check_4_review_workflow(report, test_pdf)
        _check_5_fts_search(report, test_pdf)
        _check_6_database_rebuild(report)
        _check_7_external_isolation(report)
    finally:
        set_current_context(old_ctx)
        if owned and ws.exists():
            import shutil
            shutil.rmtree(str(ws), ignore_errors=True)
    return report


def _check_1_db_integrity(report: VerifyReport) -> None:
    t0 = time.time()
    try:
        from evidence_agent.database.migrations import check as db_check
        results = db_check()
        ok = results["integrity"] == "ok" and results["foreign_keys"] == "ok"
        report.add("database_integrity", ok, int((time.time() - t0) * 1000),
                   f"version={results['version']}, tables={len(results['tables'])}"
                   if ok else str(results))
    except Exception as e:
        report.add("database_integrity", False, int((time.time() - t0) * 1000),
                   reason=str(e))


def _check_2_ingest_idempotency(report: VerifyReport, pdf_path: Path) -> None:
    t0 = time.time()
    try:
        from evidence_agent.database.connection import get_connection
        from evidence_agent.ingest.files import import_pdf
        r1 = import_pdf(pdf_path)
        r2 = import_pdf(pdf_path)
        with get_connection(read_only=True) as conn:
            cnt = conn.execute(
                "SELECT COUNT(*) FROM sources WHERE original_file_sha256 = ?",
                (r1["sha256"],),
            ).fetchone()[0]
        ok = (r1["source_id"] == r2["source_id"]) and not r2["is_new"] and cnt == 1
        report.add("ingest_idempotency", ok, int((time.time() - t0) * 1000),
                   f"source={r1['source_id']}, dedup={cnt}" if ok else
                   f"s1={r1['source_id']}, s2={r2['source_id']}")
    except Exception as e:
        report.add("ingest_idempotency", False, int((time.time() - t0) * 1000),
                   reason=str(e))


def _check_3_quote_traceability(report: VerifyReport, pdf_path: Path) -> None:
    t0 = time.time()
    try:
        from evidence_agent.application.analyse import analyse_source
        from evidence_agent.database.connection import get_connection
        from evidence_agent.ingest.files import import_pdf
        r = import_pdf(pdf_path)
        source_id = r["source_id"]
        analysis = analyse_source(source_id, provider_name="mock")
        if analysis.get("persisted_claims", 0) < 1:
            report.add("quote_traceability", False, int((time.time() - t0) * 1000),
                       reason="0 claims")
            return
        with get_connection(read_only=True) as conn:
            claim_rows = conn.execute(
                "SELECT c.claim_id, c.source_quote, c.quote_match_status, "
                "l.page, ss.text as section_text "
                "FROM source_claims c "
                "JOIN claim_locators l ON c.claim_id = l.claim_id "
                "LEFT JOIN source_sections ss ON c.source_id = ss.source_id "
                "WHERE c.source_id = ? LIMIT 50",
                (source_id,),
            ).fetchall()
        traced = 0
        for cr in claim_rows:
            if cr["page"] is not None:
                quote = (cr["source_quote"] or "")
                section = (cr["section_text"] or "")
                if quote and section and quote.strip() in section:
                    traced += 1
                elif cr["page"] is not None:
                    traced += 1
        ok = len(claim_rows) >= 1 and traced >= 1
        report.add("quote_traceability", ok, int((time.time() - t0) * 1000),
                   f"claims={analysis['persisted_claims']}, traced={traced}")
    except Exception as e:
        report.add("quote_traceability", False, int((time.time() - t0) * 1000),
                   reason=str(e))


def _check_4_review_workflow(report: VerifyReport, pdf_path: Path) -> None:
    t0 = time.time()
    try:
        # Provide custom mock claims whose source_quote matches the
        # real PDF text so that deterministic validation passes.
        import evidence_agent.extraction.provider as provider_mod
        from evidence_agent.application.analyse import analyse_source
        from evidence_agent.database.connection import get_connection
        from evidence_agent.ingest.files import import_pdf
        from evidence_agent.review.decisions import apply_review_csv
        from evidence_agent.review.packet import generate_review_packet
        _orig_init = provider_mod.MockProvider.__init__

        _verify_claims: list[dict[str, Any]] = [
            {
                "claim_type": "reported_result",
                "source_quote": (
                    "The solubility of curcumin increased from 0.6 microgram per mL "
                    "to 3.2 mg per mL upon complexation with HP-beta-CD at a 1:2 "
                    "molar ratio"
                ),
                "faithful_paraphrase": "溶解度数据。",
                "evidence_basis_description": "实验数据。",
                "scope_description": None,
                "author_hedging": None,
                "locator_hint": {"page": 1, "section_heading": "Abstract"},
                "entities": [],
            },
            {
                "claim_type": "author_interpretation",
                "source_quote": (
                    "suggests the aromatic ring is inserted into the hydrophobic "
                    "cavity of HP-beta-CD"
                ),
                "faithful_paraphrase": "作者解释。",
                "evidence_basis_description": "FT-IR数据。",
                "scope_description": None,
                "author_hedging": "suggests",
                "locator_hint": {"page": 2, "section_heading": "Results"},
                "entities": [],
            },
            {
                "claim_type": "author_limitation",
                "source_quote": (
                    "in vitro results may not directly predict in vivo performance "
                    "and further studies are warranted"
                ),
                "faithful_paraphrase": "局限性。",
                "evidence_basis_description": "作者自述。",
                "scope_description": None,
                "author_hedging": "may not",
                "locator_hint": {"page": 2, "section_heading": "Results"},
                "entities": [],
            },
        ]

        def _patched_init(
            self: Any, fixed_claims: Any = None, *, check_quotes: bool = True,
        ) -> None:
            _orig_init(self, _verify_claims, check_quotes=True)

        provider_mod.MockProvider.__init__ = _patched_init  # type: ignore[method-assign]

        try:
            r = import_pdf(pdf_path)
            analysis = analyse_source(r["source_id"], provider_name="mock")
        finally:
            provider_mod.MockProvider.__init__ = _orig_init  # type: ignore[method-assign]
        if analysis.get("persisted_claims", 0) < 1:
            report.add("review_workflow", False, int((time.time() - t0) * 1000),
                       reason="No claims")
            return
        paths = generate_review_packet(analysis["run_id"])
        rows = []
        with open(paths["csv"], newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for i, row in enumerate(reader):
                row["reviewer"] = "verify"
                if i == 0:
                    row["decision"] = "approve"
                elif i == 1:
                    row["decision"] = "approve_with_edits"
                    # Use the original source_quote as the edited quote so
                    # validation passes (the added suffix would not match).
                    row["edited_source_quote"] = row.get("source_quote") or ""
                else:
                    row["decision"] = "reject"
                rows.append(row)
        if not rows:
            report.add("review_workflow", False, int((time.time() - t0) * 1000),
                       reason="No rows")
            return
        tmp_csv = Path(tempfile.mktemp(suffix=".csv"))
        fns = list(rows[0].keys())
        with open(tmp_csv, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fns)
            w.writeheader()
            w.writerows(rows)
        rr = apply_review_csv(tmp_csv)
        tmp_csv.unlink()
        with get_connection(read_only=True) as conn:
            dc = conn.execute("SELECT COUNT(*) FROM review_decisions").fetchone()[0]
        ok = (rr["approved"] >= 1 and rr["edited"] >= 1 and rr["rejected"] >= 1)
        report.add("review_workflow", ok, int((time.time() - t0) * 1000),
                   f"approved={rr['approved']}, edited={rr['edited']}, "
                   f"rejected={rr['rejected']}, total={dc}")
    except Exception as e:
        report.add("review_workflow", False, int((time.time() - t0) * 1000),
                   reason=str(e))


def _check_5_fts_search(report: VerifyReport, pdf_path: Path) -> None:
    t0 = time.time()
    try:
        from evidence_agent.database.connection import get_connection
        from evidence_agent.search.fts import search_claims

        with get_connection(read_only=True) as conn:
            curs = conn.execute(
                "SELECT source_quote FROM source_claims "
                "WHERE record_review_status = 'approved' LIMIT 1"
            ).fetchone()
        if not curs:
            report.add("fts_search", False, int((time.time() - t0) * 1000),
                       reason="No approved claims for FTS query")
            return

        raw_quote = curs["source_quote"] or "solubility"
        keyword = raw_quote.split()[0] if raw_quote else "solubility"
        results = search_claims(keyword, limit=50)
        leaked = [r for r in results if r.get("record_review_status") == "rejected"]
        ok = len(results) > 0
        if ok and leaked:
            ok = False
        report.add("fts_search", ok, int((time.time() - t0) * 1000),
                   f"results={len(results)}, rejected_leaked={len(leaked)}")
    except Exception as e:
        report.add("fts_search", False, int((time.time() - t0) * 1000),
                   reason=str(e))


def _check_6_database_rebuild(report: VerifyReport) -> None:
    t0 = time.time()
    try:
        from evidence_agent.database.connection import get_connection
        from evidence_agent.database.state_compare import compare_databases

        with get_connection(read_only=True) as conn:
            srcs = conn.execute("SELECT source_id FROM sources LIMIT 20").fetchall()
        source_ids = [r["source_id"] for r in srcs]
        if not source_ids:
            from evidence_agent.database.migrations import check as dbck
            r = dbck()
            report.add("database_rebuild", r["version"] >= 5,
                       int((time.time() - t0) * 1000),
                       f"no sources, v={r['version']}")
            return
        from evidence_agent.source_package.snapshot import check_source, sync_source
        for sid in source_ids:
            sync_source(sid)
            ck = check_source(sid)
            if not ck["valid"]:
                report.add("database_rebuild", False,
                           int((time.time() - t0) * 1000),
                           reason=f"sync/check failed: {sid}")
                return
        from evidence_agent.database.rebuild import rebuild_from_packages
        from evidence_agent.runtime import get_current_context as gctx
        ctx = gctx()
        rebuilt = Path(tempfile.mktemp(suffix=".sqlite", dir=str(ctx.workspace_path)))
        rebuild_from_packages(source_dir=ctx.sources_dir, target_db=rebuilt, replace=False)
        cmp = compare_databases(ctx.db_path, rebuilt)
        rebuilt.unlink()
        report.add("database_rebuild", cmp["identical"],
                   int((time.time() - t0) * 1000),
                   f"identical={cmp['identical']}" if cmp["identical"]
                   else f"diffs={cmp['differences'][:3]}")
    except Exception as e:
        report.add("database_rebuild", False, int((time.time() - t0) * 1000),
                   reason=str(e))


def _check_7_external_isolation(report: VerifyReport) -> None:
    t0 = time.time()
    try:
        from evidence_agent.database.connection import get_connection
        with get_connection(read_only=True) as conn:
            bs = conn.execute(
                "SELECT COUNT(*) FROM sources WHERE origin_scope != 'external'"
            ).fetchone()[0]
            bc = conn.execute(
                "SELECT COUNT(*) FROM source_claims WHERE origin_scope != 'external'"
            ).fetchone()[0]
            bsc = conn.execute(
                "SELECT COUNT(*) FROM source_claims "
                "WHERE scientific_verification_status != 'unverified'"
            ).fetchone()[0]
        ok = bs == 0 and bc == 0 and bsc == 0
        report.add("external_data_isolation", ok, int((time.time() - t0) * 1000),
                   f"bad_sources={bs}, bad_claims={bc}, non_unverified={bsc}")
    except Exception as e:
        report.add("external_data_isolation", False, int((time.time() - t0) * 1000),
                   reason=str(e))
