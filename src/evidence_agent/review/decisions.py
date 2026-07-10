"""Apply human review decisions with full revalidation and FTS sync.

Two-phase design:
1. Pre-validate all rows — build application plan
2. Apply everything in a single transaction (all-or-nothing)
"""

import csv
import json
from pathlib import Path
from typing import Any

from evidence_agent.database.connection import get_connection, transaction
from evidence_agent.ids import generate_review_id, generate_revision_id, now_iso

VALID_DECISIONS = {
    "approve", "approve_with_edits", "reject",
    "mark_missing", "needs_followup",
}
VALID_CLAIM_TYPES = {
    "background_statement", "method_statement",
    "reported_observation", "reported_result",
    "author_interpretation", "author_conclusion",
    "author_hypothesis", "author_limitation", "future_work",
}


class ReviewValidationError(Exception):
    """A row failed pre-validation."""


def apply_review_csv(csv_path: Path) -> dict[str, Any]:
    """Apply review decisions from CSV. All-or-nothing transaction."""
    if not csv_path.exists():
        raise FileNotFoundError(f"Review CSV not found: {csv_path}")

    rows: list[dict[str, str]] = []
    with open(csv_path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)

    if not rows:
        return _empty_report("No rows in CSV")

    # Phase 1: Pre-validate all rows
    errors: list[str] = []
    plans: list[dict[str, Any]] = []

    with get_connection(read_only=True) as conn:
        # Pre-load source sections for all claims
        all_claims = set()
        for row in rows:
            cid = (row.get("claim_id") or "").strip()
            if cid:
                all_claims.add(cid)

        # Get all claims at once
        if all_claims:
            placeholders = ",".join("?" * len(all_claims))
            existing_rows = conn.execute(
                f"SELECT * FROM source_claims WHERE claim_id IN ({placeholders})",
                tuple(all_claims),
            ).fetchall()
            existing = {r["claim_id"]: dict(r) for r in existing_rows}
        else:
            existing = {}

        # Pre-load sections
        sections_by_source: dict[str, str] = {}
        section_set = conn.execute(
            "SELECT source_id, text FROM source_sections"
        ).fetchall()
        for row in section_set:
            sid = row["source_id"]
            if sid not in sections_by_source:
                sections_by_source[sid] = ""
            sections_by_source[sid] += (row["text"] or "") + "\n"

    for row in rows:
        claim_id = (row.get("claim_id") or "").strip()
        decision = (row.get("decision") or "").strip().lower()

        if not claim_id:
            errors.append("Missing claim_id in row")
            continue

        if not decision:
            # Empty decision = skip
            continue

        if decision not in VALID_DECISIONS:
            errors.append(f"Invalid decision '{decision}' for {claim_id}")
            continue

        ex = existing.get(claim_id)
        if not ex:
            errors.append(f"Claim not found: {claim_id}")
            continue

        source_id = ex.get("source_id", "")

        # Build plan entry
        plan = {
            "claim_id": claim_id,
            "decision": decision,
            "row": row,
            "existing": ex,
            "source_id": source_id,
        }

        # Validate edits if needed
        if decision == "approve_with_edits":
            ed_errs = _validate_edits(row, source_id, sections_by_source)
            errors.extend(ed_errs)
            if ed_errs:
                continue

        plans.append(plan)

    if errors:
        return _error_report(rows, errors)

    # Phase 2: Apply all plans in a single transaction
    report: dict[str, Any] = {
        "total": len(rows),
        "approved": 0, "rejected": 0, "edited": 0,
        "marked_missing": 0, "needs_followup": 0,
        "skipped": 0, "errors": [],
    }

    with transaction() as conn:
        for plan in plans:
            claim_id = plan["claim_id"]
            decision = plan["decision"]
            row = plan["row"]
            ex = plan["existing"]

            # Idempotency check
            cursor = conn.execute(
                "SELECT COUNT(*) FROM review_decisions "
                "WHERE object_id = ? AND decision = ?",
                (claim_id, decision),
            )
            if cursor.fetchone()[0] > 0:
                report["skipped"] += 1
                continue

            now = now_iso()
            rid = generate_review_id()
            orig = json.dumps({
                "claim_type": ex["claim_type"],
                "source_quote": ex["source_quote"],
                "faithful_paraphrase": ex["faithful_paraphrase"],
                "evidence_basis_description": ex["evidence_basis_description"],
            })

            if decision == "approve":
                _apply_approve(conn, rid, claim_id, orig, row, now)
                report["approved"] += 1
                _sync_fts_insert(conn, claim_id)

            elif decision == "approve_with_edits":
                _apply_edit(conn, rid, claim_id, orig, row, ex, now)
                report["edited"] += 1
                _sync_fts_replace(conn, claim_id)

            elif decision == "reject":
                _apply_reject(conn, rid, claim_id, orig, row, now)
                report["rejected"] += 1
                _sync_fts_remove(conn, claim_id)

            elif decision == "mark_missing":
                _apply_mark_missing(conn, rid, claim_id, orig, row, now)
                report["marked_missing"] += 1

            elif decision == "needs_followup":
                _apply_needs_followup(conn, rid, claim_id, orig, row, now)
                report["needs_followup"] += 1

    return report


def _validate_edits(
    row: dict[str, str],
    source_id: str,
    sections: dict[str, str],
) -> list[str]:
    """Validate edited fields before applying. Returns error messages."""
    errors: list[str] = []
    claim_id = (row.get("claim_id") or "").strip()
    prefix = f"[{claim_id}] "

    # Assert source_sections available
    section_text = sections.get(source_id, "")
    if not section_text:
        errors.append(f"{prefix}SOURCE_TEXT_UNAVAILABLE: no sections for source")
        return errors

    # Validate source quote
    ed_quote = (row.get("edited_source_quote") or "").strip()
    if not ed_quote:
        errors.append(f"{prefix}Edited source_quote must not be empty")
        return errors

    from evidence_agent.validators.quote import match_quote
    ms, _, _ = match_quote(ed_quote, section_text)
    if ms not in ("exact", "normalised"):
        errors.append(
            f"{prefix}Edited quote not found in source text (match: {ms})"
        )

    # Validate edited page if specified
    ed_page_str = (row.get("edited_page") or "").strip()
    if ed_page_str:
        try:
            ed_page = int(ed_page_str)
            if ed_page < 1:
                errors.append(f"{prefix}Invalid edited_page: {ed_page}")
            else:
                # Check page exists in source sections
                from evidence_agent.database.connection import get_connection
                with get_connection(read_only=True) as conn:
                    cur = conn.execute(
                        "SELECT MAX(page_end) FROM source_sections WHERE source_id = ?",
                        (source_id,),
                    )
                    max_page = (cur.fetchone()[0] or 0)
                    if ed_page > max_page:
                        errors.append(
                            f"{prefix}Edited page {ed_page} exceeds source max page {max_page}"
                        )
        except ValueError:
            errors.append(f"{prefix}Invalid edited_page: '{ed_page_str}'")

    # Validate edited section if specified
    ed_section = (row.get("edited_section") or "").strip()
    if ed_section:
        from evidence_agent.database.connection import get_connection
        with get_connection(read_only=True) as conn:
            cur = conn.execute(
                "SELECT COUNT(*) FROM source_sections "
                "WHERE source_id = ? AND heading = ?",
                (source_id, ed_section),
            )
            if cur.fetchone()[0] == 0:
                errors.append(f"{prefix}Edited section '{ed_section}' not found in source")

    # Validate claim_type
    ed_type = (row.get("edited_claim_type") or "").strip()
    if ed_type and ed_type not in VALID_CLAIM_TYPES:
        errors.append(f"{prefix}Invalid claim_type: '{ed_type}'")

    return errors


def _apply_approve(
    conn: Any, rid: str, claim_id: str, orig: str,
    row: dict[str, str], now: str,
) -> None:
    conn.execute(
        "INSERT INTO review_decisions (review_id, object_type, "
        "object_id, decision, original_content_json, reviewer, "
        "reviewed_at) VALUES (?, 'claim', ?, ?, ?, ?, ?)",
        (rid, claim_id, "approve", orig,
         row.get("reviewer", "unknown"), now),
    )
    conn.execute(
        "UPDATE source_claims SET record_review_status='approved', "
        "updated_at=? WHERE claim_id=?", (now, claim_id))


def _apply_edit(
    conn: Any, rid: str, claim_id: str, orig: str,
    row: dict[str, str], ex: dict[str, Any], now: str,
) -> None:
    ed_quote = row.get("edited_source_quote") or ex["source_quote"]
    ed_para = row.get("edited_faithful_paraphrase") or ex["faithful_paraphrase"]
    raw_ed_basis = row.get("edited_evidence_basis_description")
    ed_basis = raw_ed_basis or ex["evidence_basis_description"]
    ed_type = row.get("edited_claim_type") or ex["claim_type"]

    edited = {
        "claim_type": ed_type,
        "source_quote": ed_quote,
        "faithful_paraphrase": ed_para,
        "evidence_basis_description": ed_basis,
    }
    ed_json = json.dumps(edited)

    rev_id = generate_revision_id()
    conn.execute(
        "INSERT INTO claim_revisions (revision_id, claim_id, "
        "previous_content_json, new_content_json, changed_by, "
        "change_reason, created_at) VALUES (?,?,?,?,?,?,?)",
        (rev_id, claim_id, orig, ed_json,
         row.get("reviewer", "unknown"),
         row.get("review_reason", ""), now))

    conn.execute(
        "INSERT INTO review_decisions (review_id, object_type, "
        "object_id, decision, original_content_json, "
        "edited_content_json, reviewer, reviewed_at) "
        "VALUES (?, 'claim', ?, ?, ?, ?, ?, ?)",
        (rid, claim_id, "approve_with_edits", orig, ed_json,
         row.get("reviewer", "unknown"), now))

    conn.execute(
        "UPDATE source_claims SET claim_type=?, source_quote=?, "
        "faithful_paraphrase=?, evidence_basis_description=?, "
        "record_review_status='approved_with_edits', updated_at=? "
        "WHERE claim_id=?",
        (ed_type, ed_quote, ed_para, ed_basis, now, claim_id))


def _apply_reject(
    conn: Any, rid: str, claim_id: str, orig: str,
    row: dict[str, str], now: str,
) -> None:
    conn.execute(
        "INSERT INTO review_decisions (review_id, object_type, "
        "object_id, decision, original_content_json, reviewer, "
        "review_reason, reviewed_at) VALUES (?, 'claim', ?, ?, ?, ?, ?, ?)",
        (rid, claim_id, "reject", orig,
         row.get("reviewer", "unknown"),
         row.get("review_reason", ""), now))
    conn.execute(
        "UPDATE source_claims SET record_review_status='rejected', "
        "updated_at=? WHERE claim_id=?", (now, claim_id))


def _apply_mark_missing(
    conn: Any, rid: str, claim_id: str, orig: str,
    row: dict[str, str], now: str,
) -> None:
    conn.execute(
        "INSERT INTO review_decisions (review_id, object_type, "
        "object_id, decision, original_content_json, reviewer, "
        "review_reason, reviewed_at) VALUES (?, 'claim', ?, ?, ?, ?, ?, ?)",
        (rid, claim_id, "mark_missing", orig,
         row.get("reviewer", "unknown"),
         row.get("review_reason", ""), now))


def _apply_needs_followup(
    conn: Any, rid: str, claim_id: str, orig: str,
    row: dict[str, str], now: str,
) -> None:
    conn.execute(
        "INSERT INTO review_decisions (review_id, object_type, "
        "object_id, decision, original_content_json, reviewer, "
        "review_reason, reviewed_at) VALUES (?, 'claim', ?, ?, ?, ?, ?, ?)",
        (rid, claim_id, "needs_followup", orig,
         row.get("reviewer", "unknown"),
         row.get("review_reason", ""), now))


def _sync_fts_insert(conn: Any, claim_id: str) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO claim_fts (claim_id, source_id, source_quote, "
        "faithful_paraphrase, evidence_basis_description) "
        "SELECT claim_id, source_id, source_quote, faithful_paraphrase, "
        "evidence_basis_description FROM source_claims WHERE claim_id = ?",
        (claim_id,),
    )


def _sync_fts_replace(conn: Any, claim_id: str) -> None:
    _sync_fts_insert(conn, claim_id)


def _sync_fts_remove(conn: Any, claim_id: str) -> None:
    conn.execute("DELETE FROM claim_fts WHERE claim_id = ?", (claim_id,))


def _error_report(rows: list[dict], errors: list[str]) -> dict[str, Any]:
    return {
        "total": len(rows),
        "approved": 0, "rejected": 0, "edited": 0,
        "marked_missing": 0, "needs_followup": 0,
        "skipped": 0, "errors": errors,
    }


def _empty_report(reason: str) -> dict[str, Any]:
    return {
        "total": 0,
        "approved": 0, "rejected": 0, "edited": 0,
        "marked_missing": 0, "needs_followup": 0,
        "skipped": 0, "errors": [reason],
    }
