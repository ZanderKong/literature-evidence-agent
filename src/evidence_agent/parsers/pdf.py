"""PDF text extraction with page mapping."""

import json
import re
from pathlib import Path
from typing import Any

import pdfplumber


def extract_pages(pdf_path: Path) -> list[dict[str, Any]]:
    """Extract text from each page of a PDF.

    Returns list of {page, text, char_count, text_sha256}.
    """
    from evidence_agent.ingest.hashing import sha256_bytes

    pages: list[dict[str, Any]] = []

    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            pages.append(
                {
                    "page": i,
                    "text": text,
                    "char_count": len(text),
                    "text_sha256": sha256_bytes(text.encode("utf-8")),
                }
            )

    return pages


def assess_parse_quality(pages: list[dict[str, Any]]) -> dict[str, Any]:
    """Assess the quality of parsed text.

    Returns dict with:
        - total_pages
        - pages_with_text
        - average_chars
        - blank_page_ratio
        - is_low_text_density (likely scanned PDF)
    """
    total = len(pages)
    pages_with_text = sum(1 for p in pages if p["char_count"] > 50)
    avg_chars = sum(p["char_count"] for p in pages) / max(total, 1)
    blank_ratio = (total - pages_with_text) / max(total, 1)

    # Heuristic: if < 30% of pages have meaningful text, likely scanned
    is_low_density = pages_with_text / max(total, 1) < 0.3

    return {
        "total_pages": total,
        "pages_with_text": pages_with_text,
        "average_chars": round(avg_chars, 1),
        "blank_page_ratio": round(blank_ratio, 2),
        "is_low_text_density": is_low_density,
    }


def identify_sections(
    pages: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Identify major sections from parsed pages.

    Uses regex patterns to detect common section headings.
    Returns list of {page_start, page_end, heading, section_type, text}.
    """
    # Common section heading patterns
    section_patterns: list[tuple[str, re.Pattern[str]]] = [
        ("abstract", re.compile(r"(?i)^\s*(abstract|摘要)\s*$")),
        (
            "introduction",
            re.compile(r"(?i)^\s*(introduction|引言|绪论)\s*$"),
        ),
        (
            "experimental",
            re.compile(
                r"(?i)^\s*(experimental|materials?\s*(and|&)\s*methods?|"
                r"实验|材料与方法|方法)\s*$"
            ),
        ),
        (
            "results",
            re.compile(
                r"(?i)^\s*(results\s*(and|&)\s*discussion|结果|结果与讨论)\s*$"
            ),
        ),
        (
            "discussion",
            re.compile(r"(?i)^\s*(discussion|讨论)\s*$"),
        ),
        (
            "conclusion",
            re.compile(r"(?i)^\s*(conclusion|结论|总结)\s*$"),
        ),
        (
            "references",
            re.compile(r"(?i)^\s*(references|参考文献|bibliography)\s*$"),
        ),
    ]

    sections: list[dict[str, Any]] = []
    current_section: dict[str, Any] | None = None

    for page_data in pages:
        text = page_data["text"]
        lines = text.split("\n")

        for line in lines:
            line = line.strip()
            if not line:
                continue

            for section_type, pattern in section_patterns:
                if pattern.match(line) and len(line) < 80:
                    # End current section
                    if current_section and current_section.get("text"):
                        sections.append(current_section)

                    # Start new section
                    current_section = {
                        "page_start": page_data["page"],
                        "page_end": page_data["page"],
                        "heading": line,
                        "section_type": section_type,
                        "text": "",
                    }
                    break

        # Append text to current section
        if current_section:
            current_section["text"] += text + "\n"
            current_section["page_end"] = page_data["page"]

    # Don't forget the last section
    if current_section and current_section.get("text"):
        sections.append(current_section)

    # If no sections found, create a default "body" section
    if not sections:
        all_text = "\n".join(p["text"] for p in pages)
        sections = [
            {
                "page_start": 1,
                "page_end": len(pages),
                "heading": None,
                "section_type": "body",
                "text": all_text if all_text.strip() else "(no text extracted)",
            }
        ]

    return sections


def generate_document_md(pages: list[dict[str, Any]]) -> str:
    """Generate a human-readable Markdown document with page separators."""
    lines: list[str] = []
    for page_data in pages:
        lines.append(f"\n<!-- PAGE {page_data['page']} -->\n")
        lines.append(page_data["text"])
    return "\n".join(lines)


def parse_pdf(
    source_id: str, package_dir: Path
) -> dict[str, Any]:
    """Full PDF parse pipeline for a source.

    Args:
        source_id: The source ID.
        package_dir: Path to the source package directory.

    Returns dict with parse results.
    """
    # Find the main PDF
    original_dir = package_dir / "original"
    pdf_files = list(original_dir.glob("*.pdf"))
    if not pdf_files:
        raise FileNotFoundError(f"No PDF found in {original_dir}")
    pdf_path = pdf_files[0]

    # Extract pages
    pages = extract_pages(pdf_path)

    # Assess quality
    quality = assess_parse_quality(pages)

    # Identify sections
    sections = identify_sections(pages)

    # Generate markdown
    document_md = generate_document_md(pages)

    # Save outputs
    parsed_dir = package_dir / "parsed"
    parsed_dir.mkdir(parents=True, exist_ok=True)

    # pages.jsonl
    pages_path = parsed_dir / "pages.jsonl"
    with open(pages_path, "w", encoding="utf-8") as f:
        for page_data in pages:
            f.write(json.dumps(page_data, ensure_ascii=False) + "\n")

    # sections.jsonl
    sections_path = parsed_dir / "sections.jsonl"
    with open(sections_path, "w", encoding="utf-8") as f:
        for sec in sections:
            f.write(json.dumps(sec, ensure_ascii=False) + "\n")

    # document.md
    md_path = parsed_dir / "document.md"
    md_path.write_text(document_md, encoding="utf-8")

    # parse_report.json
    report = {
        "source_id": source_id,
        "parser_name": "pdfplumber",
        "parser_version": "0.11.10",
        "quality": quality,
        "section_count": len(sections),
        "section_types": [s["section_type"] for s in sections],
    }
    report_path = parsed_dir / "parse_report.json"
    report_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    return {
        "source_id": source_id,
        "pages": pages,
        "sections": sections,
        "quality": quality,
        "document_md": document_md,
        "output_paths": {
            "pages": str(pages_path),
            "sections": str(sections_path),
            "document_md": str(md_path),
            "report": str(report_path),
        },
    }
