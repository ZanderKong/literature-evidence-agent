"""Unit tests for LLM providers."""

from evidence_agent.extraction.provider import (
    ExtractionRequest,
    MockProvider,
)


class TestMockProvider:
    """Test the mock provider returns expected responses."""

    def test_model_name(self):
        provider = MockProvider()
        assert provider.model_name == "mock"

    def test_prompt_version(self):
        provider = MockProvider()
        assert provider.prompt_version == "claim_extraction_v1"

    def test_extract_claims_with_text(self):
        provider = MockProvider()
        request = ExtractionRequest(
            task_description="Extract all claims",
            section_text=(
                "The solubility increased from 1.0 to 5.2 mg/mL "
                "upon complexation. This suggests that hydrogen "
                "bonding plays a key role."
            ),
            section_heading="Results",
            page_start=1,
            page_end=1,
        )
        response = provider.extract_claims(request)

        assert len(response.claims) == 4  # Updated: 4 default claims for real PDF
        assert response.error is None
        assert response.model_name == "mock"
        assert response.prompt_version == "claim_extraction_v1"
        assert response.input_hash  # Should be computed
        assert response.output_hash

    def test_extract_claims_empty_text(self):
        provider = MockProvider()
        request = ExtractionRequest(
            task_description="Extract all claims",
            section_text="   ",
        )
        response = provider.extract_claims(request)
        assert len(response.claims) == 0

    def test_extract_claims_short_text(self):
        provider = MockProvider()
        request = ExtractionRequest(
            task_description="Extract all claims",
            section_text="Hi",
        )
        response = provider.extract_claims(request)
        assert len(response.claims) == 0

    def test_repeatable_output(self):
        """Mock provider should give the same output for the same input."""
        provider = MockProvider()
        request = ExtractionRequest(
            task_description="Extract all claims",
            section_text="Some meaningful text about solubility and complexes.",
        )

        r1 = provider.extract_claims(request)
        r2 = provider.extract_claims(request)

        assert r1.output_hash == r2.output_hash
        assert len(r1.claims) == len(r2.claims)

    def test_custom_claims(self):
        """Can provide custom claims for testing."""
        custom = [
            {
                "claim_type": "author_limitation",
                "source_quote": "This study was limited to in vitro conditions.",
                "faithful_paraphrase": "该研究仅限于体外条件。",
                "evidence_basis_description": "作者自述的限制。",
                "scope_description": None,
                "author_hedging": None,
                "locator_hint": {"page": 10, "section_heading": "Conclusion"},
                "entities": [],
            }
        ]
        provider = MockProvider(fixed_claims=custom)
        response = provider.extract_claims(
            ExtractionRequest(task_description="Test", section_text="Some text" * 10)
        )
        assert len(response.claims) == 1
        assert response.claims[0]["claim_type"] == "author_limitation"


class TestExtractionRequest:
    """Test the ExtractionRequest dataclass."""

    def test_defaults(self):
        req = ExtractionRequest(
            task_description="Test task",
            section_text="Test section text",
        )
        assert req.section_heading is None
        assert req.page_start is None
        assert req.section_type == "body"
