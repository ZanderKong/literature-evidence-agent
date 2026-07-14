"""Parse application service — CLI-ready entry point for PDF parsing.

Persists sections to DB, writes artifacts, updates manifest.
Replaces raw parse_pdf() calls in both CLI and analyse flows.
"""

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

from evidence_agent.database.connection import get_connection, transaction
from evidence_agent.ids import generate_section_id
from evidence_agent.parsers.pdf import parse_pdf as _raw_parse
from evidence_agent.runtime import RuntimeContext, get_current_context


@dataclass
class ParseSourceResult:
    """Structured result from parse_source()."""
    source_id: str
    status: str  # "completed" | "failed"
    total_pages: int = 0
    section_count: int = 0
    sections_persisted: int = 0
    low_text_density: bool = False
    output_paths: dict[str, str] = field(default_factory=dict)
    error: str | None = None


def parse_source(
    source_id: str,
    *,
    ctx: RuntimeContext | None = None,
    force: bool = False,
) -> ParseSourceResult:
    """Parse an imported PDF source and persist sections to DB.

    Args:
        source_id: Source identifier.
        ctx: Optional RuntimeContext (uses current thread context if None).
        force: If True, re-parse even if sections already in DB.

    Returns ParseSourceResult with status and counts.
    """
    runtime = ctx or get_current_context()
    package_dir = runtime.sources_dir / source_id

    if not package_dir.exists():
        return ParseSourceResult(
            source_id=source_id, status="failed",
            error=f"Source package not found: {package_dir}",
        )

    orig_pdf = package_dir / "original" / "main.pdf"
    if not orig_pdf.exists():
        return ParseSourceResult(
            source_id=source_id, status="failed",
            error=f"Source asset not found: {orig_pdf}",
        )

    # Check if already parsed (idempotent unless force)
    if not force:
        try:
            with get_connection(read_only=True) as conn:
                count = conn.execute(
                    "SELECT COUNT(*) FROM source_sections WHERE source_id=?",
                    (source_id,),
                ).fetchone()[0]
            if count > 0:
                return ParseSourceResult(
                    source_id=source_id, status="completed",
                    sections_persisted=count,
                    section_count=count,
                    low_text_density=False,
                )
        except Exception:
            pass  # Table may not exist yet

    # Raw parse
    try:
        parse_result = _raw_parse(source_id, package_dir)
    except Exception as e:
        return ParseSourceResult(
            source_id=source_id, status="failed",
            error=f"PDF parse failed: {e}",
        )

    sections = parse_result["sections"]
    quality = parse_result["quality"]

    # Persist sections to DB
    persisted = _persist_sections(source_id, sections)

    # Update manifest
    manifest_path = package_dir / "manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text())
        manifest["parsed_at"] = __import__("datetime").datetime.now().isoformat()
        manifest["section_count"] = len(sections)
        manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False))

    return ParseSourceResult(
        source_id=source_id,
        status="completed",
        total_pages=quality.get("total_pages", 0),
        section_count=len(sections),
        sections_persisted=persisted,
        low_text_density=quality.get("is_low_text_density", False),
        output_paths=parse_result.get("output_paths", {}),
    )


def _persist_sections(source_id: str, sections: list[dict[str, Any]]) -> int:
    """Persist parsed sections to source_sections table (idempotent)."""
    if not sections:
        return 0

    persisted = 0
    with transaction() as conn:
        for seq, sec in enumerate(sections, 1):
            text = sec.get("text", "")
            text_sha256 = hashlib.sha256(text.encode()).hexdigest()
            section_id = generate_section_id()

            conn.execute(
                "INSERT OR IGNORE INTO source_sections "
                "(section_id, source_id, section_type, heading, "
                "page_start, page_end, sequence_number, text, "
                "parser_name, parser_version, text_sha256) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    section_id, source_id,
                    sec.get("section_type", "body"),
                    sec.get("heading"),
                    sec.get("page_start"),
                    sec.get("page_end"),
                    seq, text,
                    "pdfplumber", "0.11",
                    text_sha256,
                ),
            )
            persisted += 1

    return persisted
