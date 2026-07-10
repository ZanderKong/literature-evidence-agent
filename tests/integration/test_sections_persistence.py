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
        from evidence_agent.database.connection import get_connection
        from evidence_agent.application.analyse import analyse_source

        result = analyse_source("SRC-test-sec", provider_name="mock")

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
        """Parse writes sections.jsonl but the database should also have them."""
        from evidence_agent.parsers.pdf import parse_pdf

        ctx = setup
        package_dir = ctx.sources_dir / "SRC-test-sec"
        result = parse_pdf("SRC-test-sec", package_dir)

        sections_path = package_dir / "parsed" / "sections.jsonl"
        assert sections_path.exists(), "Parse didn't create sections.jsonl"

        sections_from_file = []
        with open(sections_path) as f:
            for line in f:
                if line.strip():
                    sections_from_file.append(json.loads(line))

        assert len(sections_from_file) > 0, "Parse produced 0 sections"

        from evidence_agent.database.connection import get_connection
        with get_connection(read_only=True) as conn:
            cursor = conn.execute(
                "SELECT COUNT(*) as cnt FROM source_sections WHERE source_id = ?",
                ("SRC-test-sec",),
            )
            db_count = cursor.fetchone()["cnt"]

        assert db_count > 0, (
            f"FLAW: sections.jsonl has {len(sections_from_file)} sections, "
            f"but DB source_sections has {db_count}. "
            f"parse() doesn't persist sections to the database."
        )
