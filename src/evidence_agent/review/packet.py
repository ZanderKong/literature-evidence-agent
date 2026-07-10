"""Review packet generation — reads from database by run_id."""

import csv
import json
from pathlib import Path
from typing import Any

from evidence_agent.database.connection import get_connection


def generate_review_packet(
    run_id: str, output_dir: Path | None = None
) -> dict[str, str]:
    """Generate review packet from database claims for a processing run.

    Reads pending claims created by the given run_id, generates
    CSV/JSONL/MD/HTML review files.

    Returns dict mapping output type to file path.
    """
    from evidence_agent.config import config

    if output_dir is None:
        output_dir = config.review_dir / run_id
    output_dir.mkdir(parents=True, exist_ok=True)

    # Read claims from DB
    with get_connection(read_only=True) as conn:
        cursor = conn.execute(
            "SELECT c.*, l.page, l.figure_label, l.table_label, "
            "l.locator_confidence, s.title as source_title "
            "FROM source_claims c "
            "LEFT JOIN claim_locators l ON c.claim_id = l.claim_id "
            "LEFT JOIN sources s ON c.source_id = s.source_id "
            "WHERE c.created_by_run_id = ? "
            "AND c.record_review_status = 'pending' "
            "ORDER BY l.page, c.claim_type",
            (run_id,),
        )
        claims = [dict(row) for row in cursor.fetchall()]

    if not claims:
        raise ValueError(
            f"NO_PENDING_CLAIMS: No pending claims for run {run_id}"
        )

    source_title = claims[0].get("source_title", "Untitled")

    # Generate outputs
    paths: dict[str, str] = {}

    # CSV
    csv_path = output_dir / "claims_for_review.csv"
    _write_csv(claims, csv_path)
    paths["csv"] = str(csv_path)

    # JSONL
    jsonl_path = output_dir / "claims_for_review.jsonl"
    with open(jsonl_path, "w", encoding="utf-8") as f:
        for c in claims:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")
    paths["jsonl"] = str(jsonl_path)

    # Markdown
    md_path = output_dir / "review_packet.md"
    _write_md(claims, source_title, md_path)
    paths["markdown"] = str(md_path)

    # HTML
    html_path = output_dir / "review_packet.html"
    _write_html(claims, source_title, html_path)
    paths["html"] = str(html_path)

    # Instructions
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


def _write_csv(claims: list[dict[str, Any]], path: Path) -> None:
    fields = [
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
            row = {k: c.get(k, "") for k in fields}
            w.writerow(row)


def _write_md(
    claims: list[dict[str, Any]], title: str, path: Path
) -> None:
    lines = [f"# Review — {title}\n", f"**Claims:** {len(claims)}\n", "---\n"]
    for i, c in enumerate(claims, 1):
        cid = c.get("claim_id", f"CLM-{i}")
        lines.append(f"## {i}. {cid}\n")
        lines.append(f"- **Type:** {c.get('claim_type', 'N/A')}")
        lines.append(f"- **Page:** {c.get('page', 'N/A')}")
        lines.append(f"- **Match:** {c.get('quote_match_status', 'N/A')}\n")
        lines.append(f"> {c.get('source_quote', 'N/A')}\n")
        lines.append(f"**Paraphrase:** {c.get('faithful_paraphrase', '')}\n")
        lines.append("---\n")
    path.write_text("\n".join(lines), encoding="utf-8")


def _write_html(
    claims: list[dict[str, Any]], title: str, path: Path
) -> None:
    import html
    items = []
    for i, c in enumerate(claims, 1):
        cid = html.escape(c.get("claim_id", f"CLM-{i}"))
        quote = html.escape(c.get("source_quote", ""))
        para = html.escape(c.get("faithful_paraphrase", ""))
        items.append(
            f"<div class='claim'><h3>{i}. {cid}</h3>"
            f"<p><b>Type:</b> {html.escape(c.get('claim_type',''))} | "
            f"<b>Page:</b> {c.get('page','N/A')}</p>"
            f"<blockquote>{quote}</blockquote>"
            f"<p>{para}</p></div>"
        )
    html_doc = (
        "<!DOCTYPE html><html><head><meta charset='UTF-8'>"
        f"<title>Review — {html.escape(title)}</title>"
        "<style>body{font-family:sans-serif;max-width:800px;margin:0 auto;"
        "padding:20px}.claim{border:1px solid #ddd;margin:8px 0;padding:12px}"
        "blockquote{background:#f5f5f5;padding:8px 16px;"
        "border-left:4px solid #2196f3}</style></head><body>"
        f"<h1>Review — {html.escape(title)}</h1>"
        "<p><b>⚠️ External source. Scientific status: unverified.</b></p>"
        f"<p><b>Claims:</b> {len(claims)}</p>"
        + "".join(items) + "</body></html>"
    )
    path.write_text(html_doc, encoding="utf-8")
