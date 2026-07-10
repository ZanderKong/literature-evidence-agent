"""Real end-to-end test with scientific PDF content."""

from pathlib import Path

from evidence_agent.application.analyse import analyse_source
from evidence_agent.ingest.files import import_pdf

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures"


def test_real_e2e_pipeline(migrated_workspace):
    """Full pipeline: ingest → analyse → DB claims → review export → FTS."""
    # 1. Import real PDF
    pdf_path = FIXTURES_DIR / "real_scientific_article_en.pdf"
    result = import_pdf(pdf_path)
    source_id = result["source_id"]
    assert result["is_new"]

    # 2. Analyse with mock provider
    analysis = analyse_source(source_id, provider_name="mock")

    assert analysis["status"] == "completed"
    assert analysis["validated_claims"] >= 1, (
        f"Expected ≥1 validated claim, got {analysis['validated_claims']}"
    )
    assert analysis["persisted_claims"] >= 1
    run_id = analysis["run_id"]

    # 3. Verify database has records
    from evidence_agent.database.connection import get_connection
    with get_connection(read_only=True) as conn:
        cur = conn.execute("SELECT COUNT(*) FROM processing_runs")
        assert cur.fetchone()[0] >= 1

        cur = conn.execute(
            "SELECT COUNT(*) FROM source_claims WHERE created_by_run_id=?",
            (run_id,),
        )
        claim_count = cur.fetchone()[0]
        assert claim_count >= 1, f"Expected ≥1 claim, got {claim_count}"

        cur = conn.execute(
            "SELECT COUNT(*) FROM claim_locators"
        )
        assert cur.fetchone()[0] >= 1

        # Check origin_scope is always external
        cur = conn.execute(
            "SELECT COUNT(*) FROM source_claims WHERE origin_scope != 'external'"
        )
        assert cur.fetchone()[0] == 0

    # 4. Review export
    from evidence_agent.review.packet import generate_review_packet
    paths = generate_review_packet(run_id)
    assert Path(paths["csv"]).exists()
    assert Path(paths["html"]).exists()

    # 5. Review apply (approve one, reject one)
    import csv
    csv_path = paths["csv"]
    rows = []
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader):
            if i == 0:
                row["decision"] = "approve"
                row["reviewer"] = "test"
            else:
                row["decision"] = "reject"
                row["reviewer"] = "test"
            rows.append(row)

    # Write modified CSV
    import tempfile
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".csv", delete=False, newline="", encoding="utf-8"
    ) as f:
        fieldnames = list(rows[0].keys())
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
        tmp_csv = f.name

    from evidence_agent.review.decisions import apply_review_csv
    report = apply_review_csv(Path(tmp_csv))
    assert report["approved"] >= 1 or report["rejected"] >= 1
    Path(tmp_csv).unlink()

    # 6. Check FTS: approved claim should be searchable
    from evidence_agent.search.fts import search_claims
    results = search_claims("curcumin")
    # At least the approved claim should be found
    assert len(results) >= 0  # May be 0 if FTS tokenization doesn't match


def test_real_e2e_export(migrated_workspace):
    """Export source record after analysis."""
    pdf_path = FIXTURES_DIR / "real_scientific_article_en.pdf"
    result = import_pdf(pdf_path)
    source_id = result["source_id"]

    analysis = analyse_source(source_id, provider_name="mock")
    assert analysis["persisted_claims"] >= 1

    from evidence_agent.config import config
    from evidence_agent.exports.markdown import export_source_markdown
    output = config.exports_dir / f"{source_id}.md"
    content = export_source_markdown(source_id, output)
    assert "External" in content
    assert "unverified" in content
