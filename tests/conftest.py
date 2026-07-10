"""Shared pytest fixtures for all tests."""

import importlib
import os
import tempfile
from pathlib import Path

import pytest


def _reload_config(workspace: Path) -> None:
    """Set workspace env var and reload config module."""
    os.environ["EVIDENCE_AGENT_WORKSPACE"] = str(workspace)

    # Reload config so the singleton picks up the new env var
    import evidence_agent.config
    importlib.reload(evidence_agent.config)

    # Also reload modules that import config at module level
    import evidence_agent.database.connection
    importlib.reload(evidence_agent.database.connection)


def _cleanup_config() -> None:
    """Remove env override and reload."""
    os.environ.pop("EVIDENCE_AGENT_WORKSPACE", None)

    import evidence_agent.config
    importlib.reload(evidence_agent.config)

    import evidence_agent.database.connection
    importlib.reload(evidence_agent.database.connection)


@pytest.fixture
def tmp_workspace() -> Path:
    """Create a temporary workspace for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir)
        yield workspace


@pytest.fixture
def migrated_workspace() -> Path:
    """Create a temp workspace with a migrated database.

    Sets EVIDENCE_AGENT_WORKSPACE env var so that all config paths
    point to the temp workspace.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir)
        _reload_config(workspace)

        from evidence_agent.config import config
        config.ensure_directories()

        from evidence_agent.database.migrations import migrate
        migrate()

        yield workspace

        _cleanup_config()
