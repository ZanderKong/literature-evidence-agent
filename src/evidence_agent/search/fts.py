"""Full-text search over approved claims using FTS5."""

from typing import Any

from evidence_agent.database.connection import get_connection


def search_claims(
    query: str, limit: int = 20
) -> list[dict[str, Any]]:
    """Search approved claims using FTS5.

    Returns only approved and approved_with_edits claims.
    """
    with get_connection(read_only=True) as conn:
        # Sync FTS content for approved claims
        _sync_claim_fts(conn)

        results: list[dict[str, Any]] = []
        try:
            cursor = conn.execute(
                "SELECT c.claim_id, c.source_quote, c.faithful_paraphrase, "
                "c.claim_type, c.record_review_status, "
                "c.scientific_verification_status, "
                "s.source_id, s.title as source_title, "
                "l.page "
                "FROM claim_fts f "
                "JOIN source_claims c ON f.claim_id = c.claim_id "
                "LEFT JOIN sources s ON c.source_id = s.source_id "
                "LEFT JOIN claim_locators l ON c.claim_id = l.claim_id "
                "WHERE claim_fts MATCH ? "
                "AND c.record_review_status IN ('approved', 'approved_with_edits') "
                "ORDER BY rank "
                "LIMIT ?",
                (query, limit),
            )
            for row in cursor.fetchall():
                results.append(
                    {
                        "claim_id": row["claim_id"],
                        "source_quote": row["source_quote"],
                        "faithful_paraphrase": row["faithful_paraphrase"],
                        "claim_type": row["claim_type"],
                        "record_review_status": row["record_review_status"],
                        "scientific_verification_status": row[
                            "scientific_verification_status"
                        ],
                        "source_id": row["source_id"],
                        "source_title": row["source_title"],
                        "page": row["page"],
                        "origin_scope": "external",
                        "_note": "External source, scientific status: unverified",
                    }
                )
        except Exception:
            # FTS may not be populated yet
            pass

        return results


def rebuild_fts() -> None:
    """Rebuild FTS indices from the source tables."""
    with get_connection() as conn:
        # Clear existing
        conn.execute("DELETE FROM claim_fts")
        conn.execute("DELETE FROM source_fts")

        # Rebuild source FTS
        conn.execute(
            "INSERT INTO source_fts (source_id, title, section_text) "
            "SELECT source_id, title, '' FROM sources"
        )

        # Rebuild claim FTS (only approved)
        conn.execute(
            "INSERT INTO claim_fts (claim_id, source_id, source_quote, "
            "faithful_paraphrase, evidence_basis_description) "
            "SELECT claim_id, source_id, source_quote, faithful_paraphrase, "
            "evidence_basis_description FROM source_claims "
            "WHERE record_review_status IN ('approved', 'approved_with_edits')"
        )


def _sync_claim_fts(conn: Any) -> None:
    """Sync approved claims into FTS if not already indexed."""
    conn.execute(
        "INSERT OR IGNORE INTO claim_fts (claim_id, source_id, source_quote, "
        "faithful_paraphrase, evidence_basis_description) "
        "SELECT claim_id, source_id, source_quote, faithful_paraphrase, "
        "evidence_basis_description FROM source_claims "
        "WHERE record_review_status IN ('approved', 'approved_with_edits')"
    )
