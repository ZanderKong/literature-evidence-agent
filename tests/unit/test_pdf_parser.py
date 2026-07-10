"""Unit tests for PDF parsing."""

from pathlib import Path

from evidence_agent.parsers.pdf import (
    assess_parse_quality,
    extract_pages,
    generate_document_md,
    identify_sections,
    parse_pdf,
)

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures"


class TestExtractPages:
    """Test page extraction."""

    def test_extract_pages(self):
        path = FIXTURES_DIR / "sample_article.pdf"
        pages = extract_pages(path)
        assert len(pages) == 1  # Our fixture has 1 page
        assert pages[0]["page"] == 1
        assert "text" in pages[0]
        assert "char_count" in pages[0]
        assert "text_sha256" in pages[0]
        assert len(pages[0]["text_sha256"]) == 64

    def test_page_order(self):
        path = FIXTURES_DIR / "sample_article.pdf"
        pages = extract_pages(path)
        for i, page in enumerate(pages, start=1):
            assert page["page"] == i


class TestAssessQuality:
    """Test parse quality assessment."""

    def test_assess_single_page(self):
        path = FIXTURES_DIR / "sample_article.pdf"
        pages = extract_pages(path)
        quality = assess_parse_quality(pages)
        assert quality["total_pages"] == 1
        assert "average_chars" in quality
        assert "blank_page_ratio" in quality
        assert "is_low_text_density" in quality

    def test_empty_pages(self):
        empty_pages = [
            {"page": 1, "text": "", "char_count": 0, "text_sha256": "a" * 64},
            {"page": 2, "text": "", "char_count": 0, "text_sha256": "b" * 64},
        ]
        quality = assess_parse_quality(empty_pages)
        assert quality["pages_with_text"] == 0
        assert quality["is_low_text_density"] is True


class TestIdentifySections:
    """Test section identification."""

    def test_sections_from_pages(self):
        path = FIXTURES_DIR / "sample_article.pdf"
        pages = extract_pages(path)
        sections = identify_sections(pages)
        # Blank PDFs will have a "body" section
        assert len(sections) >= 1
        assert sections[0]["page_start"] >= 1

    def test_sections_with_headings(self):
        """Test section detection with realistic headings."""
        pages = [
            {
                "page": 1,
                "text": "Abstract\nThis is the abstract text.",
                "char_count": 50,
                "text_sha256": "x" * 64,
            },
            {
                "page": 2,
                "text": "Introduction\nThis is the introduction.",
                "char_count": 50,
                "text_sha256": "y" * 64,
            },
            {
                "page": 3,
                "text": "Conclusion\nThe end.",
                "char_count": 50,
                "text_sha256": "z" * 64,
            },
        ]
        sections = identify_sections(pages)
        # Should find at least 2 sections
        assert len(sections) >= 2


class TestGenerateDocumentMd:
    """Test markdown generation."""

    def test_page_separators(self):
        path = FIXTURES_DIR / "sample_article.pdf"
        pages = extract_pages(path)
        md = generate_document_md(pages)
        assert "PAGE 1" in md


class TestParsePdf:
    """Test full parse pipeline."""

    def test_parse_pdf(self, migrated_workspace):
        from evidence_agent.ingest.files import import_pdf

        # Import a PDF first
        path = FIXTURES_DIR / "sample_article.pdf"
        result = import_pdf(path)

        # Parse it
        parse_result = parse_pdf(result["source_id"], result["package_dir"])

        assert parse_result["source_id"] == result["source_id"]
        assert len(parse_result["pages"]) == 1
        assert parse_result["quality"]["total_pages"] == 1

        # Check output files exist
        for path_str in parse_result["output_paths"].values():
            assert Path(path_str).exists()
