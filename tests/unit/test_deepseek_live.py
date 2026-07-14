"""DeepSeek live smoke test — requires EVIDENCE_AGENT_LLM_API_KEY.

Run with: pytest -m live_deepseek -q
Skip in normal CI.
"""

import dataclasses
import os

import pytest

pytestmark = pytest.mark.live_deepseek


def test_deepseek_api_smoke():
    """Verify DeepSeek API call succeeds and returns valid claims."""
    api_key = os.getenv("EVIDENCE_AGENT_LLM_API_KEY")
    if not api_key:
        pytest.skip("EVIDENCE_AGENT_LLM_API_KEY not set")

    from evidence_agent.extraction.provider import (
        DeepSeekProvider, ExtractionRequest,
    )

    provider = DeepSeekProvider(api_key=api_key)
    request = ExtractionRequest(
        section_id="SEC-test-001",
        section_text=(
            "This study investigated the solubility enhancement of curcumin "
            "using HP-beta-CD. The solubility increased by 3.2-fold at 25 "
            "degrees C. This suggests that the inclusion complex was "
            "successfully formed through hydrogen bonding."
        ),
        task_description="Extract all author claims from this section",
        section_heading="Results and Discussion",
        page_start=1,
        page_end=1,
        section_type="body",
    )
    response = provider.extract_claims(request)

    if response.error:
        assert response.error == "", (
            f"DeepSeek API error: {response.error}"
        )

    assert len(response.claims) > 0, "Must return at least 1 claim"
    for claim in response.claims:
        assert claim.get("source_quote"), "Each claim must have source_quote"
        assert claim.get("claim_type") in (
            "background_statement", "method_statement",
            "reported_observation", "reported_result",
            "author_interpretation", "author_conclusion",
            "author_hypothesis", "author_limitation", "future_work",
        ), f"Invalid claim_type: {claim.get('claim_type')}"

        quote = claim.get("source_quote", "").strip()
        if quote:
            assert _quote_in_text(quote, request.section_text), (
                f"Quote not found in section text: {quote[:80]}"
            )

    assert response.model_name, "model_name must not be empty"
    assert response.prompt_version, "prompt_version must not be empty"


def test_deepseek_no_key_leaks_in_output():
    """API key must not appear in response."""
    api_key = os.getenv("EVIDENCE_AGENT_LLM_API_KEY")
    if not api_key:
        pytest.skip("EVIDENCE_AGENT_LLM_API_KEY not set")

    from evidence_agent.extraction.provider import (
        DeepSeekProvider, ExtractionRequest,
    )

    provider = DeepSeekProvider(api_key=api_key)
    request = ExtractionRequest(
        section_id="SEC-leak-test",
        section_text="curcumin solubility at room temperature.",
        task_description="Extract claims",
        section_heading="Test",
        page_start=1,
        page_end=1,
    )
    response = provider.extract_claims(request)

    if response.error:
        pytest.skip(f"DeepSeek API error: {response.error}")

    response_dict = dataclasses.asdict(response)
    response_str = str(response_dict)
    assert api_key not in response_str, "API key leaked in response!"


def _quote_in_text(quote: str, section_text: str) -> bool:
    """Check if quote appears in section text (fuzzy)."""
    quote_words = [w for w in quote.split() if len(w) > 3]
    if not quote_words:
        return True
    text_lower = section_text.lower()
    matched = sum(1 for w in quote_words if w.lower() in text_lower)
    return matched / len(quote_words) >= 0.5
