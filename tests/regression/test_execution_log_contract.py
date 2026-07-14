"""Regression tests: execution log contract — verify that execution logs
match actual system state.

The current execution log at docs/plans/ROUND1_EXECUTION_LOG.md may claim
tasks as completed when they actually weren't, or use vague statuses
like 'done' without evidence.
"""

from pathlib import Path

import pytest


class TestExecutionLogContract:
    """Execution logs must use defined statuses and match actual state."""

    def test_old_execution_log_exists_and_is_accessible(self):
        """The existing execution log must exist for us to audit it."""
        log_path = Path("docs/plans/ROUND1_EXECUTION_LOG.md")
        if not log_path.exists():
            pytest.skip("ROUND1_EXECUTION_LOG.md not found — may have been renamed")

        content = log_path.read_text()
        assert len(content) > 100, "Execution log is suspiciously short"

    def test_no_future_completion_claims_in_log(self):
        """The log should not claim RC2 tasks as done before RC2 even starts."""
        log_path = Path("docs/plans/ROUND1_EXECUTION_LOG.md")
        if not log_path.exists():
            pytest.skip("ROUND1_EXECUTION_LOG.md not found")

        content = log_path.read_text()

        # RC2-specific task names that should NOT exist in the old log
        rc2_indicators = [
            "review_batches",
            "rebuild_identity",
            "edit_revalidation",
            "golden_set_bilingual",
            "ROUND1_1_RC2",
        ]
        for indicator in rc2_indicators:
            assert indicator.lower() not in content.lower(), (
                f"FLAW: old execution log references RC2 task '{indicator}' "
                f"that hasn't been started yet"
            )

    def test_rc2_execution_log_must_use_defined_statuses(self):
        """The RC2 execution log must use only allowed status values."""
        # We create this expect to fail initially because the log doesn't exist yet
        log_path = Path("docs/plans/ROUND1_1_RC2_EXECUTION_LOG.md")
        assert log_path.exists(), (
            "FLAW: RC2 execution log not yet created. "
            "Should exist with proper status entries."
        )

        content = log_path.read_text()

        allowed_statuses = [
            "not_started", "in_progress", "verified",
            "blocked_external", "failed",
        ]
        forbidden = ["done", "completed", "ok", "finished"]

        for fb in forbidden:
            # Rough check: a line like "- Status: done" would be invalid
            if f"Status: {fb}" in content or f"status: {fb}" in content:
                assert False, (
                    f"FLAW: execution log uses forbidden status '{fb}'. "
                    f"Allowed: {allowed_statuses}"
                )
