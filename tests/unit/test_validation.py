"""Unit tests for claim validation."""

from evidence_agent.validators.quote import (
    _normalize,
    check_leakage,
    match_quote,
    validate_claims,
    validate_schema,
)


class TestNormalize:
    """Test text normalization."""

    def test_normalize_whitespace(self):
        result = _normalize("hello   world\n\ttest")
        assert result == "hello world test"

    def test_normalize_unicode(self):
        # Non-breaking space -> space
        result = _normalize("hello\u00a0world")
        assert result == "hello world"

    def test_normalize_hyphens(self):
        result = _normalize("well\u2010known")
        assert result == "well-known"


class TestMatchQuote:
    """Test quote matching."""

    def test_exact_match(self):
        status, start, end = match_quote(
            "The solubility increased.", "The solubility increased."
        )
        assert status == "exact"
        assert start == 0

    def test_normalised_whitespace(self):
        status, start, end = match_quote(
            "hello world", "hello   world"
        )
        assert status == "normalised"

    def test_newline_normalised(self):
        status, _, _ = match_quote(
            "The solubility increased upon complexation.",
            "The solubility\nincreased upon\ncomplexation.",
        )
        assert status == "normalised"

    def test_not_found(self):
        status, _, _ = match_quote(
            "completely different text", "The solubility increased."
        )
        assert status == "not_found"

    def test_unicode_hyphen(self):
        """Different hyphen characters should normalize."""
        status, _, _ = match_quote(
            "well-known effect", "well\u2010known effect"
        )
        assert status == "normalised"


class TestValidateSchema:
    """Test schema validation."""

    def test_valid_claim(self):
        claim = {
            "claim_type": "reported_result",
            "source_quote": "The solubility increased.",
            "faithful_paraphrase": "溶解度提高了。",
            "evidence_basis_description": "Based on Figure 1.",
        }
        errors = validate_schema(claim)
        assert len(errors) == 0

    def test_missing_quote(self):
        claim = {
            "claim_type": "reported_result",
            "source_quote": "",
            "faithful_paraphrase": "paraphrase",
            "evidence_basis_description": "basis",
        }
        errors = validate_schema(claim)
        assert len(errors) >= 1

    def test_invalid_claim_type(self):
        claim = {
            "claim_type": "made_up_type",
            "source_quote": "quote",
            "faithful_paraphrase": "paraphrase",
            "evidence_basis_description": "basis",
        }
        errors = validate_schema(claim)
        assert len(errors) >= 1


class TestCheckLeakage:
    """Test external data isolation checks."""

    def test_no_leakage(self):
        claim = {
            "source_quote": "The solubility increased.",
            "faithful_paraphrase": "溶解度提高了。",
        }
        errors = check_leakage(claim)
        assert len(errors) == 0

    def test_internal_reference_detected(self):
        claim = {
            "source_quote": "As shown in our internal_measurements database...",
            "faithful_paraphrase": "paraphrase",
        }
        errors = check_leakage(claim)
        assert len(errors) >= 1


class TestValidateClaims:
    """Test full claim validation pipeline."""

    def test_valid_claim_passes(self):
        raw = [
            {
                "claim_type": "reported_result",
                "source_quote": "The solubility increased from 1.0 to 5.2 mg/mL.",
                "faithful_paraphrase": "溶解度从 1.0 增加到 5.2 mg/mL。",
                "evidence_basis_description": "Based on Figure 1.",
                "locator_hint": {"page": 1},
                "_block_page_start": 1,
            }
        ]

        sections = [
            {
                "text": "The solubility increased from 1.0 to 5.2 mg/mL. "
                        "This was measured by HPLC."
            }
        ]
        pages = [{"page": 1, "text": sections[0]["text"]}]

        validated, failed, invalid = validate_claims(raw, sections, pages)
        assert len(validated) == 1
        assert len(failed) == 0
        assert len(invalid) == 0
        assert validated[0]["_quote_match_status"] == "exact"

    def test_quote_not_found_fails(self):
        raw = [
            {
                "claim_type": "reported_result",
                "source_quote": "This text does not exist in the source.",
                "faithful_paraphrase": "转述",
                "evidence_basis_description": "basis",
                "locator_hint": {"page": 1},
            }
        ]

        sections = [{"text": "Completely different content."}]
        pages = [{"page": 1, "text": "Completely different content."}]

        validated, failed, invalid = validate_claims(raw, sections, pages)
        assert len(validated) == 0
        assert len(failed) >= 1  # not_found -> failed_locator

    def test_missing_schema_fields_invalid(self):
        raw = [
            {
                "claim_type": "reported_result",
                "source_quote": "",
                "faithful_paraphrase": "",
                "evidence_basis_description": "",
            }
        ]

        sections = [{"text": ""}]
        pages = [{"page": 1, "text": ""}]

        validated, failed, invalid = validate_claims(raw, sections, pages)
        assert len(validated) == 0
        assert len(invalid) >= 1
