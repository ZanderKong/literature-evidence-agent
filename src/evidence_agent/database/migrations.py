"""Database migration management."""

import sqlite3
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from evidence_agent.database.connection import connect

# Migration files in order
MIGRATIONS: list[tuple[int, str]] = [
    (1, "001_initial.sql"),
    (2, "002_fts.sql"),
    (3, "003_constraints.sql"),
    (4, "004_review_batches.sql"),
    (5, "005_review_integrity.sql"),
]


def get_migrations_dir() -> Path:
    """Get the migrations directory path."""
    # Look for migrations/ relative to project root
    cwd = Path.cwd()
    candidates = [
        cwd / "migrations",
        cwd.parent / "migrations",
    ]
    for d in candidates:
        if (d / "001_initial.sql").exists():
            return d
    # Fallback: look relative to this file
    this_dir = Path(__file__).resolve().parent
    fallback = this_dir.parent.parent.parent / "migrations"
    if fallback.exists():
        return fallback
    return cwd / "migrations"


def get_current_version(conn: sqlite3.Connection) -> int:
    """Get the current schema version, or 0 if not yet migrated."""
    try:
        cursor = conn.execute(
            "SELECT MAX(version) FROM schema_migrations"
        )
        row = cursor.fetchone()
        return row[0] if row and row[0] is not None else 0
    except sqlite3.OperationalError:
        return 0


def run_migration(conn: sqlite3.Connection, version: int, name: str) -> None:
    """Run a single migration file."""
    migrations_dir = get_migrations_dir()
    path = migrations_dir / name

    if not path.exists():
        raise FileNotFoundError(f"Migration file not found: {path}")

    sql = path.read_text(encoding="utf-8")

    # Split and execute each statement individually to handle
    # ALTER TABLE ADD COLUMN idempotency
    for statement in sql.split(";"):
        statement = statement.strip()
        if not statement:
            continue
        try:
            conn.execute(statement)
        except sqlite3.OperationalError as e:
            err_msg = str(e).lower()
            if "duplicate column name" in err_msg:
                # Column already exists, skip safely
                continue
            raise

    conn.execute(
        "INSERT INTO schema_migrations (version, name) VALUES (?, ?)",
        (version, name),
    )


def migrate(db_path: Path | None = None) -> Sequence[tuple[int, str]]:
    """Run all pending migrations. Returns list of applied migrations."""
    conn = connect(db_path)
    applied: list[tuple[int, str]] = []

    try:
        current = get_current_version(conn)

        for version, name in MIGRATIONS:
            if version > current:
                run_migration(conn, version, name)
                applied.append((version, name))

        conn.commit()
    finally:
        conn.close()

    return applied


def check(db_path: Path | None = None) -> dict[str, Any]:
    """Check database integrity. Returns dict with check results."""
    conn = connect(db_path, read_only=True)
    results: dict[str, Any] = {
        "version": 0,
        "integrity": "unknown",
        "foreign_keys": "unknown",
        "tables": [],
        "fts_tables": [],
        "errors": [],
    }

    try:
        # Schema version
        results["version"] = get_current_version(conn)

        # Integrity check
        cursor = conn.execute("PRAGMA integrity_check")
        row = cursor.fetchone()
        results["integrity"] = row[0] if row else "unknown"

        # Foreign key check
        cursor = conn.execute("PRAGMA foreign_key_check")
        fk_issues = cursor.fetchall()
        results["foreign_keys"] = "ok" if not fk_issues else f"issues: {len(fk_issues)}"

        # Table list
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        results["tables"] = [row[0] for row in cursor.fetchall()]

        # FTS tables
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name LIKE '%_fts%' ORDER BY name"
        )
        results["fts_tables"] = [row[0] for row in cursor.fetchall()]

    except sqlite3.Error as e:
        results["errors"].append(str(e))
    finally:
        conn.close()

    return results


def rebuild(db_path: Path | None = None) -> list[tuple[int, str]]:
    """Drop all tables and re-run all migrations."""
    conn = connect(db_path)
    applied: list[tuple[int, str]] = []

    try:
        # Disable foreign keys temporarily for drop sequence
        conn.execute("PRAGMA foreign_keys = OFF")

        # Get all user tables/views
        cursor = conn.execute(
            "SELECT name, type FROM sqlite_master "
            "WHERE name NOT LIKE 'sqlite_%'"
        )
        rows = cursor.fetchall()

        # Drop FTS5 virtual tables first (they have content tables)
        fts_base_names: set[str] = set()
        for name, _type in rows:
            if _type == "table" and "_fts" in name:
                try:
                    conn.execute(f"DROP TABLE IF EXISTS \"{name}\"")
                except sqlite3.OperationalError:
                    pass
                fts_base_names.add(name)

        # Then drop remaining tables/views (excluding FTS-related ones)
        for name, _type in rows:
            if name not in fts_base_names:
                try:
                    conn.execute(f"DROP TABLE IF EXISTS \"{name}\"")
                except sqlite3.OperationalError:
                    pass

        conn.execute("PRAGMA foreign_keys = ON")

        conn.commit()

        # Re-run all migrations
        for version, name in MIGRATIONS:
            run_migration(conn, version, name)
            applied.append((version, name))

        conn.commit()
    finally:
        conn.close()

    return applied
