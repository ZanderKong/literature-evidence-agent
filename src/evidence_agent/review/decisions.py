"""Apply human review decisions with revalidation and FTS sync."""

import csv
import json
from pathlib import Path
from typing import Any

from evidence_agent.database.connection import transaction
from evidence_agent.ids import generate_review_id, generate_revision_id, now_iso


def apply_review_csv(csv_path: Path) -> dict[str, Any]:
    """Apply review decisions from CSV. With edit revalidation and idempotency."""
    if not csv_path.exists():
        raise FileNotFoundError(f"Review CSV not found: {csv_path}")

    rows: list[dict[str, str]] = []
    with open(csv_path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)

    report: dict[str, Any] = {
        "total": len(rows),
        "approved": 0, "rejected": 0, "edited": 0,
        "marked_missing": 0, "needs_followup": 0,
        "skipped": 0, "errors": [],
    }

    with transaction() as conn:
        for row in rows:
            claim_id = (row.get("claim_id") or "").strip()
            decision = (row.get("decision") or "").strip().lower()

            if not claim_id:
                report["errors"].append("Missing claim_id")
                continue

            valid = {"approve", "approve_with_edits", "reject",
                     "mark_missing", "needs_followup"}
            if decision not in valid:
                report["errors"].append(f"Invalid decision '{decision}' for {claim_id}")
                continue

            # Get existing claim
            cursor = conn.execute(
                "SELECT * FROM source_claims WHERE claim_id = ?", (claim_id,)
            )
            existing = cursor.fetchone()
            if not existing:
                report["errors"].append(f"Claim not found: {claim_id}")
                continue

            # Check already applied (idempotent)
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
                "claim_type": existing["claim_type"],
                "source_quote": existing["source_quote"],
                "faithful_paraphrase": existing["faithful_paraphrase"],
                "evidence_basis_description": existing["evidence_basis_description"],
            })

            if decision == "approve":
                conn.execute(
                    "INSERT INTO review_decisions (review_id, object_type, "
                    "object_id, decision, original_content_json, reviewer, "
                    "reviewed_at) VALUES (?, 'claim', ?, ?, ?, ?, ?)",
                    (rid, claim_id, decision, orig,
                     row.get("reviewer", "unknown"), now),
                )
                conn.execute(
                    "UPDATE source_claims SET record_review_status='approved', "
                    "updated_at=? WHERE claim_id=?", (now, claim_id))
                report["approved"] += 1
                _sync_fts_insert(conn, claim_id)

            elif decision == "approve_with_edits":
                # Get edited values
                ed_quote = row.get("edited_source_quote") or existing["source_quote"]
                ed_para = row.get("edited_faithful_paraphrase") or existing["faithful_paraphrase"]
                raw_ed_basis = row.get("edited_evidence_basis_description")
                ed_basis = raw_ed_basis or existing["evidence_basis_description"]
                ed_type = row.get("edited_claim_type") or existing["claim_type"]

                # Revalidate quote against source text
                from evidence_agent.validators.quote import match_quote
                cursor2 = conn.execute(
                    "SELECT ss.text FROM source_sections ss "
                    "JOIN source_claims sc ON sc.source_id = ss.source_id "
                    "WHERE sc.claim_id = ?", (claim_id,)
                )
                section_text = " ".join(r[0] for r in cursor2.fetchall() if r[0])
                if section_text:
                    ms, _, _ = match_quote(ed_quote, section_text)
                    if ms not in ("exact", "normalised"):
                        report["errors"].append(
                            f"Edited quote not found in source for {claim_id}: {ms}")
                        continue

                # Validate claim type
                valid_types = {
                    "background_statement", "method_statement",
                    "reported_observation", "reported_result",
                    "author_interpretation", "author_conclusion",
                    "author_hypothesis", "author_limitation", "future_work",
                }
                if ed_type not in valid_types:
                    report["errors"].append(f"Invalid claim_type: {ed_type}")
                    continue

                edited = {"claim_type": ed_type, "source_quote": ed_quote,
                          "faithful_paraphrase": ed_para,
                          "evidence_basis_description": ed_basis}
                ed_json = json.dumps(edited)

                # Revision history
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
                    (rid, claim_id, decision, orig, ed_json,
                     row.get("reviewer", "unknown"), now))

                # Update claim
                conn.execute(
                    "UPDATE source_claims SET claim_type=?, source_quote=?, "
                    "faithful_paraphrase=?, evidence_basis_description=?, "
                    "record_review_status='approved_with_edits', updated_at=? "
                    "WHERE claim_id=?",
                    (ed_type, ed_quote, ed_para, ed_basis, now, claim_id))
                report["edited"] += 1
                _sync_fts_replace(conn, claim_id)

            elif decision == "reject":
                conn.execute(
                    "INSERT INTO review_decisions (review_id, object_type, "
                    "object_id, decision, original_content_json, reviewer, "
                    "review_reason, reviewed_at) VALUES (?, 'claim', ?, ?, ?, ?, ?, ?)",
                    (rid, claim_id, decision, orig,
                     row.get("reviewer", "unknown"),
                     row.get("review_reason", ""), now))
                conn.execute(
                    "UPDATE source_claims SET record_review_status='rejected', "
                    "updated_at=? WHERE claim_id=?", (now, claim_id))
                report["rejected"] += 1
                _sync_fts_remove(conn, claim_id)

            elif decision == "mark_missing":
                conn.execute(
                    "INSERT INTO review_decisions (review_id, object_type, "
                    "object_id, decision, original_content_json, reviewer, "
                    "review_reason, reviewed_at) VALUES (?, 'claim', ?, ?, ?, ?, ?, ?)",
                    (rid, claim_id, decision, orig,
                     row.get("reviewer", "unknown"),
                     row.get("review_reason", ""), now))
                report["marked_missing"] += 1

            elif decision == "needs_followup":
                conn.execute(
                    "INSERT INTO review_decisions (review_id, object_type, "
                    "object_id, decision, original_content_json, reviewer, "
                    "review_reason, reviewed_at) VALUES (?, 'claim', ?, ?, ?, ?, ?, ?)",
                    (rid, claim_id, decision, orig,
                     row.get("reviewer", "unknown"),
                     row.get("review_reason", ""), now))
                report["needs_followup"] += 1

    return report


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
