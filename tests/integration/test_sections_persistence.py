"""Integration tests: source sections must be persisted to the database.

Current implementation:
- PDF parsing writes sections to files (parsed/sections.jsonl)
- But analyse() does NOT persist sections to source_sections table
- This means review edit validation cannot reliably access source text
"""

import json
from pathlib import Path

import pytest


class TestSectionsPersistence:
    """Parsed sections must be written to the source_sections database table."""

    @pytest.fixture
    def setup(self, runtime_context):
        """Setup migrated workspace with an ingested source."""
        from evidence_agent.database.connection import get_connection

        src_dir = runtime_context.sources_dir / "SRC-test-sec"
        src_dir.mkdir(parents=True, exist_ok=True)

        manifest = {
            "source_id": "SRC-test-sec",
            "source_type": "journal_article",
            "title": "Test Sections Article",
            "original_file_sha256": "sha256:sections_test",
            "created_at": "2025-01-01T00:00:00",
            "updated_at": "2025-01-01T00:00:00",
        }
        (src_dir / "manifest.json").write_text(json.dumps(manifest))

        import shutil
        orig_dir = src_dir / "original"
        orig_dir.mkdir(exist_ok=True)

        sample_pdf = (
            Path(__file__).resolve().parent.parent / "fixtures" / "sample_article.pdf"
        )
        if sample_pdf.exists():
            shutil.copy(sample_pdf, orig_dir / "main.pdf")

        with get_connection() as conn:
            conn.execute(
                "INSERT INTO sources (source_id, source_type, title, "
                "authors_json, original_file_sha256, origin_scope, "
                "scientific_verification_status, created_at, updated_at) "
                "VALUES ('SRC-test-sec', 'journal_article', 'Test', "
                "'[]', 'sha256:sections_test', 'external', 'unverified', "
                "'2025-01-01T00:00:00', '2025-01-01T00:00:00')"
            )

        return runtime_context

    def test_analyse_does_not_persist_sections_to_db(self, setup):
        """After analyse, source_sections DB table should have data."""
        from evidence_agent.application.analyse import analyse_source
        from evidence_agent.database.connection import get_connection

        analyse_source("SRC-test-sec", provider_name="mock")

        with get_connection(read_only=True) as conn:
            cursor = conn.execute(
                "SELECT COUNT(*) as cnt FROM source_sections WHERE source_id = ?",
                ("SRC-test-sec",),
            )
            count = cursor.fetchone()["cnt"]

        assert count > 0, (
            f"Sections persisted: {count}. analyse() should persist parsed "
            f"sections to the source_sections table after parsing."
        )
    def test_parser_writes_sections_to_files_but_not_db(self, setup):
        """parse_source() persists sections to both files and DB."""
        from evidence_agent.application.parse import parse_source
        from evidence_agent.database.connection import get_connection

        result = parse_source("SRC-test-sec")
        assert result.sections_persisted > 0

        with get_connection(read_only=True) as conn:
            db_count = conn.execute(
                "SELECT COUNT(*) FROM source_sections WHERE source_id=?",
                ("SRC-test-sec",),
            ).fetchone()[0]
        assert db_count > 0, f"DB has {db_count} sections"
