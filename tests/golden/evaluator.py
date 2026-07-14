"""Golden set evaluator: per-annotation matching with strict thresholds.

Matches each annotation individually against extracted claims.
Computes recall, negative extraction, unsupported_accepted,
quote_match, locator_completeness, claim_type accuracy,
hedging preservation, scope preservation.
"""

import json
from pathlib import Path
from typing import Any

GOLDEN_DIR = Path(__file__).resolve().parent


def load_golden() -> list[dict[str, Any]]:
    path = GOLDEN_DIR / "golden_set.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    raise FileNotFoundError(f"Golden set not found: {path}")


def evaluate_golden(extracted_claims: list[dict[str, Any]]) -> dict[str, Any]:
    """Evaluate extracted claims against golden set, matching per-annotation."""
    golden = load_golden()
    positives = [g for g in golden if g["must_extract"]]
    negatives = [g for g in golden if not g["must_extract"]]

    matched_pos = 0
    quote_matched = 0
    locator_matched = 0
    type_matched = 0
    hedging_matched = 0
    scope_matched = 0

    for p in positives:
        target_quote = (p.get("source_quote") or "").strip()
        target_type = p.get("claim_type", "")

        best = _find_best_match(extracted_claims, target_quote)

        if best is not None:
            matched_pos += 1

            if best.get("source_quote", "").strip():
                quote_matched += 1

            if best.get("page") is not None:
                locator_matched += 1

            if best.get("claim_type", "") == target_type:
                type_matched += 1

            if p.get("author_hedging"):
                if best.get("author_hedging") or _has_hedging(
                    best.get("faithful_paraphrase", "")
                ):
                    hedging_matched += 1

            if p.get("scope_description"):
                if best.get("scope_description"):
                    scope_matched += 1

    negative_matches = 0
    for n in negatives:
        neg_quote = (n.get("source_quote") or "").strip()
        if neg_quote:
            best = _find_best_match(extracted_claims, neg_quote)
            if best is not None:
                negative_matches += 1

    unsupported_accepted = 0
    positive_quotes = {(p.get("source_quote") or "").strip() for p in positives}
    for c in extracted_claims:
        quote = (c.get("source_quote") or "").strip()
        if quote and quote not in positive_quotes:
            is_negative = False
            for n in negatives:
                nq = (n.get("source_quote") or "").strip()
                if nq and nq in quote:
                    is_negative = True
                    break
            if not is_negative:
                best = _find_best_match(list(extracted_claims), None)
                unsupported_accepted += 1
                break

    total_positives = len(positives)
    quote_expected = sum(1 for p in positives if p.get("source_quote", "").strip())
    locator_expected = sum(1 for p in positives)
    type_expected = sum(1 for p in positives if p.get("claim_type"))
    hedging_expected = sum(1 for p in positives if p.get("author_hedging"))
    scope_expected = sum(1 for p in positives if p.get("scope_description"))

    metrics = {
        "total_golden": len(golden),
        "positive_count": total_positives,
        "negative_count": len(negatives),
        "extracted_claims": len(extracted_claims),
        "positive_matches": matched_pos,
        "negative_matches": negative_matches,
        "unsupported_accepted": unsupported_accepted,
        "recall": _pct(matched_pos, total_positives),
        "negative_extraction": _pct(negative_matches, len(negatives)),
        "quote_match": _pct(quote_matched, quote_expected),
        "locator_completeness": _pct(locator_matched, locator_expected),
        "type_accuracy": _pct(type_matched, type_expected),
        "hedging_preservation": _pct(hedging_matched, hedging_expected),
        "scope_preservation": _pct(scope_matched, scope_expected),
    }

    thresholds_pass = True
    if metrics["unsupported_accepted"] > 0:
        metrics["unsupported_accepted_status"] = "FAIL"
        thresholds_pass = False
    if metrics["negative_extraction"] > 0:
        metrics["negative_extraction_status"] = "FAIL"
        thresholds_pass = False
    if metrics["quote_match"] < 100 and quote_expected > 0:
        metrics["quote_match_status"] = "FAIL"
        thresholds_pass = False
    if metrics["locator_completeness"] < 100 and locator_expected > 0:
        metrics["locator_completeness_status"] = "FAIL"
        thresholds_pass = False
    if metrics["recall"] < 80 and total_positives > 0:
        metrics["recall_status"] = "FAIL"
        thresholds_pass = False
    if metrics["type_accuracy"] < 85 and type_expected > 0:
        metrics["type_accuracy_status"] = "FAIL"
        thresholds_pass = False
    if metrics["hedging_preservation"] < 95 and hedging_expected > 0:
        metrics["hedging_preservation_status"] = "FAIL"
        thresholds_pass = False
    if metrics["scope_preservation"] < 90 and scope_expected > 0:
        metrics["scope_preservation_status"] = "FAIL"
        thresholds_pass = False

    metrics["all_thresholds_pass"] = thresholds_pass
    return metrics


def _find_best_match(
    claims: list[dict[str, Any]], target_quote: str | None,
) -> dict[str, Any] | None:
    """Find best matching claim for a target quote. Returns None if no match."""
    if not target_quote:
        return None
    tq_lower = target_quote.lower().strip()
    for c in claims:
        sq = (c.get("source_quote") or "").lower().strip()
        if tq_lower in sq or _fuzzy_match(tq_lower, sq):
            return c
    return None


def _fuzzy_match(target: str, candidate: str) -> bool:
    """Fuzzy match: 70% of target words appear in candidate."""
    twords = [w for w in target.split() if len(w) > 2]
    if not twords:
        return False
    matched = sum(1 for w in twords if w in candidate)
    return matched / len(twords) >= 0.7


def _has_hedging(text: str) -> bool:
    words = ["may", "might", "could", "suggest", "potential",
             "possibly", "likely", "appears", "indicate"]
    return any(w in text.lower() for w in words)


def _pct(num: int, denom: int) -> float:
    if denom == 0:
        return 100.0
    return round(num / denom * 100, 1)
