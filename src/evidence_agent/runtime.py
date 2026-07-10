"""Runtime context — explicit configuration injection.

Replaces the global config singleton with an explicit RuntimeContext
that can be passed to all services. Falls back to env vars for CLI usage.

Usage:
    ctx = RuntimeContext.from_env()
    conn = ctx.get_connection()
    with ctx.transaction() as conn:
        ...
"""

from __future__ import annotations

import os
import threading as _threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path


class RuntimeContext:
    """Explicit runtime configuration for the evidence agent.

    All paths are resolved to absolute. DB connections use this context's
    db_path unless overridden.
    """

    def __init__(self, workspace_path: Path | str) -> None:
        wp = Path(workspace_path).resolve()
        self._workspace_path = wp

        db_rel = os.getenv("EVIDENCE_AGENT_DB_PATH", "external_evidence/evidence.sqlite")
        self._db_path = wp / db_rel

    # -- Paths ----------------------------------------------------------

    @property
    def workspace_path(self) -> Path:
        return self._workspace_path

    @property
    def db_path(self) -> Path:
        return self._db_path

    @property
    def sources_dir(self) -> Path:
        return self._workspace_path / "external_evidence" / "sources"

    @property
    def review_dir(self) -> Path:
        return self._workspace_path / "external_evidence" / "review"

    @property
    def exports_dir(self) -> Path:
        return self._workspace_path / "external_evidence" / "exports"

    @property
    def logs_dir(self) -> Path:
        return self._workspace_path / "external_evidence" / "logs"

    @property
    def backups_dir(self) -> Path:
        return self._workspace_path / "external_evidence" / "backups"

    # -- Directory setup ------------------------------------------------

    def ensure_directories(self) -> None:
        d: Path
        for d in [
            self._db_path.parent,
            self.sources_dir,
            self.review_dir,
            self.exports_dir,
            self.logs_dir,
            self.backups_dir,
        ]:
            d.mkdir(parents=True, exist_ok=True)

    # -- Factory --------------------------------------------------------

    @classmethod
    def from_env(cls) -> RuntimeContext:
        """Create from EVIDENCE_AGENT_WORKSPACE environment variable."""
        ws = os.getenv("EVIDENCE_AGENT_WORKSPACE", "workspace")
        return cls(ws)


# ----------------------------------------------------------------------
# Thread-local stack for implicit context (backward compat)
# ----------------------------------------------------------------------

_stack: _threading.local = _threading.local()


def get_current_context() -> RuntimeContext:
    """Get the current RuntimeContext from the thread-local stack.

    Falls back to from_env() if no context is set.
    from_env() is called fresh each time — no caching.
    """
    ctx = get_explicit_context()
    if ctx is not None:
        return ctx
    return RuntimeContext.from_env()


def get_explicit_context() -> RuntimeContext | None:
    """Get the explicitly set context, or None if never set."""
    ctx = getattr(_stack, "context", None)
    return ctx if isinstance(ctx, RuntimeContext) else None


def set_current_context(ctx: RuntimeContext) -> None:
    """Set the current thread-local RuntimeContext."""
    _stack.context = ctx


def clear_current_context() -> None:
    """Clear the thread-local context (next call will use from_env)."""
    try:
        del _stack.context
    except AttributeError:
        pass


@contextmanager
def use_context(ctx: RuntimeContext) -> Iterator[RuntimeContext]:
    """Temporarily set the current context with proper cleanup."""
    old = get_explicit_context()
    set_current_context(ctx)
    try:
        yield ctx
    finally:
        if old is None:
            clear_current_context()
        else:
            set_current_context(old)
