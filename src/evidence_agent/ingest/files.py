"""File import and validation."""

import json
import shutil
from pathlib import Path
from typing import Any

from evidence_agent.database.connection import get_connection
from evidence_agent.ids import generate_asset_id, generate_source_id, now_iso
from evidence_agent.ingest.hashing import sha256_file
from evidence_agent.runtime import RuntimeContext, get_current_context

PDF_MAGIC = b"%PDF-"


def validate_file(path: Path) -> dict[str, str | int | bool | None]:
    """Validate a file before import. Returns dict with validation info."""
    result: dict[str, str | int | bool | None] = {
        "valid": False,
        "error": None,
        "mime_type": None,
        "file_size": 0,
    }

    if not path.exists():
        result["error"] = f"File not found: {path}"
        return result

    if not path.is_file():
        result["error"] = f"Not a file: {path}"
        return result

    file_size = path.stat().st_size
    result["file_size"] = file_size

    if file_size == 0:
        result["error"] = f"File is empty: {path}"
        return result

    max_size = int(100 * 1024 * 1024)
    if file_size > max_size:
        result["error"] = (
            f"File too large: {file_size} bytes (max: {max_size})"
        )
        return result

    with open(path, "rb") as f:
        header = f.read(5)

    if not header.startswith(PDF_MAGIC):
        result["error"] = f"Not a valid PDF (missing %PDF- header): {path}"
        return result

    with open(path, "rb") as f:
        if file_size > 1024:
            f.seek(-1024, 2)
        trailer = f.read()
    if b"%%EOF" not in trailer:
        result["error"] = "PDF appears corrupted (missing %%EOF marker)"
        return result

    result["valid"] = True
    result["mime_type"] = "application/pdf"
    return result


def import_pdf(
    file_path: Path,
    db_path: Path | None = None,
    ctx: RuntimeContext | None = None,
) -> dict[str, Any]:
    """Import a PDF file.

    Args:
        file_path: Path to the PDF file.
        db_path: Optional database path override (for testing).
        ctx: Optional RuntimeContext (uses current thread context if None).

    Returns dict with source_id, is_new, package_dir, sha256, file_size.
    """
    runtime = ctx or get_current_context()

    # 1. Validate
    validation = validate_file(file_path)
    if not validation["valid"]:
        raise ValueError(validation["error"])

    # 2. Calculate hash
    file_hash = sha256_file(file_path)

    # 3. Check if already imported
    with get_connection(db_path) as conn:
        cursor = conn.execute(
            "SELECT source_id FROM sources WHERE original_file_sha256 = ?",
            (file_hash,),
        )
        existing = cursor.fetchone()

    if existing:
        source_id = existing[0]
        package_dir = runtime.sources_dir / source_id
        return {
            "source_id": source_id,
            "is_new": False,
            "package_dir": package_dir,
            "sha256": file_hash,
            "file_size": validation["file_size"],
        }

    # 4. Generate new source
    source_id = generate_source_id()
    asset_id = generate_asset_id()
    now = now_iso()
    package_dir = runtime.sources_dir / source_id

    # 5. Create package directories
    original_dir = package_dir / "original"
    parsed_dir = package_dir / "parsed"
    analysis_dir = package_dir / "analysis"
    provenance_dir = package_dir / "provenance"

    for d in [original_dir, parsed_dir, analysis_dir, provenance_dir]:
        d.mkdir(parents=True, exist_ok=True)

    # 6. Copy original file as main.pdf
    dest_path = original_dir / "main.pdf"
    shutil.copy2(file_path, dest_path)

    # 7. Verify copy hash
    if sha256_file(dest_path) != file_hash:
        shutil.rmtree(package_dir, ignore_errors=True)
        raise RuntimeError(
            f"Hash mismatch after copy! Original: {file_hash}, "
            f"Copy: {sha256_file(dest_path)}"
        )

    # 8. Write manifest
    manifest = {
        "source_id": source_id,
        "source_type": "journal_article",
        "title": None,
        "original_file": f"original/{file_path.name}",
        "original_file_sha256": file_hash,
        "origin_scope": "external",
        "scientific_verification_status": "unverified",
        "created_at": now,
        "updated_at": now,
        "assets": [
            {
                "asset_id": asset_id,
                "asset_type": "main_document",
                "relative_path": f"original/{file_path.name}",
                "mime_type": "application/pdf",
                "sha256": file_hash,
                "file_size": validation["file_size"],
            }
        ],
    }

    manifest_path = package_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False))

    # 9. Write to database
    with get_connection(db_path) as conn:
        conn.execute(
            "INSERT INTO sources (source_id, source_type, title, "
            "original_file_sha256, origin_scope, scientific_verification_status, "
            "created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                source_id,
                manifest["source_type"],
                manifest["title"],
                file_hash,
                "external",
                "unverified",
                now,
                now,
            ),
        )
        conn.execute(
            "INSERT INTO source_assets (asset_id, source_id, asset_type, "
            "relative_path, mime_type, sha256, file_size, acquired_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                asset_id,
                source_id,
                "main_document",
                f"original/{file_path.name}",
                "application/pdf",
                file_hash,
                validation["file_size"],
                now,
            ),
        )

    return {
        "source_id": source_id,
        "is_new": True,
        "package_dir": package_dir,
        "sha256": file_hash,
        "file_size": validation["file_size"],
    }
