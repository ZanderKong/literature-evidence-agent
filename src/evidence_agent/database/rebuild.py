"""Database rebuild from source packages.

Rebuilds the entire database by scanning all source packages
under the sources directory and importing their data.
"""

import json
from pathlib import Path
from typing import Any

from evidence_agent.database.connection import connect, transaction
from evidence_agent.runtime import get_current_context


def rebuild_from_packages(
    source_dir: Path | None = None,
    target_db: Path | None = None,
) -> dict[str, Any]:
    """Rebuild database from all source packages.

    Args:
        source_dir: Path to sources/ directory. If None, uses current context.
        target_db: Path to target database file. If None, uses current context.

    Returns rebuild report with counts.
    """
    runtime = get_current_context()

    if source_dir is None:
        source_dir = runtime.sources_dir
    if target_db is None:
        target_db = runtime.db_path

    source_dir = source_dir.resolve()
    target_db = target_db.resolve()

    if not source_dir.exists():
        raise FileNotFoundError(f"Sources directory not found: {source_dir}")

    # Initialize fresh database
    target_db.parent.mkdir(parents=True, exist_ok=True)
    if target_db.exists():
        target_db.unlink()

    # Migrate target directly without mutating env vars
    target_conn = connect(target_db)
    try:
        # Build migration schema on target
        from evidence_agent.database.migrations import (
            MIGRATIONS,
            get_current_version,
            get_migrations_dir,
        )
        current = get_current_version(target_conn)
        for version, name in MIGRATIONS:
            if version > current:
                path = get_migrations_dir() / name
                sql = path.read_text(encoding="utf-8")
                for statement in sql.split(";"):
                    statement = statement.strip()
                    if not statement:
                        continue
                    try:
                        target_conn.execute(statement)
                    except Exception:
                        pass
                target_conn.execute(
                    "INSERT INTO schema_migrations (version, name) VALUES (?, ?)",
                    (version, name),
                )
        target_conn.commit()
    finally:
        target_conn.close()

    report: dict[str, Any] = {
        "target_db": str(target_db),
        "sources_imported": 0,
        "sections_imported": 0,
        "claims_imported": 0,
        "locators_imported": 0,
        "runs_imported": 0,
        "decisions_imported": 0,
        "revisions_imported": 0,
        "errors": [],
    }

    # Scan all package directories
    for pkg_dir in sorted(source_dir.iterdir()):
        if not pkg_dir.is_dir():
            continue

        manifest_path = pkg_dir / "manifest.json"
        if not manifest_path.exists():
            continue

        try:
            manifest = json.loads(manifest_path.read_text())
            _import_package(pkg_dir, manifest, target_db, report)
        except Exception as e:
            report["errors"].append(f"{pkg_dir.name}: {e}")

    # Rebuild FTS on target
    _rebuild_fts_on_target(target_db)

    return report


def _rebuild_fts_on_target(target_db: Path) -> None:
    """Rebuild FTS indices on the target database."""
    with transaction(target_db) as conn:
        conn.execute("DELETE FROM claim_fts")
        conn.execute("DELETE FROM source_fts")
        conn.execute(
            "INSERT INTO source_fts (source_id, title, section_text) "
            "SELECT source_id, title, '' FROM sources"
        )
        conn.execute(
            "INSERT INTO claim_fts (claim_id, source_id, source_quote, "
            "faithful_paraphrase, evidence_basis_description) "
            "SELECT claim_id, source_id, source_quote, faithful_paraphrase, "
            "evidence_basis_description FROM source_claims "
            "WHERE record_review_status IN ('approved', 'approved_with_edits')"
        )


def _import_package(
    pkg_dir: Path, manifest: dict[str, Any], target_db: Path, report: dict[str, Any]
) -> None:
    """Import a single package into the database."""
    source_id = manifest["source_id"]

    with transaction(target_db) as conn:
        # Source
        conn.execute(
            "INSERT OR IGNORE INTO sources (source_id, source_type, title, "
            "original_file_sha256, origin_scope, scientific_verification_status, "
            "created_at, updated_at) VALUES (?, ?, ?, ?, 'external', 'unverified', "
            "?, ?)",
            (
                source_id,
                manifest.get("source_type", "journal_article"),
                manifest.get("title"),
                manifest.get("original_file_sha256", ""),
                manifest.get("created_at", ""),
                manifest.get("updated_at", ""),
            ),
        )
        report["sources_imported"] += 1

        # Assets
        for asset in manifest.get("assets", []):
            conn.execute(
                "INSERT OR IGNORE INTO source_assets (asset_id, source_id, "
                "asset_type, relative_path, mime_type, sha256, file_size, "
                "acquired_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    asset.get("asset_id", ""),
                    source_id,
                    asset.get("asset_type", "main_document"),
                    asset.get("relative_path", ""),
                    asset.get("mime_type", "application/pdf"),
                    asset.get("sha256", ""),
                    asset.get("file_size", 0),
                    manifest.get("created_at", ""),
                ),
            )

        # Sections from parsed/sections.jsonl
        sections_path = pkg_dir / "parsed" / "sections.jsonl"
        if sections_path.exists():
            seq = 0
            for line in sections_path.read_text().strip().split("\n"):
                if not line:
                    continue
                sec = json.loads(line)
                seq += 1
                section_id = f"SEC-{source_id}-{seq:04d}"
                conn.execute(
                    "INSERT OR IGNORE INTO source_sections "
                    "(section_id, source_id, section_type, heading, "
                    "page_start, page_end, sequence_number, text, "
                    "parser_name, parser_version, text_sha256) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        section_id,
                        source_id,
                        sec.get("section_type", "body"),
                        sec.get("heading"),
                        sec.get("page_start"),
                        sec.get("page_end"),
                        seq,
                        sec.get("text", ""),
                        "pdfplumber",
                        "0.11.10",
                        sec.get("text_sha256", ""),
                    ),
                )
                report["sections_imported"] += 1

        # Claims from analysis/claims.persisted.jsonl
        claims_path = pkg_dir / "analysis" / "claims.persisted.jsonl"
        run_claims_dir = pkg_dir / "analysis" / "runs"
        if run_claims_dir.exists():
            # Try per-run directory structure first
            for run_dir in sorted(run_claims_dir.iterdir()):
                if run_dir.is_dir():
                    run_claims_path = run_dir / "claims.persisted.jsonl"
                    if run_claims_path.exists():
                        claims_path = run_claims_path
                        break

        if claims_path.exists():
            for line in claims_path.read_text().strip().split("\n"):
                if not line:
                    continue
                claim = json.loads(line)
                claim_id = claim.get("claim_id") or claim.get("_claim_id", "")
                if not claim_id:
                    continue

                locator = claim.get("locator_hint", {})
                review_status = claim.get("record_review_status", "pending")

                conn.execute(
                    "INSERT OR IGNORE INTO source_claims "
                    "(claim_id, source_id, claim_type, source_quote, "
                    "faithful_paraphrase, evidence_basis_description, "
                    "scope_description, author_hedging, origin_scope, "
                    "record_review_status, scientific_verification_status, "
                    "quote_match_status, created_by_run_id, created_at, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'external', ?, "
                    "'unverified', ?, ?, ?, ?)",
                    (
                        claim_id,
                        source_id,
                        claim.get("claim_type", ""),
                        claim.get("source_quote", ""),
                        claim.get("faithful_paraphrase", ""),
                        claim.get("evidence_basis_description", ""),
                        claim.get("scope_description"),
                        claim.get("author_hedging"),
                        review_status,
                        claim.get("quote_match_status", "exact"),
                        claim.get("run_id") or claim.get("created_by_run_id") or "",
                        claim.get("created_at", ""),
                        claim.get("updated_at", ""),
                    ),
                )

                # Locator — preserve original locator_id from persisted record
                loc_id = claim.get("locator_id") or f"LOC-{claim_id}"
                loc_page = locator.get("page") if locator else claim.get("page")
                loc_fig = locator.get("figure_label") if locator else claim.get("figure_label")
                loc_tbl = locator.get("table_label") if locator else claim.get("table_label")
                loc_conf = claim.get("locator_confidence",
                    "medium" if locator else "medium")

                conn.execute(
                    "INSERT OR IGNORE INTO claim_locators "
                    "(locator_id, claim_id, page, figure_label, table_label, "
                    "locator_confidence) VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        loc_id,
                        claim_id,
                        loc_page,
                        loc_fig,
                        loc_tbl,
                        loc_conf,
                    ),
                )
                report["claims_imported"] += 1
                report["locators_imported"] += 1

        # Processing runs from provenance
        runs_path = pkg_dir / "provenance" / "processing_runs.jsonl"
        if runs_path.exists():
            for line in runs_path.read_text().strip().split("\n"):
                if not line:
                    continue
                run = json.loads(line)
                conn.execute(
                    "INSERT OR IGNORE INTO processing_runs "
                    "(run_id, task_id, source_id, module_name, model_name, "
                    "model_mode, prompt_version, parser_name, parser_version, "
                    "code_commit, input_hash, output_hash, "
                    "status, started_at, completed_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        run.get("run_id", ""),
                        run.get("task_id"),
                        run.get("source_id"),
                        run.get("module_name", "analyse"),
                        run.get("model_name"),
                        run.get("model_mode"),
                        run.get("prompt_version"),
                        run.get("parser_name"),
                        run.get("parser_version"),
                        run.get("code_commit", ""),
                        run.get("input_hash", ""),
                        run.get("output_hash", ""),
                        run.get("status", "completed"),
                        run.get("started_at", ""),
                        run.get("completed_at"),
                    ),
                )
                report["runs_imported"] += 1

        # Review decisions from review/decisions.jsonl (if snapshot exists)
        decisions_path = pkg_dir / "review" / "decisions.jsonl"
        if decisions_path.exists():
            for line in decisions_path.read_text().strip().split("\n"):
                if not line:
                    continue
                dec = json.loads(line)
                conn.execute(
                    "INSERT OR IGNORE INTO review_decisions "
                    "(review_id, object_type, object_id, decision, "
                    "original_content_json, edited_content_json, "
                    "reviewer, review_reason, reviewed_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        dec.get("review_id", ""),
                        dec.get("object_type", "claim"),
                        dec.get("object_id", ""),
                        dec.get("decision", ""),
                        dec.get("original_content_json", "{}"),
                        dec.get("edited_content_json"),
                        dec.get("reviewer", "unknown"),
                        dec.get("review_reason"),
                        dec.get("reviewed_at", ""),
                    ),
                )
                report["decisions_imported"] += 1

        # Claim revisions from review/revisions.jsonl
        revisions_path = pkg_dir / "review" / "revisions.jsonl"
        if revisions_path.exists():
            for line in revisions_path.read_text().strip().split("\n"):
                if not line:
                    continue
                rev = json.loads(line)
                conn.execute(
                    "INSERT OR IGNORE INTO claim_revisions "
                    "(revision_id, claim_id, previous_content_json, "
                    "new_content_json, changed_by, change_reason, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        rev.get("revision_id", ""),
                        rev.get("claim_id", ""),
                        rev.get("previous_content_json", "{}"),
                        rev.get("new_content_json", "{}"),
                        rev.get("changed_by", "unknown"),
                        rev.get("change_reason", ""),
                        rev.get("created_at", ""),
                    ),
                )
                report["revisions_imported"] += 1
