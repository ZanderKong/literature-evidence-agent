"""Application layer — unified analyse workflow.

Orchestrates the full analysis pipeline:
    parse → extract → validate → persist → save artifacts
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


def _get_provider(name: str) -> ClaimExtractionProvider:
    """Get provider by name."""
    if name == "deepseek":
        return DeepSeekProvider()
    return MockProvider()


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
    package_dir = config.sources_dir / source_id
    if not package_dir.exists():
        raise ValueError(f"Source not found: {source_id}")

    # 1. Create processing run
    run_id = generate_run_id()
    now = now_iso()
    provider = _get_provider(provider_name)

    with get_connection() as conn:
        conn.execute(
            "INSERT INTO processing_runs (run_id, task_id, source_id, "
            "module_name, model_name, prompt_version, input_hash, status, "
            "started_at) VALUES (?, ?, ?, 'analyse', ?, ?, ?, 'started', ?)",
            (
                run_id,
                task_id,
                source_id,
                provider.model_name,
                provider.prompt_version,
                "pending",
                now,
            ),
        )

    try:
        # 2. Parse PDF
        parse_result = parse_pdf(source_id, package_dir)

        # 3. Check low text density
        if parse_result["quality"]["is_low_text_density"]:
            _fail_run(run_id, "SCAN_OR_LOW_TEXT_DENSITY", "Low text density detected")
            return {
                "run_id": run_id,
                "status": "failed",
                "error": "SCAN_OR_LOW_TEXT_DENSITY",
                "message": "PDF appears to be scanned or has very low text density.",
            }

        # 4. Extract claims
        task_desc = "Extract all author claims from the scientific text."
        if task_id:
            from evidence_agent.database.repositories import get_task
            t = get_task(task_id)
            if t:
                task_desc = t.get("user_request", task_desc)

        raw_claims, extraction_report = extract_claims_from_source(
            parse_result["sections"],
            task_description=task_desc,
            analysis_depth="source_complete",
            provider=provider,
        )

        # Save raw claims
        analysis_dir = package_dir / "analysis"
        analysis_dir.mkdir(exist_ok=True)
        _save_jsonl(raw_claims, analysis_dir / "claims.raw.jsonl")

        # 5. Validate claims
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

        # 6. Persist validated claims to database
        persisted_count = _persist_claims(
            validated, source_id, task_id, run_id
        )

        # Save persisted snapshot
        _save_jsonl(validated, analysis_dir / "claims.persisted.jsonl")

        # 7. Complete run
        _complete_run(run_id)

        return {
            "run_id": run_id,
            "status": "completed",
            "source_id": source_id,
            "task_id": task_id,
            "pages": parse_result["quality"]["total_pages"],
            "sections": len(parse_result["sections"]),
            "candidate_claims": extraction_report["candidate_claims"],
            "validated_claims": len(validated),
            "persisted_claims": persisted_count,
            "failed_locators": len(failed_locator),
            "invalid_schema": len(invalid_schema),
            "model": provider.model_name,
            "prompt": provider.prompt_version,
            "next_action": (
                f"review export {run_id}"
                if persisted_count > 0
                else "No claims to review"
            ),
        }

    except Exception as e:
        _fail_run(run_id, type(e).__name__, str(e))
        raise


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

            # Insert claim
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

            # Insert locator
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


def _complete_run(run_id: str) -> None:
    """Mark a processing run as completed."""
    with get_connection() as conn:
        conn.execute(
            "UPDATE processing_runs SET status = 'completed', "
            "completed_at = ? WHERE run_id = ?",
            (now_iso(), run_id),
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


def _save_jsonl(items: list[dict[str, Any]], path: Path) -> None:
    """Save list of dicts to JSONL file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for item in items:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")
