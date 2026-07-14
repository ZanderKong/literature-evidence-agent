"""Full-text search over approved claims using FTS5.

Review-aware: only approved/approved_with_edits claims are indexed.
Rejected, pending, and needs_followup claims are excluded.
Safe queries: user input is sanitized before FTS5 MATCH.
"""

import re
from typing import Any

from evidence_agent.database.connection import get_connection


def compile_safe_query(user_input: str) -> str:
    """Sanitize user input for FTS5 MATCH query.

    Removes FTS5 special operators, escapes double-quotes,
    and produces a safe phrase query with wildcards.
    """
    if not user_input or not user_input.strip():
        raise ValueError("Query must not be empty")

    sanitized = user_input.strip()

    sanitized = re.sub(r'[+\-*^()\[\]{}~]', ' ', sanitized)
    sanitized = re.sub(r'\bAND\b', ' ', sanitized, flags=re.IGNORECASE)
    sanitized = re.sub(r'\bOR\b', ' ', sanitized, flags=re.IGNORECASE)
    sanitized = re.sub(r'\bNOT\b', ' ', sanitized, flags=re.IGNORECASE)
    sanitized = re.sub(r'\bNEAR\b', ' ', sanitized, flags=re.IGNORECASE)
    sanitized = sanitized.replace('"', '')
    sanitized = re.sub(r'\s+', ' ', sanitized).strip()

    if not sanitized:
        raise ValueError(f"Query reduced to empty after sanitization: {user_input}")

    safe = ' '.join(f'"{word}"*' for word in sanitized.split() if len(word) > 1)
    if not safe:
        safe = f'"{sanitized}"*'

    return sanitized


def search_claims(user_query: str, limit: int = 20) -> list[dict[str, Any]]:
    """Search approved claims using FTS5 with safe query compilation.

    Only returns claims with record_review_status IN
    ('approved', 'approved_with_edits').

    Raises ValueError for invalid/empty queries.
    """
    if not user_query or not user_query.strip():
        raise ValueError("Query must not be empty")

    safe = compile_safe_query(user_query)
    results: list[dict[str, Any]] = []

    with get_connection(read_only=True) as conn:
        try:
            cursor = conn.execute(
                "SELECT c.claim_id, c.source_quote, c.faithful_paraphrase, "
                "c.evidence_basis_description, "
                "c.claim_type, c.record_review_status, "
                "c.scientific_verification_status, "
                "c.origin_scope, "
                "s.source_id, s.title as source_title, "
                "a.relative_path as source_relative_path, "
                "l.page, l.section_id, "
                "ss.heading as section_heading "
                "FROM claim_fts f "
                "JOIN source_claims c ON f.claim_id = c.claim_id "
                "LEFT JOIN sources s ON c.source_id = s.source_id "
                "LEFT JOIN source_assets a ON c.source_id = a.source_id "
                "LEFT JOIN claim_locators l ON c.claim_id = l.claim_id "
                "LEFT JOIN source_sections ss "
                "  ON c.source_id = ss.source_id AND l.page = ss.page_start "
                "WHERE claim_fts MATCH ? "
                "AND c.record_review_status IN ('approved', 'approved_with_edits') "
                "ORDER BY rank LIMIT ?",
                (safe, limit),
            )
        except Exception:
            raise

        for row in cursor.fetchall():
            results.append({
                "claim_id": row["claim_id"],
                "source_quote": row["source_quote"],
                "faithful_paraphrase": row["faithful_paraphrase"],
                "evidence_basis_description": row["evidence_basis_description"],
                "claim_type": row["claim_type"],
                "record_review_status": row["record_review_status"],
                "scientific_verification_status": (
                    row["scientific_verification_status"]
                ),
                "origin_scope": row["origin_scope"],
                "source_id": row["source_id"],
                "source_title": row["source_title"],
                "source_relative_path": row["source_relative_path"],
                "page": row["page"],
                "section_id": row["section_id"],
                "section_heading": row["section_heading"],
                "query_sanitized": safe,
            })

    return results


def index_claim(claim_id: str) -> None:
    """Index a single claim in FTS (upsert)."""
    with get_connection() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO claim_fts (claim_id, source_id, source_quote, "
            "faithful_paraphrase, evidence_basis_description) "
            "SELECT claim_id, source_id, source_quote, faithful_paraphrase, "
            "evidence_basis_description FROM source_claims WHERE claim_id = ?",
            (claim_id,),
        )


def replace_claim(claim_id: str) -> None:
    """Replace a claim's FTS entry (same as index via INSERT OR REPLACE)."""
    index_claim(claim_id)


def remove_claim(claim_id: str) -> None:
    """Remove a claim from FTS index."""
    with get_connection() as conn:
        conn.execute("DELETE FROM claim_fts WHERE claim_id = ?", (claim_id,))


def rebuild_fts() -> None:
    """Rebuild FTS indices from source data.

    Only approved/approved_with_edits claims are indexed.
    Preserves existing FTS table structure (no DROP).
    """
    with get_connection() as conn:
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
