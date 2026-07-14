"""Review packet generation — reads from database by run_id.

Creates review_batches and review_batch_rows in the database
for tracking and idempotency. Same run + same packet hash
reuses existing batch/row IDs.
"""

import csv
import hashlib
import json
from pathlib import Path
from typing import Any

from evidence_agent.database.connection import get_connection
from evidence_agent.ids import generate_batch_id, generate_row_id, now_iso
from evidence_agent.runtime import get_current_context

CANONICAL_ROW_KEYS = [
    "claim_id", "claim_type", "source_quote", "faithful_paraphrase",
    "evidence_basis_description", "page", "figure_label", "table_label",
]


def hash_review_row(row: dict[str, Any]) -> str:
    """SHA-256 of canonical JSON for a single review row."""
    payload = {k: (row.get(k) or "") for k in CANONICAL_ROW_KEYS}
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True,
                     separators=(",", ":"))
    return hashlib.sha256(raw.encode()).hexdigest()


def hash_review_packet(row_hashes: list[str]) -> str:
    """SHA-256 of sorted, concatenated row hashes."""
    digest = hashlib.sha256()
    for rh in row_hashes:
        digest.update(rh.encode())
    return digest.hexdigest()


def _lookup_existing_batch(run_id: str, packet_sha256: str) -> dict[str, Any] | None:
    """Return existing batch dict if same (run_id, packet_sha256) exists."""
    with get_connection(read_only=True) as conn:
        row = conn.execute(
            "SELECT review_batch_id, packet_sha256 FROM review_batches "
            "WHERE run_id = ? AND packet_sha256 = ?",
            (run_id, packet_sha256),
        ).fetchone()
        if row is None:
            return None
        batch_id = row["review_batch_id"]
        rows = conn.execute(
            "SELECT review_row_id, claim_id, row_sequence, row_input_sha256 "
            "FROM review_batch_rows WHERE review_batch_id = ? "
            "ORDER BY row_sequence",
            (batch_id,),
        ).fetchall()
        return {
            "review_batch_id": batch_id,
            "packet_sha256": packet_sha256,
            "rows": [dict(r) for r in rows],
        }


def _insert_batch(
    run_id: str, source_id: str, packet_sha256: str,
    canonical_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    """Insert new batch and rows. Returns batch dict."""
    batch_id = generate_batch_id()
    row_records: list[dict[str, Any]] = []
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO review_batches (review_batch_id, run_id, source_id, "
            "packet_sha256, status, exported_at) VALUES (?, ?, ?, ?, 'exported', ?)",
            (batch_id, run_id, source_id, packet_sha256, now_iso()),
        )
        for row_rec in canonical_rows:
            row_id = generate_row_id()
            conn.execute(
                "INSERT INTO review_batch_rows (review_row_id, review_batch_id, "
                "claim_id, row_sequence, row_input_sha256) VALUES (?, ?, ?, ?, ?)",
                (row_id, batch_id, row_rec["claim_id"],
                 row_rec["row_sequence"], row_rec["row_input_sha256"]),
            )
            row_records.append({
                "review_row_id": row_id,
                "claim_id": row_rec["claim_id"],
                "row_sequence": row_rec["row_sequence"],
                "row_input_sha256": row_rec["row_input_sha256"],
            })
    return {
        "review_batch_id": batch_id,
        "packet_sha256": packet_sha256,
        "rows": row_records,
    }


def generate_review_packet(
    run_id: str, output_dir: Path | None = None
) -> dict[str, str]:
    """Generate review packet from database claims for a processing run.

    Idempotent: same run + same claims content reuses existing batch/row IDs.
    """
    runtime = get_current_context()

    if output_dir is None:
        output_dir = runtime.review_dir / run_id
    output_dir.mkdir(parents=True, exist_ok=True)

    with get_connection(read_only=True) as conn:
        cursor = conn.execute(
            "SELECT c.*, l.page, l.figure_label, l.table_label, "
            "l.locator_confidence, s.title as source_title "
            "FROM source_claims c "
            "LEFT JOIN claim_locators l ON c.claim_id = l.claim_id "
            "LEFT JOIN sources s ON c.source_id = s.source_id "
            "WHERE c.created_by_run_id = ? "
            "AND c.record_review_status = 'pending' "
            "ORDER BY COALESCE(l.page, 2147483647), c.claim_type, c.claim_id",
            (run_id,),
        )
        claims = [dict(row) for row in cursor.fetchall()]

    if not claims:
        raise ValueError(
            f"NO_PENDING_CLAIMS: No pending claims for run {run_id}"
        )

    row_hashes: list[str] = []
    canonical_rows: list[dict[str, Any]] = []
    for seq, c in enumerate(claims, 1):
        rh = hash_review_row(c)
        row_hashes.append(rh)
        canonical_rows.append({
            "claim_id": c["claim_id"],
            "row_sequence": seq,
            "row_input_sha256": rh,
        })

    packet_sha256 = hash_review_packet(row_hashes)

    existing = _lookup_existing_batch(run_id, packet_sha256)
    if existing is not None:
        batch = existing
    else:
        batch = _insert_batch(
            run_id, claims[0]["source_id"], packet_sha256, canonical_rows,
        )

    source_title = (claims[0].get("source_title") or "Untitled")
    claim_ids_to_row_info: dict[str, dict[str, str]] = {}
    for r in batch["rows"]:
        claim_ids_to_row_info[r["claim_id"]] = {
            "review_batch_id": batch["review_batch_id"],
            "review_row_id": r["review_row_id"],
            "row_input_sha256": r["row_input_sha256"],
            "packet_sha256": batch["packet_sha256"],
            "run_id": run_id,
        }

    paths: dict[str, str] = {}
    paths["batch_id"] = batch["review_batch_id"]
    paths["packet_sha256"] = batch["packet_sha256"]
    paths["row_count"] = str(len(canonical_rows))

    csv_path = output_dir / "claims_for_review.csv"
    _write_csv(claims, claim_ids_to_row_info, csv_path)
    paths["csv"] = str(csv_path)

    jsonl_path = output_dir / "claims_for_review.jsonl"
    with open(jsonl_path, "w", encoding="utf-8") as f:
        for c in claims:
            cid = c["claim_id"]
            info = claim_ids_to_row_info.get(cid, {})
            merged = {**c, **{k: v for k, v in info.items() if v}}
            f.write(json.dumps(merged, ensure_ascii=False) + "\n")
    paths["jsonl"] = str(jsonl_path)

    md_path = output_dir / "review_packet.md"
    _write_md(claims, claim_ids_to_row_info, source_title, md_path)
    paths["markdown"] = str(md_path)

    html_path = output_dir / "review_packet.html"
    _write_html(claims, claim_ids_to_row_info, source_title, html_path)
    paths["html"] = str(html_path)

    inst_path = output_dir / "review_instructions.md"
    inst_path.write_text(
        "# Review Instructions\n\n"
        "1. Open `claims_for_review.csv`.\n"
        "2. For each claim, set decision: approve, approve_with_edits, "
        "reject, mark_missing, needs_followup.\n"
        "3. If approve_with_edits, fill edited_* columns.\n"
        "4. Run: `evidence-agent review apply <path>`\n\n"
        "⚠️ 'Approved' means the record faithfully reflects the source. "
        "It does NOT mean the claim has been verified internally.\n",
        encoding="utf-8",
    )
    paths["instructions"] = str(inst_path)

    return paths


def _write_csv(
    claims: list[dict[str, Any]],
    batch_info: dict[str, dict[str, str]],
    path: Path,
) -> None:
    fields = [
        "review_batch_id", "review_row_id", "row_input_sha256",
        "packet_sha256", "run_id",
        "claim_id", "source_id", "claim_type", "source_quote",
        "faithful_paraphrase", "evidence_basis_description",
        "page", "section", "figure_label", "table_label",
        "quote_match_status", "locator_confidence",
        "decision", "edited_source_quote", "edited_faithful_paraphrase",
        "edited_evidence_basis_description", "edited_claim_type",
        "edited_page", "edited_section",
        "review_reason", "reviewer",
    ]
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for c in claims:
            cid = c.get("claim_id", "")
            hi = batch_info.get(cid, {})
            row = {k: c.get(k, "") for k in fields}
            for k, v in hi.items():
                row[k] = v
            w.writerow(row)


def _write_md(
    claims: list[dict[str, Any]],
    batch_info: dict[str, dict[str, str]],
    title: str,
    path: Path,
) -> None:
    lines = [f"# Review — {title}\n", f"**Claims:** {len(claims)}\n", "---\n"]
    for i, c in enumerate(claims, 1):
        cid = c.get("claim_id", f"CLM-{i}")
        hi = batch_info.get(cid, {})
        lines.append(f"## {i}. {cid}\n")
        lines.append(f"- **Batch:** {hi.get('review_batch_id','N/A')}")
        lines.append(f"- **Row:** {hi.get('review_row_id','N/A')}")
        lines.append(f"- **Type:** {c.get('claim_type', 'N/A')}")
        lines.append(f"- **Page:** {c.get('page', 'N/A')}")
        lines.append(f"- **Match:** {c.get('quote_match_status', 'N/A')}\n")
        lines.append(f"> {c.get('source_quote', 'N/A')}\n")
        lines.append(f"**Paraphrase:** {c.get('faithful_paraphrase', '')}\n")
        lines.append("---\n")
    path.write_text("\n".join(lines), encoding="utf-8")


def _write_html(
    claims: list[dict[str, Any]],
    batch_info: dict[str, dict[str, str]],
    title: str,
    path: Path,
) -> None:
    import html as html_mod
    items = []
    for i, c in enumerate(claims, 1):
        cid = html_mod.escape(c.get("claim_id", f"CLM-{i}"))
        hi = batch_info.get(c.get("claim_id", ""), {})
        quote = html_mod.escape(c.get("source_quote", ""))
        para = html_mod.escape(c.get("faithful_paraphrase", ""))
        items.append(
            f"<div class='claim'><h3>{i}. {cid}</h3>"
            f"<p><b>Batch:</b> {html_mod.escape(hi.get('review_batch_id',''))}"
            f" | <b>Row:</b> {html_mod.escape(hi.get('review_row_id',''))}"
            f" | <b>Type:</b> {html_mod.escape(c.get('claim_type',''))}"
            f" | <b>Page:</b> {c.get('page','N/A')}</p>"
            f"<blockquote>{quote}</blockquote>"
            f"<p>{para}</p></div>"
        )
    html_doc = (
        "<!DOCTYPE html><html><head><meta charset='UTF-8'>"
        f"<title>Review — {html_mod.escape(title)}</title>"
        "<style>body{font-family:sans-serif;max-width:800px;margin:0 auto;"
        "padding:20px}.claim{border:1px solid #ddd;margin:8px 0;padding:12px}"
        "blockquote{background:#f5f5f5;padding:8px 16px;"
        "border-left:4px solid #2196f3}</style></head><body>"
        f"<h1>Review — {html_mod.escape(title)}</h1>"
        "<p><b>External source. Scientific status: unverified.</b></p>"
        f"<p><b>Claims:</b> {len(claims)}</p>"
        + "".join(items) + "</body></html>"
    )
    path.write_text(html_doc, encoding="utf-8")
