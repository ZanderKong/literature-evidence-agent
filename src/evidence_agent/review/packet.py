"""Review packet generation.

Generates CSV, JSONL, Markdown, and HTML review packages
for human review of extracted claims.
"""

import csv
import json
from pathlib import Path
from typing import Any


def generate_review_csv(
    claims: list[dict[str, Any]], output_path: Path
) -> None:
    """Generate a CSV file for human review."""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = [
        "claim_id",
        "decision",
        "edited_source_quote",
        "edited_faithful_paraphrase",
        "edited_evidence_basis_description",
        "edited_claim_type",
        "edited_page",
        "edited_section",
        "review_reason",
        "reviewer",
    ]

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for claim in claims:
            claim_id = claim.get("_claim_id", "")
            row = {
                "claim_id": claim_id,
                "decision": "",
                "edited_source_quote": "",
                "edited_faithful_paraphrase": "",
                "edited_evidence_basis_description": "",
                "edited_claim_type": "",
                "edited_page": "",
                "edited_section": "",
                "review_reason": "",
                "reviewer": "",
            }
            writer.writerow(row)


def generate_review_jsonl(
    claims: list[dict[str, Any]], output_path: Path
) -> None:
    """Generate a JSONL file with full claim data for review."""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        for claim in claims:
            f.write(json.dumps(claim, ensure_ascii=False) + "\n")


def generate_review_markdown(
    claims: list[dict[str, Any]], source_title: str, output_path: Path
) -> None:
    """Generate a Markdown review packet."""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    lines: list[str] = []
    lines.append(f"# Review Packet — {source_title}\n")
    lines.append(f"**Claims to review:** {len(claims)}\n")
    lines.append("---\n")

    for i, claim in enumerate(claims, start=1):
        claim_id = claim.get("_claim_id", f"CLM-{i:06d}")
        lines.append(f"## Claim {i}: {claim_id}\n")
        lines.append(f"- **Type:** {claim.get('claim_type', 'N/A')}")
        lines.append(f"- **Page:** {claim.get('locator_hint', {}).get('page', 'N/A')}")
        section = claim.get('locator_hint', {}).get('section_heading', 'N/A')
        lines.append(f"- **Section:** {section}")
        lines.append(f"- **Match:** {claim.get('_quote_match_status', 'N/A')}\n")
        lines.append(f"### Source Quote\n> {claim.get('source_quote', 'N/A')}\n")
        lines.append(f"### Faithful Paraphrase\n{claim.get('faithful_paraphrase', 'N/A')}\n")
        lines.append(f"### Evidence Basis\n{claim.get('evidence_basis_description', 'N/A')}\n")
        hedging = claim.get("author_hedging")
        if hedging:
            lines.append(f"### Author Hedging\n`{hedging}`\n")
        lines.append("---\n")

    output_path.write_text("\n".join(lines), encoding="utf-8")


def generate_review_html(
    claims: list[dict[str, Any]], source_title: str, output_path: Path
) -> None:
    """Generate a static HTML review packet."""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    claim_items: list[str] = []
    for i, claim in enumerate(claims, start=1):
        claim_id = claim.get("_claim_id", f"CLM-{i:06d}")
        claim_items.append(
            f"""<div class="claim">
<h3>Claim {i}: {claim_id}</h3>
<table>
<tr><td><strong>Type:</strong></td><td>{claim.get('claim_type', 'N/A')}</td></tr>
<tr><td><strong>Page:</strong></td><td>{claim.get('locator_hint', {}).get('page', 'N/A')}</td></tr>
<tr><td><strong>Match:</strong></td><td>{claim.get('_quote_match_status', 'N/A')}</td></tr>
</table>
<h4>Source Quote</h4>
<blockquote>{claim.get('source_quote', 'N/A')}</blockquote>
<h4>Paraphrase</h4>
<p>{claim.get('faithful_paraphrase', 'N/A')}</p>
<h4>Evidence Basis</h4>
<p>{claim.get('evidence_basis_description', 'N/A')}</p>
</div>"""
        )

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Review Packet — {source_title}</title>
<style>
body {{ font-family: system-ui, sans-serif; max-width: 800px; margin: 0 auto; padding: 20px; }}
.claim {{ border: 1px solid #ddd; margin: 16px 0; padding: 16px; border-radius: 8px; }}
.claim h3 {{ margin-top: 0; }}
blockquote {{ background: #f5f5f5; padding: 8px 16px; border-left: 4px solid #2196f3; }}
table {{ border-collapse: collapse; }}
td {{ padding: 4px 8px; }}
.warning {{ background: #fff3e0; padding: 16px; border-radius: 8px; margin-bottom: 20px; }}
</style>
</head>
<body>
<h1>Review Packet — {source_title}</h1>
<div class="warning">
<strong>⚠️ Important:</strong> "Approved" only means the record faithfully
reflects what the authors stated. It does NOT mean the scientific claim
has been internally verified.
</div>
<p><strong>Claims to review:</strong> {len(claims)}</p>
{''.join(claim_items)}
</body>
</html>"""

    output_path.write_text(html, encoding="utf-8")


def generate_review_packet(
    validated_claims: list[dict[str, Any]],
    failed_locators: list[dict[str, Any]],
    run_id: str,
    source_title: str = "Untitled Source",
    output_dir: Path | None = None,
) -> dict[str, str]:
    """Generate a complete review packet.

    Returns dict mapping output type to file path.
    """
    from evidence_agent.config import config

    if output_dir is None:
        output_dir = config.review_dir / run_id

    output_dir.mkdir(parents=True, exist_ok=True)

    # CSV
    csv_path = output_dir / "claims_for_review.csv"
    generate_review_csv(validated_claims, csv_path)

    # JSONL
    jsonl_path = output_dir / "claims_for_review.jsonl"
    generate_review_jsonl(validated_claims, jsonl_path)

    # Markdown
    md_path = output_dir / "review_packet.md"
    generate_review_markdown(validated_claims, source_title, md_path)

    # HTML
    html_path = output_dir / "review_packet.html"
    generate_review_html(validated_claims, source_title, html_path)

    # Failed locators
    failed_path = output_dir / "failed_locators.jsonl"
    with open(failed_path, "w", encoding="utf-8") as f:
        for claim in failed_locators:
            f.write(json.dumps(claim, ensure_ascii=False) + "\n")

    # Instructions
    instructions = output_dir / "review_instructions.md"
    instructions.write_text(
        "# Review Instructions\n\n"
        "1. Open `claims_for_review.csv` in your spreadsheet editor.\n"
        "2. For each claim, enter one of: approve, approve_with_edits, "
        "reject, mark_missing, needs_followup\n"
        "3. If approving with edits, fill in the edited_* columns.\n"
        "4. Save the CSV and run: `evidence-agent review apply <csv_path>`\n\n"
        "## ⚠️ Important\n\n"
        "- 'Approved' means the record accurately reflects the source.\n"
        "- It does NOT mean the scientific claim has been verified internally.\n"
        "- All approved records will be tagged: 'External source, "
        "scientific status: unverified'\n",
        encoding="utf-8",
    )

    return {
        "csv": str(csv_path),
        "jsonl": str(jsonl_path),
        "markdown": str(md_path),
        "html": str(html_path),
        "failed_locators": str(failed_path),
        "instructions": str(instructions),
    }
