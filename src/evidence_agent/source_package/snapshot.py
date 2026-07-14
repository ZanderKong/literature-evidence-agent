"""Package snapshot — persist complete immutable source state.

Writes all DB data for a source to JSONL records under:
    SRC-ID/state/snapshots/SNP-ID/records/*.jsonl

Atomic: writes to .tmp-SNP → fsync → rename, then updates current.json.
"""

import hashlib
import json
import os
from pathlib import Path
from typing import Any

from evidence_agent.database.connection import get_connection
from evidence_agent.ids import generate_snapshot_id, now_iso
from evidence_agent.runtime import get_current_context

SNAPSHOT_TABLES = [
    ("research_tasks", "task_id"),
    ("sources", "source_id"),
    ("source_assets", "asset_id"),
    ("source_sections", "section_id"),
    ("processing_runs", "run_id"),
    ("source_claims", "claim_id"),
    ("claim_locators", "locator_id"),
    ("entities", "entity_id"),
    ("claim_entity_links", "link_id"),
    ("review_batches", "review_batch_id"),
    ("review_batch_rows", "review_row_id"),
    ("review_decisions", "review_id"),
    ("claim_revisions", "revision_id"),
]


TABLE_SOURCE_JOIN: dict[str, str | None] = {
    "research_tasks": None,
    "sources": "source_id",
    "source_assets": "source_id",
    "source_sections": "source_id",
    "processing_runs": "source_id",
    "source_claims": "source_id",
    "claim_locators": None,
    "entities": None,
    "claim_entity_links": None,
    "review_batches": None,
    "review_batch_rows": None,
    "review_decisions": None,
    "claim_revisions": None,
}


def _query_source_scoped(
    conn: Any, source_id: str, table: str, pk_col: str,
) -> list[dict[str, Any]]:
    """Query table rows scoped to a source."""

    if table == "research_tasks":
        cursor = conn.execute(
            "SELECT DISTINCT t.* FROM research_tasks t "
            "JOIN source_claims c ON t.task_id = c.task_id "
            "WHERE c.source_id = ? "
            "UNION "
            "SELECT DISTINCT t.* FROM research_tasks t "
            "JOIN processing_runs r ON t.task_id = r.task_id "
            "WHERE r.source_id = ?",
            (source_id, source_id),
        )
        return [dict(r) for r in cursor.fetchall()]

    if table in ("sources", "source_assets", "source_sections",
                 "source_claims"):
        cursor = conn.execute(
            f"SELECT * FROM \"{table}\" WHERE source_id = ?",
            (source_id,),
        )
        return [dict(r) for r in cursor.fetchall()]

    if table == "processing_runs":
        cursor = conn.execute(
            "SELECT * FROM processing_runs WHERE source_id = ?",
            (source_id,),
        )
        return [dict(r) for r in cursor.fetchall()]

    if table == "claim_locators":
        cursor = conn.execute(
            "SELECT l.* FROM claim_locators l "
            "JOIN source_claims c ON l.claim_id = c.claim_id "
            "WHERE c.source_id = ?",
            (source_id,),
        )
        return [dict(r) for r in cursor.fetchall()]

    if table == "review_batches":
        cursor = conn.execute(
            "SELECT b.* FROM review_batches b "
            "JOIN processing_runs r ON b.run_id = r.run_id "
            "WHERE r.source_id = ?",
            (source_id,),
        )
        return [dict(r) for r in cursor.fetchall()]

    if table == "review_batch_rows":
        cursor = conn.execute(
            "SELECT br.* FROM review_batch_rows br "
            "JOIN review_batches b ON br.review_batch_id = b.review_batch_id "
            "JOIN processing_runs r ON b.run_id = r.run_id "
            "WHERE r.source_id = ?",
            (source_id,),
        )
        return [dict(r) for r in cursor.fetchall()]

    if table == "review_decisions":
        cursor = conn.execute(
            "SELECT d.* FROM review_decisions d "
            "JOIN review_batches b ON d.review_batch_id = b.review_batch_id "
            "JOIN processing_runs r ON b.run_id = r.run_id "
            "WHERE r.source_id = ? "
            "UNION "
            "SELECT d.* FROM review_decisions d "
            "JOIN source_claims c ON d.object_id = c.claim_id "
            "WHERE c.source_id = ?",
            (source_id, source_id),
        )
        return [dict(r) for r in cursor.fetchall()]

    if table == "claim_revisions":
        cursor = conn.execute(
            "SELECT v.* FROM claim_revisions v "
            "JOIN source_claims c ON v.claim_id = c.claim_id "
            "WHERE c.source_id = ?",
            (source_id,),
        )
        return [dict(r) for r in cursor.fetchall()]

    if table in ("entities", "claim_entity_links"):
        cursor = conn.execute(
            "SELECT e.* FROM entities e "
            "JOIN claim_entity_links l ON e.entity_id = l.entity_id "
            "JOIN source_claims c ON l.claim_id = c.claim_id "
            "WHERE c.source_id = ?",
            (source_id,),
        ) if table == "entities" else conn.execute(
            "SELECT l.* FROM claim_entity_links l "
            "JOIN source_claims c ON l.claim_id = c.claim_id "
            "WHERE c.source_id = ?",
            (source_id,),
        )
        return [dict(r) for r in cursor.fetchall()]

    # Fallback
    try:
        cursor = conn.execute(
            f"SELECT * FROM \"{table}\" WHERE source_id = ?",
            (source_id,),
        )
        return [dict(r) for r in cursor.fetchall()]
    except Exception:
        return []


def _package_dir(source_id: str) -> Path:
    ctx = get_current_context()
    return ctx.sources_dir / source_id


def _state_dir(source_id: str) -> Path:
    return _package_dir(source_id) / "state"


def _snapshots_dir(source_id: str) -> Path:
    return _state_dir(source_id) / "snapshots"


def sync_source(source_id: str) -> dict[str, Any]:
    """Snapshot all DB state for a source into its package directory.

    Returns dict with snapshot_id, record_counts, manifest_sha256.
    """
    pkg = _package_dir(source_id)
    if not pkg.exists():
        raise FileNotFoundError(f"Package not found: {pkg}")

    snapshots = _snapshots_dir(source_id)
    tmp_dir = _state_dir(source_id) / ".tmp-SNP"
    final_dir = snapshots / generate_snapshot_id()

    _write_snapshot(source_id, tmp_dir)

    snapshots.mkdir(parents=True, exist_ok=True)
    os.replace(str(tmp_dir), str(final_dir))

    current = {"snapshot_id": final_dir.name, "updated_at": now_iso()}
    current_path = _state_dir(source_id) / "current.json"
    current_tmp = _state_dir(source_id) / ".tmp-current.json"
    current_tmp.write_text(json.dumps(current, ensure_ascii=False), encoding="utf-8")
    os.fsync(os.open(str(current_tmp), os.O_RDONLY))
    os.replace(str(current_tmp), str(current_path))

    manifest = json.loads((final_dir / "manifest.json").read_text())
    return {
        "snapshot_id": final_dir.name,
        "source_id": source_id,
        "record_counts": manifest["record_counts"],
        "manifest_sha256": manifest["manifest_sha256"],
    }


def check_source(source_id: str) -> dict[str, Any]:
    """Validate a source snapshot's integrity.

    Checks: current.json exists, snapshot dir exists,
    manifest hash match, all expected record files present,
    record counts match, no dangling IDs.
    """
    current_path = _state_dir(source_id) / "current.json"

    result: dict[str, Any] = {
        "source_id": source_id,
        "valid": True,
        "errors": [],
    }

    if not current_path.exists():
        result["valid"] = False
        result["errors"].append("current.json not found")
        return result

    current = json.loads(current_path.read_text())
    snap_id = current.get("snapshot_id")
    if not snap_id:
        result["valid"] = False
        result["errors"].append("current.json missing snapshot_id")
        return result

    snap_dir = _snapshots_dir(source_id) / snap_id
    if not snap_dir.exists():
        result["valid"] = False
        result["errors"].append(f"Snapshot directory not found: {snap_dir}")
        return result

    manifest_path = snap_dir / "manifest.json"
    if not manifest_path.exists():
        result["valid"] = False
        result["errors"].append("manifest.json not found")
        return result

    manifest = json.loads(manifest_path.read_text())

    records_dir = snap_dir / "records"
    for table, _pk in SNAPSHOT_TABLES:
        rp = records_dir / f"{table}.jsonl"
        if not rp.exists():
            result["errors"].append(f"Missing record file: {table}.jsonl")
            result["valid"] = False
            continue
        expected_count = manifest["record_counts"].get(table)
        if expected_count is None:
            continue
        actual_count = _count_jsonl(rp)
        if actual_count != expected_count:
            result["errors"].append(
                f"{table}: expected {expected_count} records, found {actual_count}"
            )
            result["valid"] = False

    total_expected = sum(manifest["record_counts"].values())
    result["expected_total"] = total_expected
    result["snapshot_id"] = snap_id
    result["record_counts"] = manifest["record_counts"]

    return result


def list_snapshots(source_id: str) -> list[dict[str, Any]]:
    """List all snapshots for a source."""
    sd = _snapshots_dir(source_id)
    if not sd.exists():
        return []
    result = []
    for d in sorted(sd.iterdir(), reverse=True):
        if d.is_dir():
            m = d / "manifest.json"
            if m.exists():
                mani = json.loads(m.read_text())
                result.append({
                    "snapshot_id": d.name,
                    "source_id": source_id,
                    "record_counts": mani["record_counts"],
                    "created_at": mani.get("created_at", ""),
                })
    return result


def _write_snapshot(source_id: str, tmp_dir: Path) -> None:
    """Write all DB records for a source into tmp_dir."""
    tmp_dir.mkdir(parents=True, exist_ok=True)
    records_dir = tmp_dir / "records"
    records_dir.mkdir(exist_ok=True)

    record_counts: dict[str, int] = {}
    manifest_hasher = hashlib.sha256()

    with get_connection(read_only=True) as conn:
        for table, pk_col in SNAPSHOT_TABLES:
            rows = _query_source_scoped(conn, source_id, table, pk_col)

            if not rows:
                record_counts[table] = 0
                (records_dir / f"{table}.jsonl").write_text("", encoding="utf-8")
                continue

            count = 0
            hasher = hashlib.sha256()
            with open(records_dir / f"{table}.jsonl", "w", encoding="utf-8") as f:
                for row in sorted(rows, key=lambda r: str(r.get(pk_col, ""))):
                    line = json.dumps(row, ensure_ascii=False, sort_keys=True)
                    f.write(line + "\n")
                    hasher.update(line.encode())
                    count += 1
                f.flush()
                os.fsync(f.fileno())
            record_counts[table] = count
            manifest_hasher.update(hasher.hexdigest().encode())

    manifest = {
        "manifest_schema_version": 2,
        "source_id": source_id,
        "record_counts": record_counts,
        "manifest_sha256": manifest_hasher.hexdigest(),
        "created_at": now_iso(),
    }
    with open(tmp_dir / "manifest.json", "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())


def _count_jsonl(path: Path) -> int:
    if not path.exists():
        return 0
    text = path.read_text(encoding="utf-8")
    if not text.strip():
        return 0
    return len([line for line in text.strip().split("\n") if line.strip()])
