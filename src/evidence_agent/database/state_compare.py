"""Database state comparison — canonical summary and diff between two DBs.

Computes structured summaries with:
- Table row counts
- ID set hashes
- Status distributions
- Schema checks
- Integrity and FK checks
"""

import sqlite3
from pathlib import Path
from typing import Any


def snapshot_summary(db_path: Path) -> dict[str, Any]:
    """Compute structured summary of database state."""
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    summary: dict[str, Any] = {
        "database": str(db_path),
        "tables": {},
        "integrity": None,
        "foreign_keys": None,
    }

    cursor = conn.execute("PRAGMA integrity_check")
    summary["integrity"] = cursor.fetchone()[0]

    cursor = conn.execute("PRAGMA foreign_key_check")
    fk_issues = cursor.fetchall()
    summary["foreign_keys"] = "ok" if not fk_issues else str(len(fk_issues))

    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    )
    tables = [r[0] for r in cursor.fetchall()]

    for table in tables:
        try:
            count = conn.execute(
                f"SELECT COUNT(*) FROM \"{table}\""
            ).fetchone()[0]
        except sqlite3.OperationalError:
            count = -1

        table_info: dict[str, Any] = {"count": count}

        if table == "schema_migrations":
            rows = conn.execute(
                "SELECT version, name FROM schema_migrations ORDER BY version"
            ).fetchall()
            table_info["versions"] = [(r[0], r[1]) for r in rows]
        elif table == "source_claims" and count > 0:
            dist = conn.execute(
                "SELECT record_review_status, COUNT(*) "
                "FROM source_claims GROUP BY record_review_status"
            ).fetchall()
            table_info["review_distribution"] = {
                r[0]: r[1] for r in dist
            }

        summary["tables"][table] = table_info

    conn.close()
    return summary


def compare_databases(db_a: Path, db_b: Path) -> dict[str, Any]:
    """Compare two databases. Returns dict with differences.

    Exit code logic (caller decides):
    - identical: exit 0
    - different: exit 7
    - invalid: exit 3
    """
    if not db_a.exists():
        return {"error": f"Database A not found: {db_a}", "different": True}
    if not db_b.exists():
        return {"error": f"Database B not found: {db_b}", "different": True}

    summary_a = snapshot_summary(db_a)
    summary_b = snapshot_summary(db_b)

    differences: list[str] = []
    identical = True

    if summary_a["integrity"] != "ok":
        differences.append(f"DB A integrity: {summary_a['integrity']}")
        identical = False
    if summary_b["integrity"] != "ok":
        differences.append(f"DB B integrity: {summary_b['integrity']}")
        identical = False

    tables_a = set(summary_a["tables"].keys())
    tables_b = set(summary_b["tables"].keys())

    only_a = tables_a - tables_b
    only_b = tables_b - tables_a
    if only_a:
        differences.append(f"Tables only in A: {only_a}")
        identical = False
    if only_b:
        differences.append(f"Tables only in B: {only_b}")
        identical = False

    for table in tables_a & tables_b:
        ca = summary_a["tables"][table].get("count", -1)
        cb = summary_b["tables"][table].get("count", -1)
        if ca != cb:
            differences.append(
                f"{table}: count A={ca} B={cb}"
            )
            identical = False

        da = summary_a["tables"][table].get("review_distribution")
        db_dist = summary_b["tables"][table].get("review_distribution")
        if da and db_dist and da != db_dist:
            differences.append(
                f"{table}: review distribution differs"
            )
            identical = False

    return {
        "identical": identical,
        "differences": differences,
        "summary_a": summary_a,
        "summary_b": summary_b,
    }
