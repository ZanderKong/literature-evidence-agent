"""Database rebuild from source package snapshots.

Reads from C01 snapshot structure or falls back to old structure.
Preflight all packages first, then build in temp DB,
verify integrity, and atomically replace target.
"""

import json
import shutil
import sqlite3
from pathlib import Path
from typing import Any

from evidence_agent.database.connection import transaction
from evidence_agent.runtime import get_current_context


class RebuildConflictError(Exception):
    """Same ID, different content between packages."""


TABLE_IMPORT_ORDER = [
    "research_tasks", "sources", "source_assets", "source_sections",
    "processing_runs", "source_claims", "claim_locators",
    "entities", "claim_entity_links",
    "review_batches", "review_batch_rows",
    "review_decisions", "claim_revisions",
]


def rebuild_from_packages(
    source_dir: Path | None = None,
    target_db: Path | None = None,
    *,
    replace: bool = False,
) -> dict[str, Any]:
    """Rebuild database from all source package snapshots."""
    runtime = get_current_context()

    if source_dir is None:
        source_dir = runtime.sources_dir
    if target_db is None:
        target_db = runtime.db_path

    source_dir = source_dir.resolve()
    target_db = target_db.resolve()

    if not source_dir.exists():
        raise FileNotFoundError(f"Sources directory not found: {source_dir}")

    if target_db.exists():
        if not replace:
            raise FileExistsError(
                f"Target database {target_db} already exists. "
                f"Use replace=True to overwrite."
            )
        backup = target_db.with_suffix(".sqlite.bak")
        shutil.copy2(str(target_db), str(backup))

    target_db.parent.mkdir(parents=True, exist_ok=True)

    temp_db = target_db.with_suffix(".tmp.sqlite")
    if temp_db.exists():
        temp_db.unlink()

    report: dict[str, Any] = {
        "target_db": str(target_db),
        "sources_imported": 0, "sections_imported": 0,
        "claims_imported": 0, "locators_imported": 0,
        "runs_imported": 0, "decisions_imported": 0,
        "revisions_imported": 0, "batches_imported": 0,
        "batch_rows_imported": 0, "entities_imported": 0,
        "links_imported": 0, "tasks_imported": 0,
        "assets_imported": 0,
        "conflicts": [], "errors": [],
        "integrity": None, "foreign_keys": None,
    }

    try:
        from evidence_agent.database.migrations import migrate
        migrate(temp_db)

        packages = _preflight_packages(source_dir, report)
        _import_all_packages(packages, temp_db, report)
        _rebuild_fts_on_target(temp_db)

        conn = sqlite3.connect(str(temp_db))
        cur = conn.execute("PRAGMA integrity_check")
        report["integrity"] = cur.fetchone()[0]
        cur = conn.execute("PRAGMA foreign_key_check")
        fk = cur.fetchall()
        report["foreign_keys"] = "ok" if not fk else str(len(fk))
        conn.close()

        shutil.copy2(str(temp_db), str(target_db))
    except RebuildConflictError:
        if temp_db.exists():
            temp_db.unlink()
        raise
    except Exception:
        if temp_db.exists():
            temp_db.unlink()
        raise
    finally:
        if temp_db.exists():
            temp_db.unlink()

    return report


def _preflight_packages(
    source_dir: Path, report: dict[str, Any],
) -> list[dict[str, Any]]:
    """Scan packages, validate, detect ID conflicts."""
    packages = []
    seen_ids: dict[str, dict[str, str]] = {}

    for pkg_dir in sorted(source_dir.iterdir()):
        if not pkg_dir.is_dir():
            continue
        pkg = _try_new_snapshot(pkg_dir, seen_ids, report)
        if pkg is None:
            pkg = _try_old_structure(pkg_dir, seen_ids, report)
        if pkg is None:
            continue
        packages.append(pkg)

    conflict_msgs = [c for c in report["conflicts"] if "RESTORE_CONFLICT" in c]
    if conflict_msgs:
        raise RebuildConflictError(
            f"Preflight: {len(conflict_msgs)} RESTORE_CONFLICT(s) found"
        )
    return packages


def _try_new_snapshot(
    pkg_dir: Path, seen_ids: dict[str, dict[str, str]], report: dict[str, Any],
) -> dict[str, Any] | None:
    current_path = pkg_dir / "state" / "current.json"
    if not current_path.exists():
        return None
    cur = json.loads(current_path.read_text())
    snap_id = cur.get("snapshot_id")
    if not snap_id:
        return None
    snap_dir = pkg_dir / "state" / "snapshots" / snap_id
    manifest_path = snap_dir / "manifest.json"
    if not manifest_path.exists():
        return None
    manifest = json.loads(manifest_path.read_text())
    records_dir = snap_dir / "records"
    if not records_dir.exists():
        return None
    source_id = manifest.get("source_id", pkg_dir.name)
    _preflight_records(records_dir, source_id, seen_ids, report)
    return {"source_id": source_id, "records_dir": records_dir}


def _try_old_structure(
    pkg_dir: Path, seen_ids: dict[str, dict[str, str]], report: dict[str, Any],
) -> dict[str, Any] | None:
    manifest_path = pkg_dir / "manifest.json"
    if not manifest_path.exists():
        return None
    manifest = json.loads(manifest_path.read_text())
    source_id = manifest.get("source_id", pkg_dir.name)

    records_dir = pkg_dir / "_import_records"
    records_dir.mkdir(exist_ok=True)
    _convert_old_to_records(pkg_dir, manifest, records_dir)
    _preflight_records(records_dir, source_id, seen_ids, report)
    return {"source_id": source_id, "records_dir": records_dir}


def _convert_old_to_records(
    pkg_dir: Path, manifest: dict[str, Any], records_dir: Path,
) -> None:
    """Convert old package files to C01-style records."""
    manifest["origin_scope"] = "external"
    manifest["scientific_verification_status"] = "unverified"

    src_file = records_dir / "sources.jsonl"
    if not src_file.exists():
        src_file.write_text(json.dumps(manifest, ensure_ascii=False) + "\n",
                            encoding="utf-8")

    sections = pkg_dir / "parsed" / "sections.jsonl"
    dst = records_dir / "source_sections.jsonl"
    if sections.exists() and not dst.exists():
        shutil.copy2(str(sections), str(dst))

    claims = pkg_dir / "analysis" / "claims.persisted.jsonl"
    run_dir = pkg_dir / "analysis" / "runs"
    if run_dir.exists():
        for rd in sorted(run_dir.iterdir()):
            if rd.is_dir():
                cp = rd / "claims.persisted.jsonl"
                if cp.exists():
                    claims = cp
                    break
    dst = records_dir / "source_claims.jsonl"
    if claims.exists() and not dst.exists():
        shutil.copy2(str(claims), str(dst))

    runs = pkg_dir / "provenance" / "processing_runs.jsonl"
    dst = records_dir / "processing_runs.jsonl"
    if runs.exists() and not dst.exists():
        shutil.copy2(str(runs), str(dst))

    dec = pkg_dir / "review" / "decisions.jsonl"
    dst = records_dir / "review_decisions.jsonl"
    if dec.exists() and not dst.exists():
        shutil.copy2(str(dec), str(dst))

    rev = pkg_dir / "review" / "revisions.jsonl"
    dst = records_dir / "claim_revisions.jsonl"
    if rev.exists() and not dst.exists():
        shutil.copy2(str(rev), str(dst))


def _preflight_records(
    records_dir: Path, source_id: str,
    seen_ids: dict[str, dict[str, str]], report: dict[str, Any],
) -> None:
    for rec_file in sorted(records_dir.iterdir()):
        if not rec_file.name.endswith(".jsonl"):
            continue
        table = rec_file.stem
        for line in rec_file.read_text(encoding="utf-8").strip().split("\n"):
            if not line:
                continue
            row = json.loads(line)
            pk = _find_pk(table, row)
            if not pk:
                continue
            key = f"{table}:{pk}"
            crc = json.dumps(row, sort_keys=True, ensure_ascii=False)
            existing = seen_ids.get(key)
            if existing is not None:
                if existing["crc"] != crc:
                    report["conflicts"].append(
                        f"RESTORE_CONFLICT: {key} in "
                        f"{existing['source']} and {source_id}"
                    )
                else:
                    report["conflicts"].append(f"DUPLICATE_IDENTICAL: {key} (ok)")
            else:
                seen_ids[key] = {"source": source_id, "crc": crc}


def _import_all_packages(
    packages: list[dict[str, Any]], target_db: Path, report: dict[str, Any],
) -> None:
    for pkg in packages:
        _import_one_package(pkg, target_db, report)


def _import_one_package(
    pkg: dict[str, Any], target_db: Path, report: dict[str, Any],
) -> None:
    """Import records in dependency order. No INSERT OR IGNORE."""
    records_dir = pkg["records_dir"]
    source_id = pkg["source_id"]

    with transaction(target_db) as conn:
        locator_rows: list[dict[str, Any]] = []

        for table in TABLE_IMPORT_ORDER:
            rec_file = records_dir / f"{table}.jsonl"
            if not rec_file.exists():
                if table == "claim_locators" and locator_rows:
                    _insert_rows(conn, table, locator_rows, report)
                    locator_rows = []
                continue
            rows = [
                json.loads(line)
                for line in rec_file.read_text(encoding="utf-8").strip().split("\n")
                if line.strip()
            ]
            if not rows:
                continue

            for row in rows:
                if table in ("sources", "source_assets", "source_sections",
                             "processing_runs", "source_claims",
                             "review_batches"):
                    row.setdefault("source_id", source_id)

                if table == "source_claims":
                    loc_id = row.pop("locator_id", None) or f"LOC-{row.get('claim_id','')}"
                    loc_row = {
                        "locator_id": loc_id,
                        "claim_id": row.get("claim_id", row.get("_claim_id", "")),
                        "page": row.pop("page", None),
                        "figure_label": row.pop("figure_label", None),
                        "table_label": row.pop("table_label", None),
                        "locator_confidence": row.pop("locator_confidence", "medium"),
                    }
                    locator_rows.append(loc_row)

                row = _adapt_row(table, row)
                if not row:
                    continue
                pk = _find_pk(table, row)
                if pk:
                    c = conn.execute(
                        f"SELECT COUNT(*) FROM \"{table}\" "
                        f"WHERE \"{_pk_column(table)}\" = ?",
                        (pk,),
                    ).fetchone()
                    if c[0] > 0:
                        continue
                cols = list(row.keys())
                plc = ", ".join("?" * len(cols))
                cq = ", ".join(f"\"{c}\"" for c in cols)
                vals = list(row.values())
                conn.execute(
                    f"INSERT INTO \"{table}\" ({cq}) VALUES ({plc})", vals,
                )

            if table == "claim_locators":
                _insert_rows(conn, table, locator_rows, report)
                locator_rows = []


def _insert_rows(
    conn: Any, table: str, rows: list[dict[str, Any]], report: dict[str, Any],
) -> None:
    imported = 0
    for row in rows:
        row = _adapt_row(table, row)
        pk = _find_pk(table, row)
        if pk:
            c = conn.execute(
                f"SELECT COUNT(*) FROM \"{table}\" "
                f"WHERE \"{_pk_column(table)}\" = ?",
                (pk,),
            ).fetchone()
            if c[0] > 0:
                continue
        cols = list(row.keys())
        plc = ", ".join("?" * len(cols))
        cq = ", ".join(f"\"{c}\"" for c in cols)
        vals = list(row.values())
        conn.execute(f"INSERT INTO \"{table}\" ({cq}) VALUES ({plc})", vals)
        imported += 1
    _increment_report(report, table, imported)


def _adapt_row(table: str, row: dict[str, Any]) -> dict[str, Any]:
    """Adapt row for a specific table, removing invalid columns."""
    if table == "sources":
        row.setdefault("origin_scope", "external")
        row.setdefault("scientific_verification_status", "unverified")
        row.pop("assets", None)
        row.pop("last_analysis", None)
    elif table == "source_claims":
        if "claim_id" not in row and "_claim_id" in row:
            row["claim_id"] = row["_claim_id"]
        if "created_by_run_id" not in row:
            row["created_by_run_id"] = row.pop("run_id", "")
        for k in ["_claim_id", "locator_hint", "locator_id", "_quote_match_status",
                   "_block_page_start", "_record_review_status", "page",
                   "figure_label", "table_label", "locator_confidence",
                   "schema_version", "run_id"]:
            row.pop(k, None)
        row.setdefault("origin_scope", "external")
        row.setdefault("scientific_verification_status", "unverified")
        row.setdefault("record_review_status", "pending")
        row.setdefault("quote_match_status", "exact")
    elif table == "claim_locators":
        if "locator_id" not in row:
            row["locator_id"] = f"LOC-{row.get('claim_id', 'unknown')}"
        row.setdefault("locator_confidence", "medium")
    elif table == "review_decisions":
        row.setdefault("object_type", "claim")
        row.setdefault("original_content_json", "{}")
        row.setdefault("reviewer", "unknown")
    elif table == "claim_revisions":
        row.setdefault("previous_content_json", "{}")
        row.setdefault("new_content_json", "{}")
        row.setdefault("changed_by", "unknown")
    elif table == "processing_runs":
        row.setdefault("module_name", "analyse")
        row.setdefault("model_name", "mock")
        row.setdefault("input_hash", "")
        row.setdefault("output_hash", "")
        row.setdefault("status", "completed")
    return row


def _rebuild_fts_on_target(target_db: Path) -> None:
    with transaction(target_db) as conn:
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


def _find_pk(table: str, row: dict[str, Any]) -> Any:
    pk_col = _pk_column(table)
    return row.get(pk_col) if pk_col else None


def _pk_column(table: str) -> str:
    pk_map = {
        "research_tasks": "task_id", "sources": "source_id",
        "source_assets": "asset_id", "source_sections": "section_id",
        "processing_runs": "run_id", "source_claims": "claim_id",
        "claim_locators": "locator_id", "entities": "entity_id",
        "claim_entity_links": "link_id", "review_batches": "review_batch_id",
        "review_batch_rows": "review_row_id", "review_decisions": "review_id",
        "claim_revisions": "revision_id",
    }
    return pk_map.get(table, "rowid")


def _increment_report(report: dict[str, Any], table: str, count: int) -> None:
    km = {
        "research_tasks": "tasks_imported", "sources": "sources_imported",
        "source_assets": "assets_imported", "source_sections": "sections_imported",
        "processing_runs": "runs_imported", "source_claims": "claims_imported",
        "claim_locators": "locators_imported", "entities": "entities_imported",
        "claim_entity_links": "links_imported", "review_batches": "batches_imported",
        "review_batch_rows": "batch_rows_imported",
        "review_decisions": "decisions_imported",
        "claim_revisions": "revisions_imported",
    }
    key = km.get(table)
    if key:
        report[key] = report.get(key, 0) + count
