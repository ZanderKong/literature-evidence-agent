"""Unit tests for database migrations and constraints."""

import sqlite3
import tempfile
from pathlib import Path

import pytest

from evidence_agent.database.connection import connect, get_connection, transaction
from evidence_agent.database.migrations import (
    check,
    get_current_version,
    migrate,
    rebuild,
)


@pytest.fixture
def tmp_db() -> Path:
    """Create a temporary database file path."""
    with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as f:
        path = Path(f.name)
    yield path
    # Cleanup
    path.unlink(missing_ok=True)
    # Also clean up WAL/SHM files
    for ext in (".sqlite-wal", ".sqlite-shm"):
        p = path.with_suffix(ext)
        p.unlink(missing_ok=True)


# ── Migration tests ────────────────────────────────────

class TestMigrations:
    """Test database migration workflow."""

    def test_empty_db_migration(self, tmp_db: Path):
        """Migrate an empty database and verify all tables exist."""
        applied = migrate(tmp_db)
        assert len(applied) == 5
        assert applied[0] == (1, "001_initial.sql")
        assert applied[1] == (2, "002_fts.sql")
        assert applied[2] == (3, "003_constraints.sql")
        assert applied[3] == (4, "004_review_batches.sql")
        assert applied[4] == (5, "005_review_integrity.sql")

        conn = connect(tmp_db)
        version = get_current_version(conn)
        conn.close()
        assert version == 5

    def test_repeat_migration_is_idempotent(self, tmp_db: Path):
        """Running migration twice should not error or duplicate."""
        first = migrate(tmp_db)
        assert len(first) == 5

        second = migrate(tmp_db)
        assert len(second) == 0  # No new migrations

        conn = connect(tmp_db)
        version = get_current_version(conn)
        conn.close()
        assert version == 5

    def test_all_tables_exist(self, tmp_db: Path):
        """Verify all expected tables are created."""
        migrate(tmp_db)

        conn = connect(tmp_db)
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        tables = {row[0] for row in cursor.fetchall()}
        conn.close()

        expected = {
            "schema_migrations",
            "research_tasks",
            "sources",
            "source_assets",
            "source_sections",
            "source_claims",
            "claim_locators",
            "entities",
            "claim_entity_links",
            "processing_runs",
            "review_decisions",
            "claim_revisions",
        }
        assert expected.issubset(tables)

    def test_fts_tables_exist(self, tmp_db: Path):
        """Verify FTS5 tables are created."""
        migrate(tmp_db)

        conn = connect(tmp_db)
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name LIKE '%_fts%' ORDER BY name"
        )
        fts_tables = {row[0] for row in cursor.fetchall()}
        conn.close()

        assert "source_fts" in fts_tables
        assert "claim_fts" in fts_tables


# ── Constraint tests ───────────────────────────────────

class TestConstraints:
    """Test database constraints work correctly."""

    @pytest.fixture
    def migrated_db(self, tmp_db: Path) -> Path:
        """Fixture with a migrated database."""
        migrate(tmp_db)
        return tmp_db

    def test_unique_sha256_enforced(self, migrated_db: Path):
        """Same SHA-256 cannot create two sources."""
        conn = connect(migrated_db)

        sha = "a" * 64
        now = "2026-07-10T00:00:00"

        conn.execute(
            "INSERT INTO sources (source_id, source_type, original_file_sha256, "
            "created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
            ("SRC-000001", "journal_article", sha, now, now),
        )
        conn.commit()

        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO sources (source_id, source_type, original_file_sha256, "
                "created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                ("SRC-000002", "journal_article", sha, now, now),
            )
            conn.commit()

        conn.close()

    def test_origin_scope_must_be_external(self, migrated_db: Path):
        """Cannot insert a source with origin_scope != external."""
        conn = connect(migrated_db)

        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO sources (source_id, source_type, original_file_sha256, "
                "origin_scope, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
                ("SRC-000001", "journal_article", "a" * 64, "internal",
                 "2026-07-10", "2026-07-10"),
            )

        conn.close()

    def test_invalid_scientific_status_fails(self, migrated_db: Path):
        """Cannot set scientific_verification_status to invalid values."""
        conn = connect(migrated_db)

        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO sources (source_id, source_type, original_file_sha256, "
                "scientific_verification_status, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                ("SRC-000001", "journal_article", "a" * 64,
                 "confirmed", "2026-07-10", "2026-07-10"),
            )

        conn.close()

    def test_claim_origin_must_be_external(self, migrated_db: Path):
        """Cannot insert a claim with origin_scope != external."""
        conn = connect(migrated_db)
        now = "2026-07-10T00:00:00"
        sha = "a" * 64

        # First, create a valid source
        conn.execute(
            "INSERT INTO sources (source_id, source_type, original_file_sha256, "
            "created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
            ("SRC-000001", "journal_article", sha, now, now),
        )

        # Try to insert claim with origin_scope = internal
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO source_claims (claim_id, source_id, claim_type, "
                "source_quote, faithful_paraphrase, evidence_basis_description, "
                "origin_scope, quote_match_status, created_by_run_id, "
                "created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                ("CLM-000001", "SRC-000001", "reported_result",
                 "quote", "paraphrase", "basis", "internal", "exact",
                 "RUN-000001", now, now),
            )

        conn.close()

    def test_foreign_key_cascade(self, migrated_db: Path):
        """Deleting a source should cascade to its sections."""
        conn = connect(migrated_db)
        now = "2026-07-10T00:00:00"
        sha = "a" * 64

        conn.execute(
            "INSERT INTO sources (source_id, source_type, original_file_sha256, "
            "created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
            ("SRC-000001", "journal_article", sha, now, now),
        )

        conn.execute(
            "INSERT INTO source_sections (section_id, source_id, section_type, "
            "sequence_number, text, parser_name, parser_version, text_sha256) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ("SEC-000001", "SRC-000001", "introduction", 1,
             "text", "pdfplumber", "1.0", "b" * 64),
        )
        conn.commit()

        # Verify section exists
        cursor = conn.execute(
            "SELECT COUNT(*) FROM source_sections WHERE source_id = ?",
            ("SRC-000001",),
        )
        assert cursor.fetchone()[0] == 1

        # Delete source
        conn.execute("DELETE FROM sources WHERE source_id = ?", ("SRC-000001",))
        conn.commit()

        # Section should be gone too
        cursor = conn.execute(
            "SELECT COUNT(*) FROM source_sections WHERE source_id = ?",
            ("SRC-000001",),
        )
        assert cursor.fetchone()[0] == 0

        conn.close()

    def test_file_size_non_negative(self, migrated_db: Path):
        """Cannot insert an asset with negative file_size."""
        conn = connect(migrated_db)
        now = "2026-07-10T00:00:00"
        sha = "a" * 64

        conn.execute(
            "INSERT INTO sources (source_id, source_type, original_file_sha256, "
            "created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
            ("SRC-000001", "journal_article", sha, now, now),
        )

        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO source_assets (asset_id, source_id, asset_type, "
                "relative_path, mime_type, sha256, file_size, acquired_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                ("AST-000001", "SRC-000001", "main_document",
                 "original/test.pdf", "application/pdf", "c" * 64, -1, now),
            )

        conn.close()


# ── Check tests ────────────────────────────────────────

class TestDatabaseCheck:
    """Test the db check functionality."""

    def test_check_on_migrated_db(self, tmp_db: Path):
        """Check should pass on a correctly migrated database."""
        migrate(tmp_db)
        results = check(tmp_db)

        assert results["version"] == 5
        assert results["integrity"] == "ok"
        assert results["foreign_keys"] == "ok"
        assert len(results["tables"]) >= 12
        assert "source_fts" in results["fts_tables"]
        assert "claim_fts" in results["fts_tables"]
        assert len(results["errors"]) == 0

    def test_check_on_empty_db(self, tmp_db: Path):
        """Check on empty (non-existent) db should report version 0."""
        # File doesn't exist yet — check should create it
        results = check(tmp_db)
        assert results["version"] == 0


# ── Rebuild tests ──────────────────────────────────────

class TestRebuild:
    """Test database rebuild functionality."""

    def test_rebuild_from_empty(self, tmp_db: Path):
        """Rebuild on empty should work."""
        applied = rebuild(tmp_db)
        assert len(applied) == 5

    def test_rebuild_after_migration(self, tmp_db: Path):
        """Rebuild after migration should drop and recreate."""
        migrate(tmp_db)

        conn = connect(tmp_db)
        now = "2026-07-10T00:00:00"
        sha = "d" * 64
        conn.execute(
            "INSERT INTO sources (source_id, source_type, original_file_sha256, "
            "created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
            ("SRC-000001", "journal_article", sha, now, now),
        )
        conn.commit()
        conn.close()

        # Rebuild
        applied = rebuild(tmp_db)
        assert len(applied) == 5

        # Data should be gone
        conn = connect(tmp_db)
        cursor = conn.execute("SELECT COUNT(*) FROM sources")
        assert cursor.fetchone()[0] == 0
        conn.close()


# ── Connection tests ───────────────────────────────────

class TestConnection:
    """Test connection management."""

    def test_connect_creates_parent_dir(self, tmp_path: Path):
        """Connection should create parent directories."""
        db_path = tmp_path / "subdir" / "test.sqlite"
        conn = connect(db_path)
        conn.close()
        assert db_path.exists()

    def test_get_connection_context(self, tmp_db: Path):
        """Context manager should auto-commit and close."""
        migrate(tmp_db)

        with get_connection(tmp_db) as conn:
            conn.execute(
                "INSERT INTO sources (source_id, source_type, "
                "original_file_sha256, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?)",
                ("SRC-000001", "journal_article", "x" * 64,
                 "2026-07-10", "2026-07-10"),
            )

        # Should be committed
        conn = connect(tmp_db, read_only=True)
        cursor = conn.execute("SELECT COUNT(*) FROM sources")
        assert cursor.fetchone()[0] == 1
        conn.close()

    def test_transaction_rollback(self, tmp_db: Path):
        """Transaction should rollback on exception."""
        migrate(tmp_db)

        try:
            with transaction(tmp_db) as conn:
                conn.execute(
                    "INSERT INTO sources (source_id, source_type, "
                    "original_file_sha256, created_at, updated_at) "
                    "VALUES (?, ?, ?, ?, ?)",
                    ("SRC-000001", "journal_article", "x" * 64,
                     "2026-07-10", "2026-07-10"),
                )
                raise RuntimeError("force rollback")
        except RuntimeError:
            pass

        # Should be rolled back
        conn = connect(tmp_db, read_only=True)
        cursor = conn.execute("SELECT COUNT(*) FROM sources")
        assert cursor.fetchone()[0] == 0
        conn.close()

    def test_read_only_connection(self, tmp_db: Path):
        """Read-only connection should prevent writes."""
        migrate(tmp_db)
        conn = connect(tmp_db, read_only=True)

        with pytest.raises(sqlite3.OperationalError):
            conn.execute(
                "INSERT INTO sources (source_id, source_type, "
                "original_file_sha256, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?)",
                ("SRC-000001", "journal_article", "x" * 64,
                 "2026-07-10", "2026-07-10"),
            )

        conn.close()
