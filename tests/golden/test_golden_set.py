"""Golden set evaluation tests."""

from tests.golden.evaluator import evaluate_golden
from tests.golden.golden_loader import load_golden


class TestGoldenSet:
    def test_golden_set_has_32_entries(self):
        golden = load_golden()
        assert len(golden) >= 32, f"Expected >=32, got {len(golden)}"
        positives = [g for g in golden if g.get("must_extract")]
        negatives = [g for g in golden if not g.get("must_extract")]
        assert len(positives) >= 24, f"Expected >=24 positive, got {len(positives)}"
        assert len(negatives) >= 8, f"Expected >=8 negative, got {len(negatives)}"

    def test_golden_has_bilingual_entries(self):
        golden = load_golden()
        en = [g for g in golden if g.get("language") == "EN"]
        cn = [g for g in golden if g.get("language") == "CN"]
        assert len(en) > 0, "Must have English entries"
        assert len(cn) > 0, "Must have Chinese entries"

    def test_golden_all_required_fields(self):
        golden = load_golden()
        required = ["annotation_id", "source_file", "language",
                     "source_quote", "claim_type", "faithful_paraphrase",
                     "page", "section_heading", "must_extract"]
        for g in golden:
            for r in required:
                assert r in g, f"{g.get('annotation_id','?')}: missing {r}"

    def test_evaluate_with_known_claims_all_thresholds_pass(self, runtime_context):
        """Insert claims matching golden annotations, evaluate, all thresholds pass."""
        import json
        from evidence_agent.database.connection import get_connection

        golden = load_golden()
        positives = [g for g in golden if g.get("must_extract")]

        with get_connection() as conn:
            conn.execute(
                "INSERT INTO sources (source_id, source_type, title, "
                "original_file_sha256, origin_scope, "
                "scientific_verification_status, created_at, updated_at) "
                "VALUES ('SRC-golden', 'journal_article', 'Golden Test', "
                "'sha:golden', 'external', 'unverified', "
                "'2025-01-01T00:00:00', '2025-01-01T00:00:00')"
            )
            conn.execute(
                "INSERT INTO processing_runs (run_id, source_id, module_name, "
                "model_name, input_hash, status, started_at) "
                "VALUES ('RUN-golden', 'SRC-golden', 'analyse', 'mock', "
                "'hash:golden', 'completed', '2025-01-01T00:00:00')"
            )

            for i, p in enumerate(positives):
                cid = f"CLM-golden-{i:03d}"
                loc_id = f"LOC-golden-{i:03d}"
                castype = p.get("claim_type", "reported_result")
                quote = p.get("source_quote", "")
                para = p.get("faithful_paraphrase", "")
                page = p.get("page", 1)
                hedging = p.get("author_hedging", "")
                scope = p.get("scope_description", "")

                conn.execute(
                    "INSERT INTO source_claims (claim_id, source_id, "
                    "claim_type, source_quote, faithful_paraphrase, "
                    "evidence_basis_description, author_hedging, "
                    "scope_description, origin_scope, record_review_status, "
                    "scientific_verification_status, quote_match_status, "
                    "created_by_run_id, created_at, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'external', 'approved', "
                    "'unverified', 'exact', ?, ?, ?)",
                    (cid, "SRC-golden", castype, quote, para,
                     "Evidence", hedging, scope,
                     "RUN-golden",
                     "2025-01-01T00:00:00", "2025-01-01T00:00:00"),
                )
                conn.execute(
                    "INSERT INTO claim_locators (locator_id, claim_id, page, "
                    "locator_confidence) VALUES (?, ?, ?, 'high')",
                    (loc_id, cid, page or 1),
                )

        with get_connection(read_only=True) as conn:
            rows = conn.execute(
                "SELECT c.*, l.page, l.locator_confidence "
                "FROM source_claims c "
                "LEFT JOIN claim_locators l ON c.claim_id = l.claim_id "
                "WHERE c.source_id = 'SRC-golden'"
            ).fetchall()
            claims = [dict(r) for r in rows]

        result = evaluate_golden(claims)

        assert result["all_thresholds_pass"], (
            f"All thresholds must pass. Metrics: {json.dumps(result, indent=2)}"
        )
        assert result["unsupported_accepted"] == 0
        assert result["negative_matches"] == 0
        assert result["recall"] >= 80

    def test_negative_insertion_causes_fail(self, runtime_context):
        """Insert a negative item as a claim → evaluator must FAIL."""
        from evidence_agent.database.connection import get_connection

        golden = load_golden()
        positives = [g for g in golden if g.get("must_extract")][:5]

        with get_connection() as conn:
            conn.execute(
                "INSERT INTO sources (source_id, source_type, title, "
                "original_file_sha256, origin_scope, "
                "scientific_verification_status, created_at, updated_at) "
                "VALUES ('SRC-gneg', 'journal_article', 'Neg Test', "
                "'sha:gneg', 'external', 'unverified', "
                "'2025-01-01T00:00:00', '2025-01-01T00:00:00')"
            )
            conn.execute(
                "INSERT INTO processing_runs (run_id, source_id, module_name, "
                "model_name, input_hash, status, started_at) "
                "VALUES ('RUN-gneg', 'SRC-gneg', 'analyse', 'mock', "
                "'hash:gneg', 'completed', '2025-01-01T00:00:00')"
            )

            for i, p in enumerate(positives):
                conn.execute(
                    "INSERT INTO source_claims (claim_id, source_id, "
                    "claim_type, source_quote, faithful_paraphrase, "
                    "evidence_basis_description, origin_scope, "
                    "record_review_status, scientific_verification_status, "
                    "quote_match_status, created_by_run_id, "
                    "created_at, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, 'external', 'approved', "
                    "'unverified', 'exact', ?, ?, ?)",
                    (f"CLM-neg-{i:03d}", "SRC-gneg",
                     p.get("claim_type", ""),
                     p.get("source_quote", ""),
                     p.get("faithful_paraphrase", ""),
                     "Evidence",
                     "RUN-gneg",
                     "2025-01-01T00:00:00", "2025-01-01T00:00:00"),
                )
                conn.execute(
                    "INSERT INTO claim_locators (locator_id, claim_id, page, "
                    "locator_confidence) VALUES (?, ?, ?, 'high')",
                    (f"LOC-neg-{i:03d}", f"CLM-neg-{i:03d}",
                     p.get("page", 1)),
                )

            neg = [g for g in golden if not g.get("must_extract")][0]
            conn.execute(
                "INSERT INTO source_claims (claim_id, source_id, claim_type, "
                "source_quote, faithful_paraphrase, evidence_basis_description, "
                "origin_scope, record_review_status, "
                "scientific_verification_status, quote_match_status, "
                "created_by_run_id, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, 'external', 'approved', "
                "'unverified', 'exact', ?, ?, ?)",
                ("CLM-neg-BAD", "SRC-gneg", "reported_result",
                 neg.get("source_quote", ""), "Bad claim", "Evidence",
                 "RUN-gneg",
                 "2025-01-01T00:00:00", "2025-01-01T00:00:00"),
            )

        with get_connection(read_only=True) as conn:
            rows = conn.execute(
                "SELECT * FROM source_claims WHERE source_id = 'SRC-gneg'"
            ).fetchall()
            claims = [dict(r) for r in rows]

        result = evaluate_golden(claims)
        assert not result["all_thresholds_pass"], (
            "Must FAIL when negative item appears as claim"
        )
