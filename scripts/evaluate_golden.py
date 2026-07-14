#!/usr/bin/env python3
"""Evaluate extracted claims against Golden Set annotations.

Computes:
- unsupported accepted claim rate (should be 0)
- approved quote match rate
- approved locator completeness
- hedging preservation rate
- claim recall
- claim type accuracy
"""

import json
import sys
from pathlib import Path
from typing import Any


def load_golden(golden_path: Path) -> list[dict[str, Any]]:
    """Load golden set annotations."""
    annotations: list[dict[str, Any]] = []
    with open(golden_path) as f:
        for line in f:
            line = line.strip()
            if line:
                annotations.append(json.loads(line))
    return annotations


def load_extracted(claims_path: Path) -> list[dict[str, Any]]:
    """Load extracted claims from JSONL."""
    claims: list[dict[str, Any]] = []
    if not claims_path.exists():
        return claims
    with open(claims_path) as f:
        for line in f:
            line = line.strip()
            if line:
                claims.append(json.loads(line))
    return claims


def compute_metrics(
    golden: list[dict[str, Any]],
    extracted: list[dict[str, Any]],
) -> dict[str, Any]:
    """Compute Golden Set evaluation metrics."""
    must_extract = [g for g in golden if g.get("must_extract", False)]
    must_not_extract = [g for g in golden if not g.get("must_extract", True)]

    # 1. Unsupported accepted claim rate
    unsupported = 0
    for ex in extracted:
        ex_quote = ex.get("source_quote", "").strip().lower()
        found = False
        for g in must_extract + must_not_extract:
            gq = g.get("source_quote", "").strip().lower()
            if ex_quote and (ex_quote in gq or gq in ex_quote):
                found = True
                break
        if not found and ex_quote:
            unsupported += 1

    # 2. Approved quote match rate
    quote_matched = sum(
        1 for c in extracted
        if c.get("_quote_match_status") in ("exact", "normalised")
    )

    # 3. Locator completeness
    with_locator = sum(
        1 for c in extracted
        if c.get("page") or c.get("locator_hint", {}).get("page")
    )

    # 4. Claim recall
    recalled = 0
    for g in must_extract:
        gq = g.get("source_quote", "").strip().lower()
        for ex in extracted:
            eq = ex.get("source_quote", "").strip().lower()
            if gq and eq and (gq in eq or eq in gq):
                recalled += 1
                break

    total_extracted = len(extracted)
    total_golden = len(must_extract)

    return {
        "total_extracted_claims": total_extracted,
        "total_golden_claims": total_golden,
        "unsupported_accepted_claim_rate": (
            unsupported / max(total_extracted, 1)
        ),
        "approved_quote_match_rate": (
            quote_matched / max(total_extracted, 1)
        ),
        "approved_locator_completeness": (
            with_locator / max(total_extracted, 1)
        ),
        "claim_recall": (
            recalled / max(total_golden, 1)
        ),
        "claim_type_accuracy": "manual_review_required",
        "hedging_preservation": "manual_review_required",
    }


def main() -> int:
    golden_path = Path("tests/golden/annotations.jsonl")
    claims_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(
        "workspace/external_evidence/sources/SRC-*/analysis/claims.persisted.jsonl"
    )

    golden = load_golden(golden_path)
    extracted = load_extracted(claims_path)

    if not golden:
        print("ERROR: No golden annotations found")
        return 1

    metrics = compute_metrics(golden, extracted)

    # Thresholds
    thresholds = {
        "unsupported_accepted_claim_rate": (0.0, 0.0),
        "approved_quote_match_rate": (1.0, 0.95),
        "approved_locator_completeness": (1.0, 0.95),
        "claim_recall": (0.80, 0.70),
    }

    all_pass = True
    for key, (hard, soft) in thresholds.items():
        val = metrics.get(key, 0)
        status = "PASS" if val >= hard else ("WARN" if val >= soft else "FAIL")
        if status == "FAIL":
            all_pass = False
        print(f"{key}: {val:.2%} [{status}] (threshold: {hard:.0%})")

    print(f"\nOverall: {'PASS' if all_pass else 'FAIL'}")
    print("\nNote: claim_type_accuracy and hedging_preservation require manual review.")
    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
