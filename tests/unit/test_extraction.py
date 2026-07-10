"""Unit tests for claim extraction."""

from evidence_agent.extraction.claims import extract_claims_from_source
from evidence_agent.extraction.provider import MockProvider


class TestExtractClaims:
    """Test claim extraction pipeline."""

    def test_extract_from_sections(self):
        sections = [
            {
                "section_type": "results",
                "heading": "Results",
                "page_start": 1,
                "page_end": 2,
                "text": (
                    "The solubility increased from 1.0 to 5.2 mg/mL "
                    "upon complexation. This suggests that hydrogen "
                    "bonding plays a key role in the stabilization. "
                    "However, the in vitro results may not predict "
                    "in vivo performance."
                ),
            }
        ]

        claims, report = extract_claims_from_source(
            sections, provider=MockProvider()
        )

        assert report["blocks_processed"] >= 1
        assert report["candidate_claims"] >= 1
        assert len(claims) >= 1

        # Each claim should have metadata
        for claim in claims:
            assert "_model_name" in claim
            assert "_prompt_version" in claim

    def test_skips_references(self):
        sections = [
            {
                "section_type": "references",
                "heading": "References",
                "page_start": 10,
                "page_end": 12,
                "text": "[1] Author A, et al. Journal of Something. 2020.",
            }
        ]

        claims, report = extract_claims_from_source(
            sections, provider=MockProvider()
        )

        assert report["blocks_processed"] == 0

    def test_skips_short_sections(self):
        sections = [
            {
                "section_type": "body",
                "text": "Short.",
            }
        ]

        claims, report = extract_claims_from_source(
            sections, provider=MockProvider()
        )

        assert report["blocks_processed"] == 0

    def test_task_focused_mode(self):
        """task_focused should work same as source_complete in mock."""
        sections = [
            {
                "section_type": "results",
                "heading": "Results",
                "text": "The solubility increased from 1.0 to 5.2 mg/mL." * 5,
            }
        ]

        claims, report = extract_claims_from_source(
            sections,
            task_description="Extract only solubility claims",
            analysis_depth="task_focused",
            provider=MockProvider(),
        )

        assert report["blocks_processed"] >= 1
