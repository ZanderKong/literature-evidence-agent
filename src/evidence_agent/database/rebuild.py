"""Database rebuild from source packages.

Rebuilds the entire database by scanning all source packages
under the sources directory and importing their data.
"""

import json
from pathlib import Path
from typing import Any

from evidence_agent.database.connection import transaction
from evidence_agent.database.migrations import migrate


def rebuild_from_packages(
    source_dir: Path | None = None,
    target_db: Path | None = None,
) -> dict[str, Any]:
    """Rebuild database from all source packages.

    Args:
        source_dir: Path to sources/ directory.
        target_db: Path to target database file.

    Returns rebuild report with counts.
    """
    from evidence_agent.config import config

    if source_dir is None:
        source_dir = config.sources_dir
    if target_db is None:
        target_db = config.db_path

    if not source_dir.exists():
        raise FileNotFoundError(f"Sources directory not found: {source_dir}")

    # Initialize fresh database
    target_db.parent.mkdir(parents=True, exist_ok=True)
    if target_db.exists():
        target_db.unlink()

    # Override config for rebuild target
    import os
    os.environ["EVIDENCE_AGENT_DB_PATH"] = str(target_db.relative_to(config.workspace_path))
    import importlib

    import evidence_agent.config as cfg_mod
    importlib.reload(cfg_mod)

    migrate(target_db)

    report: dict[str, Any] = {
        "target_db": str(target_db),
        "sources_imported": 0,
        "sections_imported": 0,
        "claims_imported": 0,
        "locators_imported": 0,
        "runs_imported": 0,
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

    # Rebuild FTS
    # Temporarily switch to target
    import evidence_agent.database.connection as conn_mod
    from evidence_agent.search.fts import rebuild_fts as fts_rebuild
    importlib.reload(conn_mod)
    fts_rebuild()

    return report


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
        if claims_path.exists():
            for line in claims_path.read_text().strip().split("\n"):
                if not line:
                    continue
                claim = json.loads(line)
                claim_id = claim.get("_claim_id") or claim.get("claim_id", "")
                if not claim_id:
                    continue
                locator = claim.get("locator_hint", {})

                conn.execute(
                    "INSERT OR IGNORE INTO source_claims "
                    "(claim_id, source_id, claim_type, source_quote, "
                    "faithful_paraphrase, evidence_basis_description, "
                    "scope_description, author_hedging, origin_scope, "
                    "record_review_status, scientific_verification_status, "
                    "quote_match_status, created_by_run_id, created_at, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'external', 'pending', "
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
                        claim.get("_quote_match_status", "exact"),
                        claim.get("_block_page_start", "0"),
                        claim.get("created_at", ""),
                        claim.get("updated_at", ""),
                    ),
                )

                # Locator
                loc_id = f"LOC-{claim_id}"
                conn.execute(
                    "INSERT OR IGNORE INTO claim_locators "
                    "(locator_id, claim_id, page, figure_label, table_label, "
                    "locator_confidence) VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        loc_id,
                        claim_id,
                        locator.get("page"),
                        locator.get("figure_label"),
                        locator.get("table_label"),
                        locator.get("_locator_confidence", "medium"),
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
                    "prompt_version, input_hash, status, started_at, completed_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        run.get("run_id", ""),
                        run.get("task_id"),
                        run.get("source_id"),
                        run.get("module_name", "analyse"),
                        run.get("model_name"),
                        run.get("prompt_version"),
                        run.get("input_hash", ""),
                        run.get("status", "completed"),
                        run.get("started_at", ""),
                        run.get("completed_at"),
                    ),
                )
                report["runs_imported"] += 1
