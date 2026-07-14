"""Golden set evaluation tests."""


from tests.golden.evaluator import evaluate_golden
from tests.golden.golden_loader import load_golden


class TestGoldenSet:
    def test_golden_set_has_32_entries(self):
        """Golden set must have at least 32 entries."""
        golden = load_golden()
        assert len(golden) >= 32, f"Expected >=32, got {len(golden)}"
        positives = [g for g in golden if g["label"] == "positive"]
        negatives = [g for g in golden if g["label"] == "negative"]
        assert len(positives) >= 24, f"Expected >=24 positive, got {len(positives)}"
        assert len(negatives) >= 8, f"Expected >=8 negative, got {len(negatives)}"

    def test_golden_evaluator_handles_empty(self):
        """Evaluator must handle empty claims gracefully."""
        result = evaluate_golden([])
        assert result["extracted_claims"] == 0
        assert "recall" in result
        assert "negative_extraction" in result

    def test_golden_evaluator_no_false_neg_match(self):
        """Negative patterns must not match when no claims."""
        result = evaluate_golden([])
        assert result["negative_matches"] == 0

    def test_golden_claim_types_valid(self):
        """All golden entries must have valid claim types."""
        valid = {
            "background_statement", "method_statement",
            "reported_observation", "reported_result",
            "author_interpretation", "author_conclusion",
            "author_hypothesis", "author_limitation", "future_work",
        }
        golden = load_golden()
        for g in golden:
            ct = g.get("claim_type")
            if ct:
                assert ct in valid, f"Invalid type: {ct}"

    def test_evaluate_with_real_pipeline(self, runtime_context):
        """Run full pipeline and evaluate against golden set."""
        from pathlib import Path

        from evidence_agent.application.analyse import analyse_source
        from evidence_agent.database.connection import get_connection
        from evidence_agent.ingest.files import import_pdf

        fixtures = Path(__file__).resolve().parent.parent / "fixtures"
        pdf = fixtures / "real_scientific_article_en.pdf"
        r = import_pdf(pdf)
        analysis = analyse_source(r["source_id"], provider_name="mock")

        with get_connection(read_only=True) as conn:
            rows = conn.execute(
                "SELECT * FROM source_claims WHERE created_by_run_id = ?",
                (analysis["run_id"],),
            ).fetchall()

        claims = [dict(row) for row in rows]
        result = evaluate_golden(claims)

        assert result["extracted_claims"] > 0, "Must extract at least 1 claim"
        assert result["negative_matches"] == 0, (
            f"Must have 0 negative matches, got {result['negative_matches']}"
        )
