"""Database connection management."""

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from evidence_agent.config import config


def get_db_path() -> Path:
    """Get the database file path from config."""
    return config.db_path


def connect(db_path: Path | None = None, *, read_only: bool = False) -> sqlite3.Connection:
    """Create a database connection with required pragmas."""
    path = db_path or get_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    if read_only:
        uri = f"file:{path}?mode=ro"
        conn = sqlite3.connect(uri, uri=True)
        conn.row_factory = sqlite3.Row
        # Read-only: skip write pragmas
        try:
            conn.execute("PRAGMA foreign_keys = ON")
        except sqlite3.OperationalError:
            pass
        return conn

    conn = sqlite3.connect(str(path))
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    conn.row_factory = sqlite3.Row
    return conn


@contextmanager
def get_connection(
    db_path: Path | None = None, *, read_only: bool = False
) -> Iterator[sqlite3.Connection]:
    """Context manager for database connections with auto-commit/close."""
    conn = connect(db_path, read_only=read_only)
    try:
        yield conn
        if not read_only:
            conn.commit()
    except Exception:
        if not read_only:
            conn.rollback()
        raise
    finally:
        conn.close()


@contextmanager
def transaction(db_path: Path | None = None) -> Iterator[sqlite3.Connection]:
    """Context manager for explicit transaction handling."""
    conn = connect(db_path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
