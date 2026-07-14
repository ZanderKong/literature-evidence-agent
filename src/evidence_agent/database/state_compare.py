"""Database state comparison — canonical summary and diff between two DBs."""

import hashlib
import sqlite3
from pathlib import Path
from typing import Any


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
        if cnt > 0:
            ti["id_set_hash"] = _id_hash(conn, table)
            ti["content_hash"] = _content_hash(conn, table)
        summary["tables"][table] = ti
    conn.close()
    return summary


def _id_hash(conn: sqlite3.Connection, table: str) -> str:
    try:
        rows = conn.execute(
            f"SELECT * FROM \"{table}\" ORDER BY rowid"
        ).fetchall()
    except Exception:
        return "N/A"
    if not rows:
        return "empty"
    first = dict(rows[0])
    for col in first:
        if "id" in col.lower() or col.endswith("_id"):
            ids = sorted(str(r[col]) for r in rows if r[col] is not None)
            h = hashlib.sha256()
            for i in ids:
                h.update(i.encode())
            return h.hexdigest()
    return "no_id_col"


def _content_hash(conn: sqlite3.Connection, table: str) -> str:
    try:
        rows = conn.execute(
            f"SELECT * FROM \"{table}\" ORDER BY rowid"
        ).fetchall()
    except Exception:
        return "N/A"
    h = hashlib.sha256()
    for row in rows:
        h.update("|".join(str(v) for v in row).encode())
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
        ha = sa["tables"][table].get("id_set_hash")
        hb = sb["tables"][table].get("id_set_hash")
        if ha and hb and ha != hb:
            diffs.append(f"{table}: id_set differs")
            ok = False
        ca_h = sa["tables"][table].get("content_hash")
        cb_h = sb["tables"][table].get("content_hash")
        if ca_h and cb_h and ca_h != cb_h:
            diffs.append(f"{table}: content differs")
            ok = False
        da = sa["tables"][table].get("review_distribution")
        db_dist = sb["tables"][table].get("review_distribution")
        if da and db_dist and da != db_dist:
            diffs.append(f"{table}: review_dist differs")
            ok = False
    fa = _fts_hash(db_a)
    fb = _fts_hash(db_b)
    if fa != fb:
        diffs.append("FTS results differ")
        ok = False
    return {
        "identical": ok, "differences": diffs,
        "summary_a": sa, "summary_b": sb,
    }


def _fts_hash(db_path: Path) -> str:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    h = hashlib.sha256()
    for term in ["test", "quote", "approve"]:
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
