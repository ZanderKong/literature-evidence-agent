"""Unit tests for file import and hashing."""

import tempfile
from pathlib import Path

from evidence_agent.ingest.files import import_pdf, validate_file
from evidence_agent.ingest.hashing import sha256_file

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures"


class TestValidateFile:
    """Test file validation."""

    def test_valid_pdf(self):
        path = FIXTURES_DIR / "sample_article.pdf"
        result = validate_file(path)
        assert result["valid"] is True
        assert result["mime_type"] == "application/pdf"
        assert result["file_size"] > 0

    def test_file_not_found(self):
        path = Path("/nonexistent/file.pdf")
        result = validate_file(path)
        assert result["valid"] is False
        assert "not found" in result["error"].lower()

    def test_empty_file(self):
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            pass  # Empty file
        path = Path(f.name)
        result = validate_file(path)
        assert result["valid"] is False
        assert "empty" in result["error"].lower()
        path.unlink()

    def test_not_pdf_magic(self):
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            f.write(b"Not a PDF file\nJust some text")
        path = Path(f.name)
        result = validate_file(path)
        assert result["valid"] is False
        assert "not a valid pdf" in result["error"].lower()
        path.unlink()

    def test_corrupted_pdf(self):
        """PDF with magic bytes but no EOF marker."""
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            f.write(b"%PDF-1.4\nSome corrupted content without EOF")
        path = Path(f.name)
        result = validate_file(path)
        assert result["valid"] is False
        assert "corrupted" in result["error"].lower()
        path.unlink()


class TestImportPdf:
    """Test PDF import workflow."""

    def test_import_valid_pdf(self, migrated_workspace):
        path = FIXTURES_DIR / "sample_article.pdf"
        result = import_pdf(path)
        assert result["is_new"] is True
        assert result["source_id"].startswith("SRC-")
        assert result["package_dir"].exists()
        assert result["sha256"]
        assert result["file_size"] > 0

        # Verify manifest
        manifest = result["package_dir"] / "manifest.json"
        assert manifest.exists()

        import json
        data = json.loads(manifest.read_text())
        assert data["source_id"] == result["source_id"]
        assert data["origin_scope"] == "external"

    def test_import_idempotent(self, migrated_workspace):
        """Importing the same file twice returns the same source_id."""
        path = FIXTURES_DIR / "sample_article.pdf"

        first = import_pdf(path)
        second = import_pdf(path)

        assert first["source_id"] == second["source_id"]
        assert second["is_new"] is False

    def test_import_two_different_pdfs(self, migrated_workspace):
        """Two different PDFs get different source_ids."""
        path1 = FIXTURES_DIR / "sample_article.pdf"
        path2 = FIXTURES_DIR / "sample_article_2.pdf"

        result1 = import_pdf(path1)
        result2 = import_pdf(path2)

        assert result1["source_id"] != result2["source_id"]
        assert result1["sha256"] != result2["sha256"]


class TestHashing:
    """Test SHA-256 hashing."""

    def test_sha256_file(self):
        path = FIXTURES_DIR / "sample_article.pdf"
        h1 = sha256_file(path)
        h2 = sha256_file(path)
        assert len(h1) == 64
        assert h1 == h2  # Deterministic

    def test_two_files_different_hashes(self):
        h1 = sha256_file(FIXTURES_DIR / "sample_article.pdf")
        h2 = sha256_file(FIXTURES_DIR / "sample_article_2.pdf")
        assert h1 != h2
