"""Shared pytest fixtures for all tests.

Uses RuntimeContext + use_context() for proper isolation.
No importlib.reload anywhere.
"""

import tempfile
from pathlib import Path

import pytest

from evidence_agent.runtime import RuntimeContext, use_context


@pytest.fixture
def tmp_workspace() -> Path:
    """Simple temporary directory for tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def runtime_context(tmp_path: Path) -> RuntimeContext:
    """Create an isolated RuntimeContext with migrated database."""
    ws = tmp_path / "lea-ws"
    ws.mkdir()
    ctx = RuntimeContext(str(ws))
    ctx.ensure_directories()

    from evidence_agent.database.migrations import migrate
    migrate(ctx.db_path)

    with use_context(ctx):
        yield ctx


@pytest.fixture
def migrated_workspace(runtime_context: RuntimeContext) -> Path:
    """Backward-compat: returns workspace_path for old tests."""
    return runtime_context.workspace_path
