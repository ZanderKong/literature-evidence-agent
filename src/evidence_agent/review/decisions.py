"""Apply human review decisions with full revalidation and FTS sync.

Two-phase design:
1. Pre-validate all rows — no DB writes if any validation fails
2. Apply everything in a single transaction (all-or-nothing)

Batch-aware: decisions carry review_batch_id + review_row_id.
Idempotent by (review_batch_id, review_row_id).

Decision actions:
- approve → mark approved, index FTS
- approve_with_edits → validate edits, create revision, update claim
- reject → mark rejected, remove from FTS
- mark_missing / needs_followup → record decision only
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
    """Apply review decisions from CSV. All-or-nothing transaction.

    CSV must include at minimum: claim_id, decision.
    When batch-aware, must include: review_batch_id, review_row_id,
    row_input_sha256.
    """
    if not csv_path.exists():
        raise FileNotFoundError(f"Review CSV not found: {csv_path}")

    rows: list[dict[str, str]] = []
    with open(csv_path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)

    if not rows:
        return _empty_report("No rows in CSV")

    errors: list[str] = []
    plans: list[dict[str, Any]] = []

    # Determine if batch-aware (has review_batch_id column)
    batch_mode = any(
        (r.get("review_batch_id") or "").strip()
        for r in rows
    )

    with get_connection(read_only=True) as conn:
        all_existing = _preload_claims(conn, rows)
        sections_by_source = _preload_sections(conn)

        if batch_mode:
            _validate_batch_context(conn, rows, errors)

    for row in rows:
        claim_id = (row.get("claim_id") or "").strip()
        decision = (row.get("decision") or "").strip().lower()

        if not claim_id:
            errors.append("Missing claim_id in row")
            continue

        if not decision:
            continue

        if decision not in VALID_DECISIONS:
            errors.append(f"Invalid decision '{decision}' for {claim_id}")
            continue

        ex = all_existing.get(claim_id)
        if not ex:
            errors.append(f"Claim not found: {claim_id}")
            continue

        source_id = ex.get("source_id", "")

        plan: dict[str, Any] = {
            "claim_id": claim_id,
            "decision": decision,
            "row": row,
            "existing": ex,
            "source_id": source_id,
        }

        if batch_mode:
            batch_id = (row.get("review_batch_id") or "").strip()
            row_id = (row.get("review_row_id") or "").strip()
            plan["review_batch_id"] = batch_id
            plan["review_row_id"] = row_id

        if decision == "approve_with_edits":
            ed_errs = _validate_edits(row, source_id, sections_by_source)
            errors.extend(ed_errs)
            if ed_errs:
                continue

        plans.append(plan)

    if errors:
        return _error_report(rows, errors)

    report: dict[str, Any] = {
        "total": len(rows),
        "approved": 0, "rejected": 0, "edited": 0,
        "marked_missing": 0, "needs_followup": 0,
        "skipped": 0, "errors": [],
    }

    with transaction() as conn:
        for _plan_idx, plan in enumerate(plans):
            claim_id = plan["claim_id"]
            decision = plan["decision"]
            row = plan["row"]
            ex = plan["existing"]
            batch_id = plan.get("review_batch_id", "")
            row_id = plan.get("review_row_id", "")

            if batch_id and row_id:
                cursor = conn.execute(
                    "SELECT COUNT(*) FROM review_decisions "
                    "WHERE review_batch_id = ? AND review_row_id = ?",
                    (batch_id, row_id),
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
                _apply_approve(conn, rid, claim_id, orig, row, batch_id, row_id, now)
                report["approved"] += 1
                _sync_fts_insert(conn, claim_id)
                _update_batch_row_applied(conn, batch_id, row_id, now)
                _update_batch_status(conn, batch_id)

            elif decision == "approve_with_edits":
                _apply_edit(conn, rid, claim_id, orig, row, ex, batch_id, row_id, now)
                report["edited"] += 1
                _sync_fts_replace(conn, claim_id)
                _update_batch_row_applied(conn, batch_id, row_id, now)
                _update_batch_status(conn, batch_id)

            elif decision == "reject":
                _apply_reject(conn, rid, claim_id, orig, row, batch_id, row_id, now)
                report["rejected"] += 1
                _sync_fts_remove(conn, claim_id)
                _update_batch_row_applied(conn, batch_id, row_id, now)
                _update_batch_status(conn, batch_id)

            elif decision == "mark_missing":
                _apply_mark_missing(conn, rid, claim_id, orig, row, batch_id, row_id, now)
                report["marked_missing"] += 1
                _update_batch_row_applied(conn, batch_id, row_id, now)
                _update_batch_status(conn, batch_id)

            elif decision == "needs_followup":
                _apply_needs_followup(conn, rid, claim_id, orig, row, batch_id, row_id, now)
                report["needs_followup"] += 1
                _update_batch_row_applied(conn, batch_id, row_id, now)
                _update_batch_status(conn, batch_id)

    return report


def _preload_claims(conn: Any, rows: list[dict[str, str]]) -> dict[str, dict[str, Any]]:
    """Preload all claims referenced in the CSV."""
    all_claims = set()
    for row in rows:
        cid = (row.get("claim_id") or "").strip()
        if cid:
            all_claims.add(cid)
    if not all_claims:
        return {}
    placeholders = ",".join("?" * len(all_claims))
    existing_rows = conn.execute(
        f"SELECT * FROM source_claims WHERE claim_id IN ({placeholders})",
        tuple(all_claims),
    ).fetchall()
    return {r["claim_id"]: dict(r) for r in existing_rows}


def _preload_sections(conn: Any) -> dict[str, str]:
    """Preload source_sections text grouped by source_id."""
    sections_by_source: dict[str, str] = {}
    section_set = conn.execute(
        "SELECT source_id, text FROM source_sections"
    ).fetchall()
    for row in section_set:
        sid = row["source_id"]
        if sid not in sections_by_source:
            sections_by_source[sid] = ""
        sections_by_source[sid] += (row["text"] or "") + "\n"
    return sections_by_source


def _validate_batch_context(
    conn: Any, rows: list[dict[str, str]], errors: list[str],
) -> None:
    """Validate that all non-skip rows belong to their batch."""
    batch_ids: set[str] = set()
    for row in rows:
        bid = (row.get("review_batch_id") or "").strip()
        if bid:
            batch_ids.add(bid)

    if not batch_ids:
        return

    placeholders = ",".join("?" * len(batch_ids))
    batch_rows = conn.execute(
        f"SELECT * FROM review_batches WHERE review_batch_id IN ({placeholders})",
        tuple(batch_ids),
    ).fetchall()
    existing_batches = {r["review_batch_id"] for r in batch_rows}

    row_placeholders = ",".join("?" * len(batch_ids))
    all_batch_rows = conn.execute(
        f"SELECT * FROM review_batch_rows WHERE review_batch_id IN ({row_placeholders})",
        tuple(batch_ids),
    ).fetchall()
    existing_row_ids: dict[str, set[str]] = {}
    for r in all_batch_rows:
        bid = r["review_batch_id"]
        if bid not in existing_row_ids:
            existing_row_ids[bid] = set()
        existing_row_ids[bid].add(r["review_row_id"])

    for row in rows:
        cid = (row.get("claim_id") or "").strip()
        decision = (row.get("decision") or "").strip().lower()
        if not decision:
            continue
        bid = (row.get("review_batch_id") or "").strip()
        rid_val = (row.get("review_row_id") or "").strip()
        if not bid or not rid_val:
            continue

        if bid not in existing_batches:
            errors.append(f"[{cid}] Batch not found: {bid}")
            continue
        if rid_val not in existing_row_ids.get(bid, set()):
            errors.append(f"[{cid}] Row {rid_val} not in batch {bid}")
            continue

        row_sha = (row.get("row_input_sha256") or "").strip()
        if row_sha:
            matched = False
            for br in all_batch_rows:
                if br["review_batch_id"] == bid and br["review_row_id"] == rid_val:
                    if br["row_input_sha256"] == row_sha:
                        matched = True
                    break
            if not matched:
                errors.append(f"[{cid}] row_input_sha256 mismatch")


def _update_batch_row_applied(
    conn: Any, batch_id: str, row_id: str, now: str,
) -> None:
    """Mark a batch row as applied."""
    if not batch_id or not row_id:
        return
    conn.execute(
        "UPDATE review_batch_rows SET applied_at = ? "
        "WHERE review_batch_id = ? AND review_row_id = ?",
        (now, batch_id, row_id),
    )


def _update_batch_status(conn: Any, batch_id: str) -> None:
    """Derive batch status from applied/pending row counts."""
    if not batch_id:
        return
    total = conn.execute(
        "SELECT COUNT(*) FROM review_batch_rows WHERE review_batch_id = ?",
        (batch_id,),
    ).fetchone()[0]
    applied = conn.execute(
        "SELECT COUNT(*) FROM review_batch_rows "
        "WHERE review_batch_id = ? AND applied_at IS NOT NULL",
        (batch_id,),
    ).fetchone()[0]
    if applied == 0:
        return
    if applied == total:
        status = "applied"
    else:
        status = "partially_applied"
    conn.execute(
        "UPDATE review_batches SET status = ?, completed_at = ? "
        "WHERE review_batch_id = ? AND status != ?",
        (status, now_iso(), batch_id, status),
    )


def _validate_edits(
    row: dict[str, str],
    source_id: str,
    sections: dict[str, str],
) -> list[str]:
    """Validate edited fields before applying. Returns error messages."""
    errors: list[str] = []
    claim_id = (row.get("claim_id") or "").strip()
    prefix = f"[{claim_id}] "

    section_text = sections.get(source_id, "")
    if not section_text:
        errors.append(f"{prefix}SOURCE_TEXT_UNAVAILABLE: no sections for source")
        return errors

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

    ed_page_str = (row.get("edited_page") or "").strip()
    if ed_page_str:
        try:
            ed_page = int(ed_page_str)
            if ed_page < 1:
                errors.append(f"{prefix}Invalid edited_page: {ed_page}")
            else:
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

    ed_type = (row.get("edited_claim_type") or "").strip()
    if ed_type and ed_type not in VALID_CLAIM_TYPES:
        errors.append(f"{prefix}Invalid claim_type: '{ed_type}'")

    return errors


def _apply_approve(
    conn: Any, rid: str, claim_id: str, orig: str,
    row: dict[str, str],
    batch_id: str, row_id: str, now: str,
) -> None:
    conn.execute(
        "INSERT INTO review_decisions (review_id, object_type, "
        "object_id, decision, original_content_json, reviewer, "
        "review_batch_id, review_row_id, reviewed_at) "
        "VALUES (?, 'claim', ?, ?, ?, ?, ?, ?, ?)",
        (rid, claim_id, "approve", orig,
         row.get("reviewer", "unknown"),
         batch_id or None, row_id or None, now),
    )
    conn.execute(
        "UPDATE source_claims SET record_review_status='approved', "
        "updated_at=? WHERE claim_id=?", (now, claim_id))


def _apply_edit(
    conn: Any, rid: str, claim_id: str, orig: str,
    row: dict[str, str], ex: dict[str, Any],
    batch_id: str, row_id: str, now: str,
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
        "edited_content_json, reviewer, "
        "review_batch_id, review_row_id, reviewed_at) "
        "VALUES (?, 'claim', ?, ?, ?, ?, ?, ?, ?, ?)",
        (rid, claim_id, "approve_with_edits", orig, ed_json,
         row.get("reviewer", "unknown"),
         batch_id or None, row_id or None, now))

    conn.execute(
        "UPDATE source_claims SET claim_type=?, source_quote=?, "
        "faithful_paraphrase=?, evidence_basis_description=?, "
        "record_review_status='approved_with_edits', updated_at=? "
        "WHERE claim_id=?",
        (ed_type, ed_quote, ed_para, ed_basis, now, claim_id))


def _apply_reject(
    conn: Any, rid: str, claim_id: str, orig: str,
    row: dict[str, str],
    batch_id: str, row_id: str, now: str,
) -> None:
    conn.execute(
        "INSERT INTO review_decisions (review_id, object_type, "
        "object_id, decision, original_content_json, reviewer, "
        "review_reason, review_batch_id, review_row_id, reviewed_at) "
        "VALUES (?, 'claim', ?, ?, ?, ?, ?, ?, ?, ?)",
        (rid, claim_id, "reject", orig,
         row.get("reviewer", "unknown"),
         row.get("review_reason", ""),
         batch_id or None, row_id or None, now))
    conn.execute(
        "UPDATE source_claims SET record_review_status='rejected', "
        "updated_at=? WHERE claim_id=?", (now, claim_id))


def _apply_mark_missing(
    conn: Any, rid: str, claim_id: str, orig: str,
    row: dict[str, str],
    batch_id: str, row_id: str, now: str,
) -> None:
    conn.execute(
        "INSERT INTO review_decisions (review_id, object_type, "
        "object_id, decision, original_content_json, reviewer, "
        "review_reason, review_batch_id, review_row_id, reviewed_at) "
        "VALUES (?, 'claim', ?, ?, ?, ?, ?, ?, ?, ?)",
        (rid, claim_id, "mark_missing", orig,
         row.get("reviewer", "unknown"),
         row.get("review_reason", ""),
         batch_id or None, row_id or None, now))


def _apply_needs_followup(
    conn: Any, rid: str, claim_id: str, orig: str,
    row: dict[str, str],
    batch_id: str, row_id: str, now: str,
) -> None:
    conn.execute(
        "INSERT INTO review_decisions (review_id, object_type, "
        "object_id, decision, original_content_json, reviewer, "
        "review_reason, review_batch_id, review_row_id, reviewed_at) "
        "VALUES (?, 'claim', ?, ?, ?, ?, ?, ?, ?, ?)",
        (rid, claim_id, "needs_followup", orig,
         row.get("reviewer", "unknown"),
         row.get("review_reason", ""),
         batch_id or None, row_id or None, now))


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


def _error_report(rows: list[dict[str, Any]], errors: list[str]) -> dict[str, Any]:
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
