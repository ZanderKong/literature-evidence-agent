"""Integration tests for CLI provider selection behavior."""

from typer.testing import CliRunner
import pytest

from evidence_agent.cli import app


runner = CliRunner()


class TestProviderSelection:
    """Provider must be explicitly chosen and validated."""

    def test_unknown_provider_returns_error(self):
        """Unknown provider name must result in error, not silent fallback."""
        result = runner.invoke(
            app,
            ["analyse", "SRC-nonexistent", "--provider", "gpt4"],
        )
        # We expect exit with error (either 2 from ValueError or 5 from analyse)
        assert result.exit_code != 0, (
            f"Unknown provider 'gpt4' should fail, got exit code {result.exit_code}"
        )

    def test_analyse_without_provider_fails_gracefully(self):
        """Omitting --provider should fail with a clear message."""
        result = runner.invoke(
            app,
            ["analyse", "SRC-nonexistent"],
        )
        assert result.exit_code != 0, (
            f"Missing --provider should fail, got exit code {result.exit_code}"
        )

    def test_help_does_not_show_duplicate_rebuild(self):
        """CLI help should not show duplicate 'db rebuild' command."""
        result = runner.invoke(app, ["db", "--help"])
        output = result.stdout

        # Count occurrences of 'rebuild' in the command list
        rebuild_count = output.count("rebuild")
        # Should have exactly 1: rebuild-from-packages
        assert rebuild_count <= 1, (
            f"CLI help shows {rebuild_count} 'rebuild' commands, "
            f"expected maximum 1 (rebuild-from-packages). Output: {output[:500]}"
        )

    def test_mock_provider_does_not_return_irrelevant_claims(self):
        """MockProvider should not return curcumin claims for unrelated text."""
        from evidence_agent.extraction.provider import (
            ExtractionRequest,
            MockProvider,
        )

        provider = MockProvider()
        request = ExtractionRequest(
            task_description="Extract claims",
            section_text=(
                "The tensile strength of the steel alloy was measured to be "
                "850 MPa after quenching in oil at 60 C for 2 hours. "
                "The hardness increased from 32 HRC to 58 HRC. "
                "This indicates that the martensitic transformation was "
                "complete under these processing conditions."
            ),
            section_heading="Results",
            page_start=1,
            page_end=1,
        )
        response = provider.extract_claims(request)

        curcumin_keywords = ["curcumin", "curcum", "HP-beta-CD"]
        for claim in response.claims:
            quote = claim.get("source_quote", "").lower()
            assert not any(kw.lower() in quote for kw in curcumin_keywords), (
                f"MockProvider returned irrelevant claim: {quote[:80]}"
            )
