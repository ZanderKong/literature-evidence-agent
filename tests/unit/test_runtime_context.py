"""Unit tests for RuntimeContext."""

import os
from pathlib import Path

import pytest

from evidence_agent.runtime import (
    RuntimeContext,
    clear_current_context,
    get_current_context,
    get_explicit_context,
    set_current_context,
    use_context,
)


class TestRuntimeContext:
    """Test RuntimeContext creation and path derivation."""

    def test_from_env_default(self, monkeypatch):
        monkeypatch.delenv("EVIDENCE_AGENT_WORKSPACE", raising=False)
        ctx = RuntimeContext.from_env()
        assert "workspace" in str(ctx.workspace_path)

    def test_from_env_custom(self, monkeypatch, tmp_path):
        monkeypatch.setenv("EVIDENCE_AGENT_WORKSPACE", str(tmp_path))
        ctx = RuntimeContext.from_env()
        assert str(tmp_path.resolve()) == str(ctx.workspace_path)

    def test_db_path_default(self, monkeypatch, tmp_path):
        monkeypatch.delenv("EVIDENCE_AGENT_DB_PATH", raising=False)
        ctx = RuntimeContext(str(tmp_path))
        assert ctx.db_path == tmp_path.resolve() / "external_evidence" / "evidence.sqlite"

    def test_db_path_custom(self, monkeypatch, tmp_path):
        monkeypatch.setenv("EVIDENCE_AGENT_DB_PATH", "custom/db.sqlite")
        ctx = RuntimeContext(str(tmp_path))
        assert ctx.db_path.name == "db.sqlite"

    def test_derived_paths(self, tmp_path):
        ctx = RuntimeContext(str(tmp_path))
        assert "sources" in str(ctx.sources_dir)
        assert "review" in str(ctx.review_dir)
        assert "exports" in str(ctx.exports_dir)

    def test_ensure_directories(self, tmp_path):
        ctx = RuntimeContext(str(tmp_path))
        ctx.ensure_directories()
        assert ctx.db_path.parent.exists()
        assert ctx.sources_dir.exists()
        assert ctx.review_dir.exists()


class TestContextStack:
    """Test thread-local context stack operations."""

    def test_no_explicit_context_returns_none(self):
        clear_current_context()
        assert get_explicit_context() is None

    def test_set_and_get_context(self, tmp_path):
        ctx = RuntimeContext(str(tmp_path))
        set_current_context(ctx)
        assert get_current_context().workspace_path == ctx.workspace_path
        clear_current_context()

    def test_clear_context(self, tmp_path):
        ctx = RuntimeContext(str(tmp_path))
        set_current_context(ctx)
        assert get_explicit_context() is not None
        clear_current_context()
        assert get_explicit_context() is None

    def test_use_context_restores_previous(self, tmp_path):
        ctx_a = RuntimeContext(str(tmp_path / "a"))
        ctx_b = RuntimeContext(str(tmp_path / "b"))
        set_current_context(ctx_a)

        with use_context(ctx_b):
            assert get_current_context().workspace_path == ctx_b.workspace_path

        assert get_current_context().workspace_path == ctx_a.workspace_path
        clear_current_context()

    def test_use_context_clears_when_no_previous(self):
        clear_current_context()
        ctx = RuntimeContext("workspace")
        with use_context(ctx):
            assert get_explicit_context() is not None
        assert get_explicit_context() is None

    def test_nested_use_context(self, tmp_path):
        clear_current_context()
        ctx_a = RuntimeContext(str(tmp_path / "a"))
        ctx_b = RuntimeContext(str(tmp_path / "b"))

        with use_context(ctx_a):
            assert get_current_context().workspace_path == ctx_a.workspace_path
            with use_context(ctx_b):
                assert get_current_context().workspace_path == ctx_b.workspace_path
            assert get_current_context().workspace_path == ctx_a.workspace_path
        assert get_explicit_context() is None

    def test_get_current_context_falls_back_to_env(self, monkeypatch, tmp_path):
        clear_current_context()
        monkeypatch.setenv("EVIDENCE_AGENT_WORKSPACE", str(tmp_path))
        ctx = get_current_context()
        assert "workspace" in str(ctx.workspace_path) or str(tmp_path.resolve()) in str(ctx.workspace_path)

    def test_explicit_ctx_over_env(self, monkeypatch, tmp_path):
        monkeypatch.setenv("EVIDENCE_AGENT_WORKSPACE", "/fake/path")
        explicit = RuntimeContext(str(tmp_path))
        set_current_context(explicit)
        ctx = get_current_context()
        assert ctx.workspace_path == explicit.workspace_path
        clear_current_context()
