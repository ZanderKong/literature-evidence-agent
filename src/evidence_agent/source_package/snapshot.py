"""Package snapshot — persist complete immutable source state.

Writes all DB data for a source to JSONL records under:
    SRC-ID/state/snapshots/SNP-ID/records/*.jsonl

Manifest v3: per-artifact path, sha256, record_type, record_count.
Integrity checks: file SHA-256, manifest hash, cross-reference validation.
Atomic: writes to .tmp-SNP-<uuid> → fsync → rename, then updates current.json.
"""

import hashlib
import json
import os
import uuid
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


def _package_dir(source_id: str) -> Path:
    ctx = get_current_context()
    return ctx.sources_dir / source_id


def _state_dir(source_id: str) -> Path:
    return _package_dir(source_id) / "state"


def _snapshots_dir(source_id: str) -> Path:
    return _state_dir(source_id) / "snapshots"


def _compute_file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _count_jsonl(path: Path) -> int:
    if not path.exists():
        return 0
    text = path.read_text(encoding="utf-8")
    if not text.strip():
        return 0
    return sum(1 for line in text.strip().split("\n") if line.strip())


# ── Snapshot write ────────────────────────────────────


def sync_source(source_id: str) -> dict[str, Any]:
    """Snapshot all DB state for a source into its package directory."""
    pkg = _package_dir(source_id)
    if not pkg.exists():
        raise FileNotFoundError(f"Package not found: {pkg}")

    snapshots = _snapshots_dir(source_id)
    tmp_dir = _state_dir(source_id) / f".tmp-SNP-{uuid.uuid4().hex[:12]}"
    final_dir = snapshots / generate_snapshot_id()

    try:
        _write_snapshot(source_id, tmp_dir)
        snapshots.mkdir(parents=True, exist_ok=True)
        os.replace(str(tmp_dir), str(final_dir))
    except Exception:
        if tmp_dir.exists():
            import shutil
            shutil.rmtree(str(tmp_dir), ignore_errors=True)
        raise

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
        "artifact_count": len(manifest["artifacts"]),
        "record_counts": manifest["record_counts"],
        "manifest_sha256": manifest["manifest_sha256"],
    }


def _write_snapshot(source_id: str, tmp_dir: Path) -> None:
    tmp_dir.mkdir(parents=True, exist_ok=True)
    records_dir = tmp_dir / "records"
    records_dir.mkdir(exist_ok=True)

    record_counts: dict[str, int] = {}
    artifacts: list[dict[str, Any]] = []
    manifest_hasher = hashlib.sha256()

    with get_connection(read_only=True) as conn:
        for table, pk_col in SNAPSHOT_TABLES:
            rows = _query_source_scoped(conn, source_id, table, pk_col)
            path = records_dir / f"{table}.jsonl"

            if not rows:
                path.write_text("", encoding="utf-8")
                sha = _compute_file_sha256(path)
                artifacts.append({
                    "path": f"records/{table}.jsonl",
                    "sha256": sha,
                    "record_type": table,
                    "record_count": 0,
                })
                record_counts[table] = 0
                manifest_hasher.update(sha.encode())
                continue

            sorted_rows = sorted(rows, key=lambda r: str(r.get(pk_col, "")))
            with open(path, "w", encoding="utf-8") as f:
                for row in sorted_rows:
                    line = json.dumps(row, ensure_ascii=False, sort_keys=True)
                    f.write(line + "\n")
                f.flush()
                os.fsync(f.fileno())

            sha = _compute_file_sha256(path)
            count = len(sorted_rows)
            artifacts.append({
                "path": f"records/{table}.jsonl",
                "sha256": sha,
                "record_type": table,
                "record_count": count,
            })
            record_counts[table] = count
            manifest_hasher.update(sha.encode())

    manifest_sha256 = manifest_hasher.hexdigest()
    manifest = {
        "manifest_schema_version": 3,
        "source_id": source_id,
        "record_counts": record_counts,
        "artifacts": artifacts,
        "manifest_sha256": manifest_sha256,
        "created_at": now_iso(),
    }
    mp = tmp_dir / "manifest.json"
    mp.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    os.fsync(os.open(str(mp), os.O_RDONLY))


# ── Snapshot integrity check ──────────────────────────


def check_source(source_id: str) -> dict[str, Any]:
    """Validate a snapshot: file SHA-256, counts, cross-references."""
    result: dict[str, Any] = {
        "source_id": source_id,
        "valid": True,
        "errors": [],
    }

    current_path = _state_dir(source_id) / "current.json"
    if not current_path.exists():
        result["valid"] = False
        result["errors"].append("current.json not found")
        return result

    current = json.loads(current_path.read_text())
    snap_id = current.get("snapshot_id")
    if not snap_id:
        result["valid"] = False
        result["errors"].append("current.json missing snapshot_id")
        result["snapshot_id"] = None
        return result

    result["snapshot_id"] = snap_id

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

    if manifest.get("source_id") != source_id:
        result["errors"].append(
            f"source_id mismatch: manifest={manifest.get('source_id')}, expected={source_id}"
        )
        result["valid"] = False

    expected_sha = manifest.get("manifest_sha256", "")
    actual_sha = _compute_manifest_hash(snap_dir, manifest.get("artifacts", []))
    if actual_sha != expected_sha:
        result["errors"].append(
            f"manifest_sha256 mismatch: expected={expected_sha[:16]}, actual={actual_sha[:16]}"
        )
        result["valid"] = False

    records_dir = snap_dir / "records"
    for table, _pk in SNAPSHOT_TABLES:
        rp = records_dir / f"{table}.jsonl"
        if not rp.exists():
            result["errors"].append(f"Missing: {table}.jsonl")
            result["valid"] = False
            continue

        artifact = _find_artifact(manifest.get("artifacts", []), table)
        if artifact is None:
            result["errors"].append(f"No artifact entry for {table}")
            result["valid"] = False
            continue

        actual_count = _count_jsonl(rp)
        expected_count = artifact.get("record_count", -1)
        if actual_count != expected_count:
            result["errors"].append(
                f"{table}: count mismatch expected={expected_count} actual={actual_count}"
            )
            result["valid"] = False

        actual_file_sha = _compute_file_sha256(rp)
        expected_file_sha = artifact.get("sha256", "")
        if actual_file_sha != expected_file_sha:
            result["errors"].append(
                f"{table}: file_sha256 mismatch "
                f"expected={expected_file_sha[:16]} actual={actual_file_sha[:16]}"
            )
            result["valid"] = False

    artifact_total = sum(a.get("record_count", 0) for a in manifest.get("artifacts", []))
    result["expected_total"] = artifact_total
    result["record_counts"] = manifest.get("record_counts", {})

    if result["valid"]:
        xref_errors = _validate_cross_references(records_dir, source_id)
        if xref_errors:
            result["errors"].extend(xref_errors)
            result["valid"] = False

    return result


def _compute_manifest_hash(snap_dir: Path, artifacts: list[dict[str, Any]]) -> str:
    h = hashlib.sha256()
    for a in artifacts:
        sha = a.get("sha256", "")
        if sha:
            h.update(sha.encode())
    return h.hexdigest()


def _find_artifact(artifacts: list[dict[str, Any]], table: str) -> dict[str, Any] | None:
    for a in artifacts:
        if a.get("record_type") == table:
            return a
    return None


def _validate_cross_references(records_dir: Path, source_id: str) -> list[str]:
    """Validate cross-table references in a snapshot."""
    errors: list[str] = []

    claims = _load_jsonl(records_dir / "source_claims.jsonl")
    sources = _load_jsonl(records_dir / "sources.jsonl")
    locators = _load_jsonl(records_dir / "claim_locators.jsonl")
    tasks = _load_jsonl(records_dir / "research_tasks.jsonl")
    runs = _load_jsonl(records_dir / "processing_runs.jsonl")
    entity_links = _load_jsonl(records_dir / "claim_entity_links.jsonl")
    entities = _load_jsonl(records_dir / "entities.jsonl")
    batch_rows = _load_jsonl(records_dir / "review_batch_rows.jsonl")
    batches = _load_jsonl(records_dir / "review_batches.jsonl")
    decisions = _load_jsonl(records_dir / "review_decisions.jsonl")
    revisions = _load_jsonl(records_dir / "claim_revisions.jsonl")

    source_ids = {s["source_id"] for s in sources}
    claim_ids = {c["claim_id"] for c in claims}
    task_ids = {t["task_id"] for t in tasks}
    run_ids = {r["run_id"] for r in runs}
    entity_ids = {e["entity_id"] for e in entities}
    batch_ids = {b["review_batch_id"] for b in batches}
    row_by_id = {br["review_row_id"]: br for br in batch_rows}

    for c in claims:
        if c.get("source_id") not in source_ids:
            errors.append(f"claim {c['claim_id']}: source_id not in sources")
        created_by = c.get("created_by_run_id") or c.get("run_id")
        if created_by and created_by not in run_ids:
            errors.append(f"claim {c['claim_id']}: created_by_run_id not in runs")

    for loc in locators:
        if loc.get("claim_id") not in claim_ids:
            errors.append(f"locator {loc['locator_id']}: claim_id not in claims")

    for r in runs:
        if r.get("source_id") not in source_ids:
            errors.append(f"run {r['run_id']}: source_id not in sources")
        if r.get("task_id") and r["task_id"] not in task_ids:
            errors.append(f"run {r['run_id']}: task_id {r['task_id']} not in tasks")

    for el in entity_links:
        if el.get("claim_id") not in claim_ids:
            errors.append(f"link {el.get('link_id','')}: claim_id not in claims")
        if el.get("entity_id") not in entity_ids:
            errors.append(f"link {el.get('link_id','')}: entity_id not in entities")

    for b in batches:
        if b.get("run_id") and b["run_id"] not in run_ids:
            errors.append(f"batch {b['review_batch_id']}: run_id {b['run_id']} not in runs")
        if b.get("source_id") != source_id:
            errors.append(
                f"batch {b['review_batch_id']}: source_id mismatch: "
                f"{b.get('source_id')} != {source_id}"
            )

    for br in batch_rows:
        if br.get("review_batch_id") not in batch_ids:
            errors.append(f"batch_row {br['review_row_id']}: batch_id not in batches")
        if br.get("claim_id") not in claim_ids:
            errors.append(f"batch_row {br['review_row_id']}: claim_id not in claims")

    for d in decisions:
        if d.get("review_batch_id") and d["review_batch_id"] not in batch_ids:
            errors.append(f"decision {d['review_id']}: batch_id not in batches")
        if d.get("object_id") and d["object_id"] not in claim_ids:
            errors.append(f"decision {d['review_id']}: object_id not in claims")
        row_id = d.get("review_row_id")
        if row_id:
            if row_id not in row_by_id:
                errors.append(
                    f"decision {d['review_id']}: review_row_id {row_id} not in rows"
                )
            else:
                br = row_by_id[row_id]
                bid = d.get("review_batch_id")
                if bid and br.get("review_batch_id") != bid:
                    errors.append(
                        f"decision {d['review_id']}: row belongs to batch "
                        f"{br.get('review_batch_id')}, not {bid}"
                    )
                obj = d.get("object_id")
                if obj and br.get("claim_id") != obj:
                    errors.append(
                        f"decision {d['review_id']}: row.claim_id "
                        f"{br.get('claim_id')} != object_id {obj}"
                    )

    for v in revisions:
        if v.get("claim_id") not in claim_ids:
            errors.append(f"revision {v['revision_id']}: claim_id not in claims")

    return errors


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").strip().split("\n"):
        if line.strip():
            rows.append(json.loads(line))
    return rows


# ── Snapshot listing ──────────────────────────────────


def list_snapshots(source_id: str) -> list[dict[str, Any]]:
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
                    "record_counts": mani.get("record_counts", {}),
                    "artifact_count": len(mani.get("artifacts", [])),
                    "created_at": mani.get("created_at", ""),
                })
    return result


# ── DB query helpers (unchanged) ──────────────────────


def _query_source_scoped(
    conn: Any, source_id: str, table: str, pk_col: str,
) -> list[dict[str, Any]]:
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

    if table in ("sources", "source_assets", "source_sections", "source_claims"):
        cursor = conn.execute(
            f"SELECT * FROM \"{table}\" WHERE source_id = ?", (source_id,),
        )
        return [dict(r) for r in cursor.fetchall()]

    if table == "processing_runs":
        cursor = conn.execute(
            "SELECT * FROM processing_runs WHERE source_id = ?", (source_id,),
        )
        return [dict(r) for r in cursor.fetchall()]

    if table == "claim_locators":
        cursor = conn.execute(
            "SELECT l.* FROM claim_locators l "
            "JOIN source_claims c ON l.claim_id = c.claim_id "
            "WHERE c.source_id = ?", (source_id,),
        )
        return [dict(r) for r in cursor.fetchall()]

    if table == "review_batches":
        cursor = conn.execute(
            "SELECT b.* FROM review_batches b "
            "JOIN processing_runs r ON b.run_id = r.run_id "
            "WHERE r.source_id = ?", (source_id,),
        )
        return [dict(r) for r in cursor.fetchall()]

    if table == "review_batch_rows":
        cursor = conn.execute(
            "SELECT br.* FROM review_batch_rows br "
            "JOIN review_batches b ON br.review_batch_id = b.review_batch_id "
            "JOIN processing_runs r ON b.run_id = r.run_id "
            "WHERE r.source_id = ?", (source_id,),
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
            "WHERE c.source_id = ?", (source_id,),
        )
        return [dict(r) for r in cursor.fetchall()]

    if table in ("entities", "claim_entity_links"):
        cursor = conn.execute(
            "SELECT e.* FROM entities e "
            "JOIN claim_entity_links l ON e.entity_id = l.entity_id "
            "JOIN source_claims c ON l.claim_id = c.claim_id "
            "WHERE c.source_id = ?", (source_id,),
        ) if table == "entities" else conn.execute(
            "SELECT l.* FROM claim_entity_links l "
            "JOIN source_claims c ON l.claim_id = c.claim_id "
            "WHERE c.source_id = ?", (source_id,),
        )
        return [dict(r) for r in cursor.fetchall()]

    try:
        cursor = conn.execute(
            f"SELECT * FROM \"{table}\" WHERE source_id = ?", (source_id,),
        )
        return [dict(r) for r in cursor.fetchall()]
    except Exception:
        return []
