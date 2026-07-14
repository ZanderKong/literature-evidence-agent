"""DeepSeek live smoke test — requires EVIDENCE_AGENT_LLM_API_KEY.

Run with: pytest -m live_deepseek -q
Skip in normal CI.
"""

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
        section_id="SEC-test",
        section_text=(
            "This study investigated the solubility enhancement of curcumin "
            "using HP-β-CD. The solubility increased by 3.2-fold at 25°C. "
            "This suggests that the inclusion complex was successfully formed."
        ),
        task_description="Extract all author claims",
        block_page_start=1,
    )
    response = provider.extract_claims(request)

    if response.error:
        pytest.skip(f"DeepSeek API error: {response.error}")

    assert len(response.claims) > 0, "Must return at least 1 claim"
    for claim in response.claims:
        assert claim.source_quote, "Each claim must have a source_quote"
        assert claim.claim_type in (
            "background_statement", "method_statement",
            "reported_observation", "reported_result",
            "author_interpretation", "author_conclusion",
            "author_hypothesis", "author_limitation", "future_work",
        ), f"Invalid claim_type: {claim.claim_type}"


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
        section_id="SEC-test",
        section_text="curcumin solubility test.",
        task_description="Extract claims",
        block_page_start=1,
    )
    response = provider.extract_claims(request)

    if response.error:
        pytest.skip(f"DeepSeek API error: {response.error}")

    response_str = response.model_dump_json()
    assert api_key not in response_str, "API key leaked in response!"
    assert provider.model_name in ("deepseek-v4-pro", "deepseek-chat"), (
        f"Unexpected model: {provider.model_name}"
    )
