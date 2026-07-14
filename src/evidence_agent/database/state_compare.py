"""Database state comparison — canonical summary and diff between two DBs.

Explicit PK and sort order per table. Canonical row hashing using JSON.
Comprehensive comparison: counts, ID sets, row hashes, review distributions,
decisions, revisions, runs, locators, entity links. FTS from real query fixtures.
"""

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any

TABLE_PK_SORT = {
    "research_tasks": ("task_id", "task_id"),
    "sources": ("source_id", "source_id"),
    "source_assets": ("asset_id", "asset_id"),
    "source_sections": ("section_id", "section_id"),
    "processing_runs": ("run_id", "run_id"),
    "source_claims": ("claim_id", "claim_id"),
    "claim_locators": ("locator_id", "claim_id, locator_id"),
    "entities": ("entity_id", "entity_id"),
    "claim_entity_links": ("link_id", "claim_id, entity_id"),
    "review_batches": ("review_batch_id", "run_id, review_batch_id"),
    "review_batch_rows": ("review_row_id", "review_batch_id, row_sequence"),
    "review_decisions": ("review_id", "object_id, reviewed_at"),
    "claim_revisions": ("revision_id", "claim_id, created_at"),
}


def snapshot_summary(db_path: Path) -> dict[str, Any]:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    summary: dict[str, Any] = {
        "database": str(db_path), "tables": {},
        "integrity": None, "foreign_keys": None,
    }
    cur = conn.execute("PRAGMA integrity_check")
    summary["integrity"] = cur.fetchone()[0]
    cur = conn.execute("PRAGMA foreign_key_check")
    fk = cur.fetchall()
    summary["foreign_keys"] = "ok" if not fk else str(len(fk))
    cur = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    )
    tables = [r[0] for r in cur.fetchall()]
    for table in tables:
        try:
            cnt = conn.execute(
                f"SELECT COUNT(*) FROM \"{table}\""
            ).fetchone()[0]
        except Exception:
            cnt = -1
        ti: dict[str, Any] = {"count": cnt}
        if table == "source_claims" and cnt > 0:
            d = conn.execute(
                "SELECT record_review_status, COUNT(*) "
                "FROM source_claims GROUP BY record_review_status"
            ).fetchall()
            ti["review_distribution"] = {r[0]: r[1] for r in d}
        if cnt > 0 and table in TABLE_PK_SORT:
            ti["id_set_hash"] = _canonical_id_hash(conn, table)
            ti["content_hash"] = _canonical_content_hash(conn, table)
        summary["tables"][table] = ti
    conn.close()
    return summary


def _canonical_id_hash(conn: sqlite3.Connection, table: str) -> str:
    pk, _sort = TABLE_PK_SORT.get(table, ("rowid", "rowid"))
    try:
        rows = conn.execute(
            f"SELECT \"{pk}\" FROM \"{table}\" ORDER BY \"{pk}\""
        ).fetchall()
    except Exception:
        return "N/A"
    ids = sorted(str(r[pk]) for r in rows if r[pk] is not None)
    h = hashlib.sha256()
    for i in ids:
        h.update(i.encode())
    return h.hexdigest()


def _canonical_content_hash(conn: sqlite3.Connection, table: str) -> str:
    pk, sort_cols = TABLE_PK_SORT.get(table, ("rowid", "rowid"))
    try:
        rows = conn.execute(
            f"SELECT * FROM \"{table}\" ORDER BY {sort_cols}"
        ).fetchall()
    except Exception:
        return "N/A"
    h = hashlib.sha256()
    for row in rows:
        d = dict(row)
        canonical = json.dumps(d, ensure_ascii=False, sort_keys=True,
                               separators=(",", ":"))
        h.update(canonical.encode())
    return h.hexdigest()


def compare_databases(db_a: Path, db_b: Path) -> dict[str, Any]:
    if not db_a.exists():
        return {"error": f"DB A not found: {db_a}", "different": True}
    if not db_b.exists():
        return {"error": f"DB B not found: {db_b}", "different": True}
    sa = snapshot_summary(db_a)
    sb = snapshot_summary(db_b)
    diffs: list[str] = []
    ok = True

    if sa["integrity"] != "ok":
        diffs.append(f"DB A integrity: {sa['integrity']}")
        ok = False
    if sb["integrity"] != "ok":
        diffs.append(f"DB B integrity: {sb['integrity']}")
        ok = False

    ta = set(sa["tables"].keys())
    tb = set(sb["tables"].keys())
    for t in ta - tb:
        diffs.append(f"Tables only in A: {t}")
        ok = False
    for t in tb - ta:
        diffs.append(f"Tables only in B: {t}")
        ok = False

    for table in ta & tb:
        ca = sa["tables"][table].get("count", -1)
        cb = sb["tables"][table].get("count", -1)
        if ca != cb:
            diffs.append(f"{table}: count A={ca} B={cb}")
            ok = False

        for keyname in ("id_set_hash", "content_hash", "review_distribution"):
            va = sa["tables"][table].get(keyname)
            vb = sb["tables"][table].get(keyname)
            if va is not None and vb is not None and va != vb:
                diffs.append(f"{table}: {keyname} differs")
                ok = False

    fa = _fts_hash_from_real_queries(db_a)
    fb = _fts_hash_from_real_queries(db_b)
    if fa != fb:
        diffs.append("FTS results differ")
        ok = False

    return {
        "identical": ok, "differences": diffs,
        "summary_a": sa, "summary_b": sb,
    }


def _fts_hash_from_real_queries(db_path: Path) -> str:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    query_terms: list[str] = []
    try:
        rows = conn.execute(
            "SELECT DISTINCT source_quote FROM source_claims "
            "WHERE record_review_status IN ('approved', 'approved_with_edits') "
            "AND source_quote IS NOT NULL AND source_quote != '' "
            "ORDER BY claim_id LIMIT 10"
        ).fetchall()
        for r in rows:
            words = str(r["source_quote"]).split()
            for w in words[:3]:
                clean = "".join(c for c in w if c.isalnum())
                if len(clean) > 2 and clean.lower() not in \
                   ("the", "and", "was", "for", "with", "that", "this", "from"):
                    query_terms.append(clean)
    except Exception:
        pass

    if not query_terms:
        query_terms = ["test", "approve"]

    h = hashlib.sha256()
    for term in query_terms[:5]:
        try:
            c = conn.execute(
                "SELECT claim_id FROM claim_fts WHERE claim_fts MATCH ? ORDER BY 1",
                (term,),
            )
            for r in c.fetchall():
                h.update(str(r["claim_id"]).encode())
        except Exception:
            h.update(b"err")
    conn.close()
    return h.hexdigest()
