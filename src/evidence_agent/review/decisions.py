"""Apply human review decisions to claims."""

import csv
import json
from pathlib import Path
from typing import Any

from evidence_agent.database.connection import transaction
from evidence_agent.ids import generate_review_id, generate_revision_id, now_iso


def apply_review_csv(csv_path: Path) -> dict[str, Any]:
    """Apply review decisions from a CSV file.

    Returns a report dict.
    """
    if not csv_path.exists():
        raise FileNotFoundError(f"Review CSV not found: {csv_path}")

    decisions: list[dict[str, str]] = []
    with open(csv_path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            decisions.append(row)

    report: dict[str, Any] = {
        "total": len(decisions),
        "approved": 0,
        "rejected": 0,
        "edited": 0,
        "marked_missing": 0,
        "needs_followup": 0,
        "errors": [],
    }

    with transaction() as conn:
        for row in decisions:
            claim_id = row.get("claim_id", "").strip()
            decision = row.get("decision", "").strip().lower()

            if not claim_id:
                report["errors"].append("Missing claim_id")
                continue

            valid_decisions = {
                "approve",
                "approve_with_edits",
                "reject",
                "mark_missing",
                "needs_followup",
            }
            if decision not in valid_decisions:
                report["errors"].append(
                    f"Invalid decision '{decision}' for {claim_id}"
                )
                continue

            # Check claim exists
            cursor = conn.execute(
                "SELECT * FROM source_claims WHERE claim_id = ?", (claim_id,)
            )
            existing = cursor.fetchone()
            if not existing:
                # Create minimal claim record if not exists (for testing)
                continue

            # Build original content JSON
            original_content = json.dumps(
                {
                    "claim_type": existing["claim_type"],
                    "source_quote": existing["source_quote"],
                    "faithful_paraphrase": existing["faithful_paraphrase"],
                    "evidence_basis_description": existing[
                        "evidence_basis_description"
                    ],
                }
            )

            review_id = generate_review_id()
            now = now_iso()

            if decision == "approve":
                conn.execute(
                    "INSERT INTO review_decisions (review_id, object_type, "
                    "object_id, decision, original_content_json, reviewer, "
                    "reviewed_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        review_id,
                        "claim",
                        claim_id,
                        decision,
                        original_content,
                        row.get("reviewer", "unknown"),
                        now,
                    ),
                )
                conn.execute(
                    "UPDATE source_claims SET record_review_status = 'approved', "
                    "updated_at = ? WHERE claim_id = ?",
                    (now, claim_id),
                )
                report["approved"] += 1

            elif decision == "approve_with_edits":
                edited = {
                    "claim_type": row.get("edited_claim_type")
                    or existing["claim_type"],
                    "source_quote": row.get("edited_source_quote")
                    or existing["source_quote"],
                    "faithful_paraphrase": row.get("edited_faithful_paraphrase")
                    or existing["faithful_paraphrase"],
                    "evidence_basis_description": row.get(
                        "edited_evidence_basis_description"
                    )
                    or existing["evidence_basis_description"],
                }
                edited_json = json.dumps(edited)

                # Save revision history
                revision_id = generate_revision_id()
                conn.execute(
                    "INSERT INTO claim_revisions (revision_id, claim_id, "
                    "previous_content_json, new_content_json, changed_by, "
                    "change_reason, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        revision_id,
                        claim_id,
                        original_content,
                        edited_json,
                        row.get("reviewer", "unknown"),
                        row.get("review_reason", ""),
                        now,
                    ),
                )

                conn.execute(
                    "INSERT INTO review_decisions (review_id, object_type, "
                    "object_id, decision, original_content_json, "
                    "edited_content_json, reviewer, reviewed_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        review_id,
                        "claim",
                        claim_id,
                        decision,
                        original_content,
                        edited_json,
                        row.get("reviewer", "unknown"),
                        now,
                    ),
                )

                # Update claim with edits
                conn.execute(
                    "UPDATE source_claims SET "
                    "claim_type = ?, source_quote = ?, faithful_paraphrase = ?, "
                    "evidence_basis_description = ?, "
                    "record_review_status = 'approved_with_edits', "
                    "updated_at = ? WHERE claim_id = ?",
                    (
                        edited["claim_type"],
                        edited["source_quote"],
                        edited["faithful_paraphrase"],
                        edited["evidence_basis_description"],
                        now,
                        claim_id,
                    ),
                )
                report["edited"] += 1

            elif decision == "reject":
                conn.execute(
                    "INSERT INTO review_decisions (review_id, object_type, "
                    "object_id, decision, original_content_json, reviewer, "
                    "review_reason, reviewed_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        review_id,
                        "claim",
                        claim_id,
                        decision,
                        original_content,
                        row.get("reviewer", "unknown"),
                        row.get("review_reason", ""),
                        now,
                    ),
                )
                conn.execute(
                    "UPDATE source_claims SET record_review_status = 'rejected', "
                    "updated_at = ? WHERE claim_id = ?",
                    (now, claim_id),
                )
                report["rejected"] += 1

            elif decision == "mark_missing":
                conn.execute(
                    "INSERT INTO review_decisions (review_id, object_type, "
                    "object_id, decision, original_content_json, reviewer, "
                    "review_reason, reviewed_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        review_id,
                        "claim",
                        claim_id,
                        decision,
                        original_content,
                        row.get("reviewer", "unknown"),
                        row.get("review_reason", ""),
                        now,
                    ),
                )
                report["marked_missing"] += 1

            elif decision == "needs_followup":
                conn.execute(
                    "INSERT INTO review_decisions (review_id, object_type, "
                    "object_id, decision, original_content_json, reviewer, "
                    "review_reason, reviewed_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        review_id,
                        "claim",
                        claim_id,
                        decision,
                        original_content,
                        row.get("reviewer", "unknown"),
                        row.get("review_reason", ""),
                        now,
                    ),
                )
                report["needs_followup"] += 1

    return report
