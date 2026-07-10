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
        for d in [
            self._db_path.parent,
            self.sources_dir,
            self.review_dir,
            self.exports_dir,
            self.logs_dir,
            self.backups_dir,
        ]:
            d.mkdir(parents=True, exist_ok=True)

    # -- DB connection helpers ------------------------------------------

    def get_connection(self, *, read_only: bool = False):
        """Get a DB connection using this context's db_path."""
        from evidence_agent.database.connection import connect
        return connect(self._db_path, read_only=read_only)

    @contextmanager
    def transaction(self):
        """Context manager for explicit transaction."""
        from evidence_agent.database.connection import connect
        conn = connect(self._db_path)
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    # -- Factory --------------------------------------------------------

    @classmethod
    def from_env(cls) -> RuntimeContext:
        """Create from EVIDENCE_AGENT_WORKSPACE environment variable."""
        ws = os.getenv("EVIDENCE_AGENT_WORKSPACE", "workspace")
        return cls(ws)


# Thread-local stack for implicit context (backward compat during migration)

_stack: _threading.local = _threading.local()


def get_current_context() -> RuntimeContext:
    """Get the current RuntimeContext from the thread-local stack.
    Falls back to from_env() if no context is set.
    """
    try:
        return _stack.context  # type: ignore[attr-defined]
    except AttributeError:
        ctx = RuntimeContext.from_env()
        _stack.context = ctx
        return ctx


def set_current_context(ctx: RuntimeContext) -> None:
    """Set the current thread-local RuntimeContext."""
    _stack.context = ctx


@contextmanager
def use_context(ctx: RuntimeContext) -> Iterator[RuntimeContext]:
    """Temporarily set the current context."""
    old = get_current_context()
    set_current_context(ctx)
    try:
        yield ctx
    finally:
        set_current_context(old)
