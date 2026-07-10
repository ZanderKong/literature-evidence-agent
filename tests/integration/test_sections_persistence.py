"""Integration tests: source sections must be persisted to the database.

Current implementation:
- PDF parsing writes sections to files (parsed/sections.jsonl)
- But analyse() does NOT persist sections to source_sections table
- This means review edit validation cannot reliably access source text
"""

import json
import os
from pathlib import Path

import pytest


class TestSectionsPersistence:
    """Parsed sections must be written to the source_sections database table."""

    @pytest.fixture
    def setup(self, tmp_workspace):
        """Setup migrated workspace with an ingested source."""
        import importlib
        import evidence_agent.config

        os.environ["EVIDENCE_AGENT_WORKSPACE"] = str(tmp_workspace)
        importlib.reload(evidence_agent.config)
        import evidence_agent.database.connection
        importlib.reload(evidence_agent.database.connection)

        from evidence_agent.config import config
        config.ensure_directories()

        from evidence_agent.database.migrations import migrate
        migrate()

        # Create a source package
        src_dir = config.sources_dir / "SRC-test-sec"
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

        # Copy a sample PDF
        import shutil
        fixtures_pdf = tmp_workspace.parent.parent / "tests" / "fixtures" / "sample_article.pdf"
        # Use a different path - we need to make the orig dir
        # Actually, let's just create a minimal PDF with text
        orig_dir = src_dir / "original"
        orig_dir.mkdir(exist_ok=True)

        # Use the real sample article PDF
        sample_pdf = (
            Path(__file__).resolve().parent.parent / "fixtures" / "sample_article.pdf"
        )
        if sample_pdf.exists():
            shutil.copy(sample_pdf, orig_dir / "main.pdf")

        # Insert source into DB
        from evidence_agent.database.connection import get_connection
        with get_connection() as conn:
            conn.execute(
                "INSERT INTO sources (source_id, source_type, title, "
                "original_file_sha256, origin_scope, "
                "scientific_verification_status, created_at, updated_at) "
                "VALUES ('SRC-test-sec', 'journal_article', 'Test', "
                "'sha256:sections_test', 'external', 'unverified', "
                "'2025-01-01T00:00:00', '2025-01-01T00:00:00')"
            )

        return config

    def test_analyse_does_not_persist_sections_to_db(self, setup):
        """After analyse, source_sections DB table should have data — but currently doesn't."""
        from evidence_agent.database.connection import get_connection
        from evidence_agent.application.analyse import analyse_source

        try:
            result = analyse_source("SRC-test-sec", provider_name="mock")
        except Exception:
            # Analyse may fail for various reasons on a minimally set up source
            pass

        with get_connection(read_only=True) as conn:
            cursor = conn.execute(
                "SELECT COUNT(*) as cnt FROM source_sections WHERE source_id = ?",
                ("SRC-test-sec",),
            )
            count = cursor.fetchone()["cnt"]

        assert count > 0, (
            f"FLAW: 0 sections persisted to source_sections table ({count}). "
            f"analyse() currently writes sections to JSONL files only, "
            f"not to the database."
        )

    def test_parser_writes_sections_to_files_but_not_db(self, setup):
        """Parse writes sections.jsonl but the database should also have them."""
        from evidence_agent.config import config
        from evidence_agent.parsers.pdf import parse_pdf

        package_dir = config.sources_dir / "SRC-test-sec"
        result = parse_pdf("SRC-test-sec", package_dir)

        # Verify the JSONL file exists
        sections_path = package_dir / "parsed" / "sections.jsonl"
        assert sections_path.exists(), "Parse didn't create sections.jsonl"

        sections_from_file = []
        with open(sections_path) as f:
            for line in f:
                if line.strip():
                    sections_from_file.append(json.loads(line))

        assert len(sections_from_file) > 0, "Parse produced 0 sections"

        # Now verify DB has 0 sections (the flaw)
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
