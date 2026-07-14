"""Review packet generation — reads from database by run_id.

Creates review_batches and review_batch_rows in the database
for tracking and idempotency. Same run + same packet hash
reuses existing batch/row IDs.

Exports CSV/JSONL/MD/HTML with full context:
- section heading, context_before/after, page, figure/table
- model/mode, prompt version, parser version, code commit
- review/scientific status
- HTML-escaped in all formats
- Only relative paths, no absolute paths
- Atomic file writes
"""

import csv
import hashlib
import html as html_mod
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from evidence_agent.database.connection import get_connection
from evidence_agent.ids import generate_batch_id, generate_row_id, now_iso
from evidence_agent.runtime import get_current_context

CANONICAL_ROW_KEYS = [
    "claim_id", "claim_type", "source_quote", "faithful_paraphrase",
    "evidence_basis_description", "page", "figure_label", "table_label",
]

CONTEXT_RADIUS = 240


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


def extract_quote_context(
    section_text: str, quote: str, radius: int = CONTEXT_RADIUS,
) -> tuple[str, str]:
    """Extract context_before and context_after around a quote in section text.

    Returns (context_before, context_after). Tries exact match first,
    then normalised whitespace match.
    """
    if not section_text or not quote:
        return ("", "")

    def _find_pos(text: str, q: str) -> int:
        idx = text.find(q)
        if idx >= 0:
            return idx

        import re
        q_norm = re.sub(r"\s+", "", q)
        t_norm = re.sub(r"\s+", "", text)
        idx_n = t_norm.find(q_norm)
        if idx_n < 0:
            return -1

        pos = 0
        nt = 0
        for ch in text:
            if ch.strip():
                nt += 1
            if nt > idx_n:
                break
            pos += 1
        return pos

    pos = _find_pos(section_text, quote)
    if pos < 0:
        return ("", "")

    start = max(0, pos - radius)
    end = min(len(section_text), pos + len(quote) + radius)

    before = section_text[start:pos].strip()
    after = section_text[pos + len(quote):end].strip()

    return (before, after)


def _esc(val: Any) -> str:
    """HTML-escape a value, converting None to empty string."""
    if val is None:
        return ""
    return html_mod.escape(str(val))


def _atomic_write_text(path: Path, content: str) -> None:
    """Write file atomically: tmp → flush → fsync → os.replace."""
    fd, tmp_name = tempfile.mkstemp(suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_name, str(path))
    except Exception:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)
        raise


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
    """Generate review packet with full context and provenance.

    Idempotent: same run + same claims content reuses existing batch/row IDs.
    """
    runtime = get_current_context()

    if output_dir is None:
        output_dir = runtime.review_dir / run_id
    output_dir.mkdir(parents=True, exist_ok=True)

    query = (
        "SELECT c.*, l.page, l.figure_label, l.table_label, "
        "l.locator_confidence, "
        "s.title as source_title, "
        "ss.heading as section_heading, ss.text as section_text, "
        "a.relative_path as asset_relative_path, "
        "r.model_name, r.model_mode, r.prompt_version, "
        "r.parser_name as run_parser_name, r.code_commit "
        "FROM source_claims c "
        "LEFT JOIN claim_locators l ON c.claim_id = l.claim_id "
        "LEFT JOIN sources s ON c.source_id = s.source_id "
        "LEFT JOIN source_assets a ON c.source_id = a.source_id "
        "LEFT JOIN source_sections ss "
        "  ON c.source_id = ss.source_id AND l.page = ss.page_start "
        "LEFT JOIN processing_runs r "
        "  ON c.created_by_run_id = r.run_id "
        "WHERE c.created_by_run_id = ? "
        "AND c.record_review_status = 'pending' "
        "ORDER BY COALESCE(l.page, 2147483647), c.claim_type, c.claim_id"
    )

    with get_connection(read_only=True) as conn:
        cursor = conn.execute(query, (run_id,))
        claims = [dict(row) for row in cursor.fetchall()]

    if not claims:
        raise ValueError(
            f"NO_PENDING_CLAIMS: No pending claims for run {run_id}"
        )

    for c in claims:
        quote = c.get("source_quote") or ""
        section_text = c.get("section_text") or ""
        ctx_before, ctx_after = extract_quote_context(section_text, quote)
        c["context_before"] = ctx_before
        c["context_after"] = ctx_after

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
    _write_jsonl(claims, claim_ids_to_row_info, jsonl_path)
    paths["jsonl"] = str(jsonl_path)

    md_path = output_dir / "review_packet.md"
    _write_md(claims, claim_ids_to_row_info, source_title, md_path)
    paths["markdown"] = str(md_path)

    html_path = output_dir / "review_packet.html"
    _write_html(claims, claim_ids_to_row_info, source_title, html_path)
    paths["html"] = str(html_path)

    inst_path = output_dir / "review_instructions.md"
    _atomic_write_text(
        inst_path,
        "# Review Instructions\n\n"
        "1. Open `claims_for_review.csv`.\n"
        "2. For each claim, set decision: approve, approve_with_edits, "
        "reject, mark_missing, needs_followup.\n"
        "3. If approve_with_edits, fill edited_* columns.\n"
        "4. Run: `evidence-agent review apply <path>`\n\n"
        "Warning: 'Approved' means the record faithfully reflects the source. "
        "It does NOT mean the claim has been verified internally.\n",
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
        "claim_id", "source_id",
        "source_title", "source_relative_path",
        "claim_type", "source_quote",
        "context_before", "context_after",
        "faithful_paraphrase", "evidence_basis_description",
        "page", "section_id", "section_heading",
        "figure_label", "table_label",
        "quote_match_status", "locator_confidence",
        "model_name", "model_mode", "prompt_version",
        "parser_name", "code_commit",
        "record_review_status", "scientific_verification_status",
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
            row["source_relative_path"] = c.get("asset_relative_path", "")
            row["section_id"] = c.get("section_id", "")
            row["section_heading"] = c.get("section_heading", "")
            row["model_name"] = c.get("model_name", "")
            row["model_mode"] = c.get("model_mode", "")
            row["prompt_version"] = c.get("prompt_version", "")
            row["parser_name"] = c.get("run_parser_name", "")
            row["code_commit"] = c.get("code_commit", "")
            row["record_review_status"] = c.get("record_review_status", "")
            row["scientific_verification_status"] = (
                c.get("scientific_verification_status", "")
            )
            w.writerow(row)


def _write_jsonl(
    claims: list[dict[str, Any]],
    batch_info: dict[str, dict[str, str]],
    path: Path,
) -> None:
    lines = []
    for c in claims:
        cid = c["claim_id"]
        hi = batch_info.get(cid, {})
        merged = {**c, **{k: v for k, v in hi.items() if v}}
        merged["source_relative_path"] = c.get("asset_relative_path", "")
        merged["section_heading"] = c.get("section_heading", "")
        merged["model_name"] = c.get("model_name", "")
        merged["model_mode"] = c.get("model_mode", "")
        merged["prompt_version"] = c.get("prompt_version", "")
        merged["parser_name"] = c.get("run_parser_name", "")
        merged["code_commit"] = c.get("code_commit", "")
        lines.append(json.dumps(merged, ensure_ascii=False) + "\n")
    _atomic_write_text(path, "".join(lines))


def _write_md(
    claims: list[dict[str, Any]],
    batch_info: dict[str, dict[str, str]],
    title: str,
    path: Path,
) -> None:
    lines = [
        f"# Review — {title}\n",
        "**External source. Scientific status: unverified.**\n",
        f"**Claims:** {len(claims)}\n",
        "---\n",
    ]
    for i, c in enumerate(claims, 1):
        cid = _esc(c.get("claim_id", f"CLM-{i}"))
        hi = batch_info.get(c.get("claim_id", ""), {})
        lines.append(f"## {i}. {cid}\n")
        lines.append(f"- **Batch:** {_esc(hi.get('review_batch_id',''))}")
        lines.append(f"- **Row:** {_esc(hi.get('review_row_id',''))}")
        lines.append(f"- **Type:** {_esc(c.get('claim_type', ''))}")
        lines.append(f"- **Page:** {c.get('page', 'N/A')}")
        sec_heading = _esc(c.get("section_heading"))
        if sec_heading:
            lines.append(f"- **Section:** {sec_heading}")
        lines.append(
            f"- **Match:** {_esc(c.get('quote_match_status', ''))}\n"
        )
        ctx_before = _esc(c.get("context_before"))
        if ctx_before:
            lines.append(f"*Context before:* {ctx_before}\n")
        lines.append(f"> {_esc(c.get('source_quote', 'N/A'))}\n")
        ctx_after = _esc(c.get("context_after"))
        if ctx_after:
            lines.append(f"*Context after:* {ctx_after}\n")
        lines.append(
            f"**Paraphrase:** {_esc(c.get('faithful_paraphrase', ''))}\n"
        )
        lines.append("---\n")
    _atomic_write_text(path, "\n".join(lines))


def _write_html(
    claims: list[dict[str, Any]],
    batch_info: dict[str, dict[str, str]],
    title: str,
    path: Path,
) -> None:
    items = []
    for i, c in enumerate(claims, 1):
        cid = _esc(c.get("claim_id", f"CLM-{i}"))
        hi = batch_info.get(c.get("claim_id", ""), {})
        ctx_before = _esc(c.get("context_before"))
        ctx_after = _esc(c.get("context_after"))
        quote = _esc(c.get("source_quote", ""))
        para = _esc(c.get("faithful_paraphrase", ""))
        sec_heading = _esc(c.get("section_heading"))

        meta = (
            f"<p>"
            f"<b>Batch:</b> {_esc(hi.get('review_batch_id',''))}"
            f" | <b>Row:</b> {_esc(hi.get('review_row_id',''))}"
            f" | <b>Type:</b> {_esc(c.get('claim_type',''))}"
            f" | <b>Page:</b> {c.get('page','N/A')}"
        )
        if sec_heading:
            meta += f" | <b>Section:</b> {sec_heading}"
        meta += "</p>"

        ctx_html = ""
        if ctx_before:
            ctx_html += f"<p class='context'><em>Before:</em> {ctx_before}</p>"
        if ctx_after:
            ctx_html += f"<p class='context'><em>After:</em> {ctx_after}</p>"

        items.append(
            f"<div class='claim'><h3>{i}. {cid}</h3>"
            f"{meta}"
            f"<blockquote>{quote}</blockquote>"
            f"{ctx_html}"
            f"<p>{para}</p></div>"
        )
    html_doc = (
        "<!DOCTYPE html><html><head><meta charset='UTF-8'>"
        f"<title>Review — {_esc(title)}</title>"
        "<style>body{font-family:sans-serif;max-width:800px;margin:0 auto;"
        "padding:20px}.claim{border:1px solid #ddd;margin:8px 0;padding:12px}"
        "blockquote{background:#f5f5f5;padding:8px 16px;"
        "border-left:4px solid #2196f3}"
        ".context{color:#666;font-size:0.9em}</style></head><body>"
        f"<h1>Review — {_esc(title)}</h1>"
        "<p><b>External source. Scientific status: unverified.</b></p>"
        f"<p><b>Claims:</b> {len(claims)}</p>"
        + "".join(items) + "</body></html>"
    )
    _atomic_write_text(path, html_doc)
