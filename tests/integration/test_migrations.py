"""Integration tests for database migrations."""

import sqlite3
import tempfile
from pathlib import Path

import pytest

from evidence_agent.database.migrations import check, migrate, rebuild


@pytest.fixture
def tmp_db() -> Path:
    """Create a temporary database file path."""
    with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as f:
        path = Path(f.name)
    yield path
    path.unlink(missing_ok=True)
    for ext in (".sqlite-wal", ".sqlite-shm"):
        p = path.with_suffix(ext)
        p.unlink(missing_ok=True)


class TestFullMigrationCycle:
    """Test complete migration, check, rebuild cycle."""

    def test_migrate_check_rebuild_cycle(self, tmp_db: Path):
        """Full cycle: migrate → check → rebuild → check."""
        # Phase 1: Migrate
        applied = migrate(tmp_db)
        assert len(applied) == 5

        # Phase 2: Check
        results = check(tmp_db)
        assert results["integrity"] == "ok"
        assert results["foreign_keys"] == "ok"
        assert results["version"] == 5

        # Phase 3: Add some data
        import sqlite3 as sq
        conn = sq.connect(str(tmp_db))
        conn.execute("PRAGMA foreign_keys = ON")
        now = "2026-07-10T00:00:00"
        conn.execute(
            "INSERT INTO sources (source_id, source_type, original_file_sha256, "
            "created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
            ("SRC-000001", "journal_article", "a" * 64, now, now),
        )
        conn.commit()
        conn.close()

        # Phase 4: Rebuild
        applied = rebuild(tmp_db)
        assert len(applied) == 5

        # Phase 5: Check again
        results = check(tmp_db)
        assert results["integrity"] == "ok"

        # Data should be gone after rebuild
        conn = sq.connect(str(tmp_db))
        cursor = conn.execute("SELECT COUNT(*) FROM sources")
        assert cursor.fetchone()[0] == 0
        conn.close()

    def test_foreign_key_enforcement_across_tables(self, tmp_db: Path):
        """Test that foreign keys are enforced across related tables."""
        migrate(tmp_db)
        conn = sqlite3.connect(str(tmp_db))
        conn.execute("PRAGMA foreign_keys = ON")
        now = "2026-07-10T00:00:00"

        # Create a source
        conn.execute(
            "INSERT INTO sources (source_id, source_type, original_file_sha256, "
            "created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
            ("SRC-000001", "journal_article", "a" * 64, now, now),
        )
        conn.commit()

        # Try to insert a section with non-existent source_id
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO source_sections (section_id, source_id, section_type, "
                "sequence_number, text, parser_name, parser_version, text_sha256) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                ("SEC-000001", "SRC-999999", "introduction", 1,
                 "text", "pdfplumber", "1.0", "b" * 64),
            )

        conn.close()

    def test_unique_section_sequence_per_source(self, tmp_db: Path):
        """Same source_id + sequence_number should be unique."""
        migrate(tmp_db)
        conn = sqlite3.connect(str(tmp_db))
        conn.execute("PRAGMA foreign_keys = ON")
        now = "2026-07-10T00:00:00"

        conn.execute(
            "INSERT INTO sources (source_id, source_type, original_file_sha256, "
            "created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
            ("SRC-000001", "journal_article", "a" * 64, now, now),
        )

        conn.execute(
            "INSERT INTO source_sections (section_id, source_id, section_type, "
            "sequence_number, text, parser_name, parser_version, text_sha256) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ("SEC-000001", "SRC-000001", "introduction", 1,
             "text1", "pdfplumber", "1.0", "b" * 64),
        )

        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO source_sections (section_id, source_id, section_type, "
                "sequence_number, text, parser_name, parser_version, text_sha256) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                ("SEC-000002", "SRC-000001", "methods", 1,
                 "text2", "pdfplumber", "1.0", "c" * 64),
            )

        conn.close()
