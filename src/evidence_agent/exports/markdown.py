"""Export source records as Markdown or JSONL."""

import json
from pathlib import Path
from typing import Any

from evidence_agent.database.connection import get_connection


def export_source_markdown(
    source_id: str, output_path: Path, include_pending: bool = False
) -> str:
    """Export a source's claims as a Markdown report."""
    with get_connection(read_only=True) as conn:
        # Source info
        cursor = conn.execute(
            "SELECT * FROM sources WHERE source_id = ?", (source_id,)
        )
        source = cursor.fetchone()
        if not source:
            raise ValueError(f"Source not found: {source_id}")

        # Claims
        status_filter = (
            "('approved', 'approved_with_edits')"
            if not include_pending
            else "('approved', 'approved_with_edits', 'pending')"
        )
        cursor = conn.execute(
            f"SELECT c.*, l.page FROM source_claims c "
            f"LEFT JOIN claim_locators l ON c.claim_id = l.claim_id "
            f"WHERE c.source_id = ? AND c.record_review_status IN {status_filter} "
            f"ORDER BY l.page, c.claim_type",
            (source_id,),
        )
        claims = cursor.fetchall()

        # Count rejected
        cursor = conn.execute(
            "SELECT COUNT(*) FROM source_claims "
            "WHERE source_id = ? AND record_review_status = 'rejected'",
            (source_id,),
        )
        rejected_count = cursor.fetchone()[0]

        lines: list[str] = []
        lines.append(f"# Source Record: {source['title'] or source_id}\n")
        lines.append("## Source Identity\n")
        lines.append(f"- **Source ID:** {source['source_id']}")
        lines.append(f"- **Type:** {source['source_type']}")
        lines.append(f"- **SHA-256:** {source['original_file_sha256']}")
        lines.append("- **Origin:** External")
        lines.append(
            f"- **Scientific Verification:** {source['scientific_verification_status']}\n"
        )
        lines.append(
            "> ⚠️ All claims below are from an **external source** "
            "and have **not been internally verified**.\n"
        )

        lines.append(f"## Claims ({len(claims)} approved)\n")

        for claim in claims:
            claim_id = claim["claim_id"]
            lines.append(f"### {claim_id}\n")
            lines.append(f"- **Type:** {claim['claim_type']}")
            lines.append(f"- **Page:** {claim['page'] or 'N/A'}")
            lines.append(f"- **Review:** {claim['record_review_status']}\n")
            lines.append(f"> {claim['source_quote']}\n")
            lines.append(f"**Paraphrase:** {claim['faithful_paraphrase']}\n")
            lines.append(f"**Evidence:** {claim['evidence_basis_description']}\n")

            if claim.get("author_hedging"):
                lines.append(
                    f"**Author Hedging:** `{claim['author_hedging']}`\n"
                )

            lines.append("---\n")

        lines.append("## Summary\n")
        lines.append(f"- **Approved claims:** {len(claims)}")
        lines.append(f"- **Rejected claims:** {rejected_count}")
        lines.append(
            "- **External source, scientific status: unverified**\n"
        )

        content = "\n".join(lines)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(content, encoding="utf-8")

        return content


def export_source_jsonl(
    source_id: str, output_path: Path, include_pending: bool = False
) -> list[dict[str, Any]]:
    """Export a source's claims as JSONL."""
    with get_connection(read_only=True) as conn:
        status_filter = (
            "('approved', 'approved_with_edits')"
            if not include_pending
            else "('approved', 'approved_with_edits', 'pending')"
        )
        cursor = conn.execute(
            f"SELECT c.*, l.page FROM source_claims c "
            f"LEFT JOIN claim_locators l ON c.claim_id = l.claim_id "
            f"WHERE c.source_id = ? AND c.record_review_status IN {status_filter} "
            f"ORDER BY l.page",
            (source_id,),
        )
        claims: list[dict[str, Any]] = [dict(row) for row in cursor.fetchall()]

        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            for claim in claims:
                claim["_note"] = (
                    "External source, scientific status: unverified"
                )
                f.write(json.dumps(claim, ensure_ascii=False) + "\n")

        return claims
