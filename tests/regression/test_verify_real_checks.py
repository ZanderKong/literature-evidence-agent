"""Regression tests: verify must perform real behavioral checks, not just COUNT >= 0.

These tests demonstrate that the current verify implementation uses weak assertions
that always pass regardless of actual data state.
"""

import sqlite3

import pytest


class TestVerifyWeakChecks:
    """Verify should fail on empty/missing data but currently passes."""

    def test_verify_passes_on_empty_database(self, tmp_workspace, monkeypatch):
        """Empty DB with just tables should NOT pass verify, but currently does."""
        import os

        db_path = tmp_workspace / "evidence.sqlite"
        os.environ["EVIDENCE_AGENT_DB_PATH"] = str(db_path)

        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE IF NOT EXISTS sources (source_id TEXT)")
        conn.commit()
        conn.close()

        from evidence_agent.cli import _verify_round1

        failed = False
        try:
            _verify_round1()
        except SystemExit:
            failed = True

        assert failed, (
            "FLAW: verify passed on an empty database. "
            "Checks like COUNT >= 0 make this always pass."
        )

    def test_verify_passes_with_zero_claims_and_locators(self, tmp_workspace, monkeypatch):
        """verify should fail when there are no claims to trace, but currently passes."""
        import os

        import evidence_agent.config
        import importlib

        os.environ["EVIDENCE_AGENT_WORKSPACE"] = str(tmp_workspace)
        importlib.reload(evidence_agent.config)
        import evidence_agent.database.connection
        importlib.reload(evidence_agent.database.connection)

        from evidence_agent.config import config
        config.ensure_directories()

        from evidence_agent.database.migrations import migrate
        migrate()

        from evidence_agent.cli import _verify_round1

        failed = False
        try:
            _verify_round1()
        except SystemExit as e:
            failed = e.code != 0

        assert failed, (
            "FLAW: verify passed on a database with zero claims. "
            "quote_traceability uses COUNT >= 0 which always passes."
        )

    def test_verify_passes_with_empty_review_decisions(self, tmp_workspace, monkeypatch):
        """verify should fail when no reviews have been done, but currently passes."""
        import os

        import evidence_agent.config
        import importlib

        os.environ["EVIDENCE_AGENT_WORKSPACE"] = str(tmp_workspace)
        importlib.reload(evidence_agent.config)
        import evidence_agent.database.connection
        importlib.reload(evidence_agent.database.connection)

        from evidence_agent.config import config
        config.ensure_directories()

        from evidence_agent.database.migrations import migrate
        migrate()

        from evidence_agent.cli import _verify_round1

        failed = False
        try:
            _verify_round1()
        except SystemExit as e:
            failed = e.code != 0

        assert failed, (
            "FLAW: review_workflow check only does SELECT COUNT(*), "
            "which succeeds on an empty table."
        )

    def test_verify_passes_with_fts_table_but_no_approved_claims(self, tmp_workspace, monkeypatch):
        """FTS check should search for actual results, not just check table existence."""
        import os

        import evidence_agent.config
        import importlib

        os.environ["EVIDENCE_AGENT_WORKSPACE"] = str(tmp_workspace)
        importlib.reload(evidence_agent.config)
        import evidence_agent.database.connection
        importlib.reload(evidence_agent.database.connection)

        from evidence_agent.config import config
        config.ensure_directories()

        from evidence_agent.database.migrations import migrate
        migrate()

        from evidence_agent.cli import _verify_round1

        failed = False
        try:
            _verify_round1()
        except SystemExit as e:
            failed = e.code != 0

        assert failed, (
            "FLAW: fts_search only checks if table exists, "
            "not whether any approved claims are actually indexed."
        )

    def test_verify_passes_with_migration_version_without_rebuild(self, tmp_workspace, monkeypatch):
        """database_rebuild check must verify actual rebuild, not just migration version."""
        import os

        import evidence_agent.config
        import importlib

        os.environ["EVIDENCE_AGENT_WORKSPACE"] = str(tmp_workspace)
        importlib.reload(evidence_agent.config)
        import evidence_agent.database.connection
        importlib.reload(evidence_agent.database.connection)

        from evidence_agent.config import config
        config.ensure_directories()

        from evidence_agent.database.migrations import migrate
        migrate()

        from evidence_agent.cli import _verify_round1

        failed = False
        try:
            _verify_round1()
        except SystemExit as e:
            failed = e.code != 0

        assert failed, (
            "FLAW: database_rebuild only checks migration version >= 4. "
            "A freshly migrated DB without any rebuild should not pass."
        )
