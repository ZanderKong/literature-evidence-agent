"""Application layer — unified analyse workflow.

Orchestrates the full analysis pipeline:
    validate → parse → extract → validate → persist → save artifacts
"""

import json
from pathlib import Path
from typing import Any

from evidence_agent.config import config
from evidence_agent.database.connection import get_connection, transaction
from evidence_agent.extraction.claims import extract_claims_from_source
from evidence_agent.extraction.provider import (
    ClaimExtractionProvider,
    DeepSeekProvider,
    MockProvider,
)
from evidence_agent.ids import (
    generate_claim_id,
    generate_locator_id,
    generate_run_id,
    now_iso,
)
from evidence_agent.parsers.pdf import parse_pdf
from evidence_agent.validators.quote import validate_claims


def _detect_code_commit() -> str:
    """Detect the current git commit hash, or 'unknown' if not in a repo."""
    import subprocess

    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()[:8]
    except Exception:
        pass
    return "unknown"


def _get_provider(name: str) -> ClaimExtractionProvider:
    """Get provider by name. Only mock and deepseek are valid."""
    if name is None or name == "":
        raise ValueError(
            "No provider specified. Use --provider mock or --provider deepseek."
        )
    if name == "deepseek":
        return DeepSeekProvider()
    if name == "mock":
        return MockProvider()
    raise ValueError(
        f"Unknown provider: '{name}'. Valid providers: mock, deepseek."
    )


def analyse_source(
    source_id: str,
    task_id: str | None = None,
    provider_name: str = "mock",
) -> dict[str, Any]:
    """Run the full analysis pipeline on a source.

    Args:
        source_id: Source identifier.
        task_id: Optional task ID to associate.
        provider_name: 'mock' or 'deepseek'.

    Returns dict with analysis results.
    """
    # 1. Validate source exists in DB
    with get_connection(read_only=True) as conn:
        src = conn.execute(
            "SELECT source_id FROM sources WHERE source_id = ?", (source_id,)
        ).fetchone()
        if not src:
            raise ValueError(f"Source not found in database: {source_id}")

    package_dir = config.sources_dir / source_id
    if not package_dir.exists():
        raise ValueError(
            f"Source package directory not found: {package_dir}"
        )

    # 2. Validate source asset exists
    orig_pdf = package_dir / "original" / "main.pdf"
    if not orig_pdf.exists():
        raise ValueError(
            f"Source asset (main.pdf) not found in package: {orig_pdf}"
        )

    # 3. Validate task if provided
    analysis_depth = "source_complete"
    task_desc = "Extract all author claims from the scientific text."
    if task_id:
        from evidence_agent.database.repositories import get_task

        t = get_task(task_id)
        if t is None:
            raise ValueError(f"Task not found: {task_id}")
        task_desc = t.get("user_request", task_desc)
        analysis_depth = t.get("analysis_depth", "source_complete")

        # Validate task mode is compatible
        task_mode = t.get("task_mode", "")
        if task_mode not in ("analyse_uploaded", "source_complete_analysis"):
            raise ValueError(
                f"Task mode '{task_mode}' is not compatible with analysis. "
                f"Use analyse_uploaded or source_complete_analysis."
            )

        # Update task status to running
        from evidence_agent.database.repositories import update_task_status
        update_task_status(task_id, "running")

    # 4. Get provider (validates name)
    provider = _get_provider(provider_name)

    # 5. Create processing run
    run_id = generate_run_id()
    now = now_iso()
    parser_name = "pdfplumber"
    parser_version = "0.11"
    code_commit = _detect_code_commit()

    with get_connection() as conn:
        conn.execute(
            "INSERT INTO processing_runs (run_id, task_id, source_id, "
            "module_name, model_name, model_mode, prompt_version, "
            "parser_name, parser_version, code_commit, "
            "input_hash, status, started_at) "
            "VALUES (?, ?, ?, 'analyse', ?, ?, ?, ?, ?, ?, 'pending', 'started', ?)",
            (
                run_id,
                task_id,
                source_id,
                provider.model_name,
                "extraction",
                provider.prompt_version,
                parser_name,
                parser_version,
                code_commit,
                now,
            ),
        )

    try:
        # 6. Parse PDF
        parse_result = parse_pdf(source_id, package_dir)

        # 7. Persist sections to database (before any failure exit)
        _persist_sections(source_id, parse_result["sections"], parser_name, parser_version)

        # 8. Check low text density
        if parse_result["quality"]["is_low_text_density"]:
            _fail_run(run_id, "SCAN_OR_LOW_TEXT_DENSITY", "Low text density detected")
            if task_id:
                from evidence_agent.database.repositories import update_task_status
                update_task_status(task_id, "failed")
            return {
                "run_id": run_id,
                "status": "failed",
                "error": "SCAN_OR_LOW_TEXT_DENSITY",
                "message": "PDF appears to be scanned or has very low text density.",
            }

        # 10. Extract claims
        raw_claims, extraction_report = extract_claims_from_source(
            parse_result["sections"],
            task_description=task_desc,
            analysis_depth=analysis_depth,
            provider=provider,
        )

        # Save raw claims
        analysis_dir = package_dir / "analysis"
        analysis_dir.mkdir(exist_ok=True)
        _save_jsonl(raw_claims, analysis_dir / "claims.raw.jsonl")

        # 9. Check for NO_ANALYZABLE_TEXT
        blocks_processed = extraction_report.get("blocks_processed", 0)
        blocks_failed = extraction_report.get("blocks_failed", 0)

        if blocks_processed == 0:
            msg = "No analyzable text blocks found in the document."
            _fail_run(run_id, "NO_ANALYZABLE_TEXT", msg)
            if task_id:
                from evidence_agent.database.repositories import update_task_status
                update_task_status(task_id, "failed")
            return {
                "run_id": run_id,
                "status": "failed",
                "error": "NO_ANALYZABLE_TEXT",
                "message": msg,
            }

        if blocks_failed == blocks_processed:
            msg = f"All {blocks_processed} blocks failed extraction."
            _fail_run(run_id, "PROVIDER_ALL_BLOCKS_FAILED", msg)
            if task_id:
                from evidence_agent.database.repositories import update_task_status
                update_task_status(task_id, "failed")
            return {
                "run_id": run_id,
                "status": "failed",
                "error": "PROVIDER_ALL_BLOCKS_FAILED",
                "message": msg,
            }

        warnings: list[str] = []
        if blocks_failed > 0:
            warnings.append(f"{blocks_failed}/{blocks_processed} blocks had errors")

        # 10. Validate claims
        validated, failed_locator, invalid_schema = validate_claims(
            raw_claims,
            parse_result["sections"],
            parse_result["pages"],
        )

        # Save validated/failed
        _save_jsonl(validated, analysis_dir / "claims.validated.jsonl")
        _save_jsonl(
            failed_locator + invalid_schema,
            analysis_dir / "unresolved_items.jsonl",
        )

        # 11. Check if source_complete produced 0 validated claims
        if len(validated) == 0 and analysis_depth == "source_complete":
            warnings.append(
                "source_complete analysis produced 0 validated claims "
                "(text may have no extractable claims)"
            )

        # 12. Persist validated claims to database
        persisted_count = _persist_claims(
            validated, source_id, task_id, run_id
        )

        # Save persisted snapshot
        _save_jsonl(validated, analysis_dir / "claims.persisted.jsonl")

        # 13. Save provenance
        provenance_dir = package_dir / "provenance"
        provenance_dir.mkdir(exist_ok=True)
        run_record = {
            "run_id": run_id,
            "task_id": task_id,
            "source_id": source_id,
            "module_name": "analyse",
            "model_name": provider.model_name,
            "prompt_version": provider.prompt_version,
            "status": "completed",
            "started_at": now,
            "completed_at": now_iso(),
            "candidate_claims": extraction_report.get("candidate_claims", 0),
            "validated_claims": len(validated),
            "persisted_claims": persisted_count,
            "blocks_processed": blocks_processed,
            "blocks_failed": blocks_failed,
            "analysis_depth": analysis_depth,
            "warnings": warnings,
        }
        _save_jsonl([run_record], provenance_dir / "processing_runs.jsonl")

        # 14. Update manifest with analysis info
        manifest_path = package_dir / "manifest.json"
        if manifest_path.exists():
            manifest = json.loads(manifest_path.read_text())
            manifest["last_analysis"] = {
                "run_id": run_id,
                "completed_at": run_record["completed_at"],
                "validated_claims": len(validated),
                "analysis_depth": analysis_depth,
            }
            manifest_path.write_text(
                json.dumps(manifest, indent=2, ensure_ascii=False)
            )

        # 15. Complete run with metadata
        _complete_run(
            run_id,
            input_hash=_compute_input_hash(
                source_id, package_dir, task_desc, provider, analysis_depth
            ),
            output_hash=_compute_output_hash(validated, failed_locator, invalid_schema),
            warnings=warnings,
        )

        # 16. Update task status
        if task_id:
            from evidence_agent.database.repositories import update_task_status
            new_status = "review" if persisted_count > 0 else "completed"
            update_task_status(task_id, new_status)

        return {
            "run_id": run_id,
            "status": "completed",
            "source_id": source_id,
            "task_id": task_id,
            "pages": parse_result["quality"]["total_pages"],
            "sections": len(parse_result["sections"]),
            "candidate_claims": extraction_report.get("candidate_claims", 0),
            "validated_claims": len(validated),
            "persisted_claims": persisted_count,
            "failed_locators": len(failed_locator),
            "invalid_schema": len(invalid_schema),
            "model": provider.model_name,
            "prompt": provider.prompt_version,
            "analysis_depth": analysis_depth,
            "warnings": warnings,
            "next_action": (
                f"review export {run_id}"
                if persisted_count > 0
                else "No claims to review"
            ),
        }

    except Exception as e:
        _fail_run(run_id, type(e).__name__, str(e))
        if task_id:
            try:
                from evidence_agent.database.repositories import update_task_status
                update_task_status(task_id, "failed")
            except Exception:
                pass
        raise


def _compute_input_hash(
    source_id: str,
    package_dir: Path,
    task_desc: str,
    provider: ClaimExtractionProvider,
    analysis_depth: str,
) -> str:
    """Compute deterministic input hash for a processing run."""
    import hashlib

    orig_pdf = package_dir / "original" / "main.pdf"
    pdf_hash = ""
    if orig_pdf.exists():
        pdf_hash = hashlib.sha256(orig_pdf.read_bytes()).hexdigest()[:16]

    components = [
        source_id,
        pdf_hash,
        task_desc,
        provider.model_name,
        provider.prompt_version,
        analysis_depth,
    ]
    return hashlib.sha256("|".join(components).encode()).hexdigest()[:16]


def _compute_output_hash(
    validated: list[dict[str, Any]],
    failed_locator: list[dict[str, Any]],
    invalid_schema: list[dict[str, Any]],
) -> str:
    """Compute deterministic output hash from claim JSON."""
    import hashlib

    claims_json = json.dumps(
        {
            "validated": [
                {k: v for k, v in c.items() if not k.startswith("_")}
                for c in validated
            ],
            "failed_locator": [
                {k: v for k, v in c.items() if not k.startswith("_")}
                for c in failed_locator
            ],
            "invalid_schema": len(invalid_schema),
        },
        sort_keys=True,
        ensure_ascii=False,
    )
    return hashlib.sha256(claims_json.encode()).hexdigest()[:16]


def _persist_claims(
    claims: list[dict[str, Any]],
    source_id: str,
    task_id: str | None,
    run_id: str,
) -> int:
    """Persist validated claims to database in a single transaction."""
    if not claims:
        return 0

    count = 0
    with transaction() as conn:
        for claim in claims:
            match_status = claim.get("_quote_match_status", "not_found")
            if match_status not in ("exact", "normalised"):
                continue

            claim_id = generate_claim_id()
            locator_id = generate_locator_id()
            now = now_iso()
            locator = claim.get("locator_hint", {})

            conn.execute(
                "INSERT INTO source_claims (claim_id, source_id, task_id, "
                "claim_type, source_quote, faithful_paraphrase, "
                "evidence_basis_description, scope_description, author_hedging, "
                "origin_scope, record_review_status, "
                "scientific_verification_status, quote_match_status, "
                "created_by_run_id, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'external', 'pending', "
                "'unverified', ?, ?, ?, ?)",
                (
                    claim_id,
                    source_id,
                    task_id,
                    claim.get("claim_type", "reported_result"),
                    claim.get("source_quote", ""),
                    claim.get("faithful_paraphrase", ""),
                    claim.get("evidence_basis_description", ""),
                    claim.get("scope_description"),
                    claim.get("author_hedging"),
                    match_status,
                    run_id,
                    now,
                    now,
                ),
            )

            page = locator.get("page") or claim.get("_block_page_start")
            conn.execute(
                "INSERT INTO claim_locators (locator_id, claim_id, section_id, "
                "page, figure_label, table_label, locator_confidence) "
                "VALUES (?, ?, NULL, ?, ?, ?, ?)",
                (
                    locator_id,
                    claim_id,
                    page,
                    locator.get("figure_label"),
                    locator.get("table_label"),
                    "high" if match_status == "exact" else "medium",
                ),
            )

            count += 1

    return count


def _complete_run(
    run_id: str,
    input_hash: str = "",
    output_hash: str = "",
    warnings: list[str] | None = None,
) -> None:
    """Mark a processing run as completed with metadata."""
    import json as _json

    warning_json = _json.dumps(warnings or [])
    with get_connection() as conn:
        conn.execute(
            "UPDATE processing_runs SET status = 'completed', "
            "input_hash = ?, output_hash = ?, "
            "warning_json = ?, completed_at = ? "
            "WHERE run_id = ?",
            (input_hash, output_hash, warning_json, now_iso(), run_id),
        )


def _fail_run(run_id: str, error_type: str, error_msg: str) -> None:
    """Mark a processing run as failed."""
    with get_connection() as conn:
        conn.execute(
            "UPDATE processing_runs SET status = 'failed', "
            "error_type = ?, error_message = ?, completed_at = ? "
            "WHERE run_id = ?",
            (error_type, error_msg, now_iso(), run_id),
        )


def _persist_sections(
    source_id: str,
    sections: list[dict[str, Any]],
    parser_name: str,
    parser_version: str,
) -> int:
    """Persist parsed sections to source_sections table (idempotent by text hash)."""
    import hashlib

    from evidence_agent.ids import generate_section_id

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
                    section_id,
                    source_id,
                    sec.get("section_type", "body"),
                    sec.get("heading"),
                    sec.get("page_start"),
                    sec.get("page_end"),
                    seq,
                    text,
                    parser_name,
                    parser_version,
                    text_sha256,
                ),
            )
            persisted += 1

    return persisted


def _save_jsonl(items: list[dict[str, Any]], path: Path) -> None:
    """Save list of dicts to JSONL file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for item in items:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")
