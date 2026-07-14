"""Golden set evaluator: calculate recall, negative extraction, quote match,
locator completeness, claim type accuracy, hedging, scope.
"""

from typing import Any

from tests.golden.golden_loader import load_golden


def evaluate_golden(extracted_claims: list[dict[str, Any]]) -> dict[str, Any]:
    """Evaluate extracted claims against golden set."""
    golden = load_golden()

    positives = [g for g in golden if g["label"] == "positive"]
    negatives = [g for g in golden if g["label"] == "negative"]

    all_paraphrase = " ".join(
        c.get("faithful_paraphrase", "") + " " +
        c.get("source_quote", "")
        for c in extracted_claims
    ).lower()

    matched_pos = 0
    quote_matched = 0
    locator_matched = 0
    type_matched = 0
    hedging_matched = 0
    scope_matched = 0

    for p in positives:
        target_type = p.get("claim_type")
        pattern = p.get("pattern", "").lower()

        if pattern and pattern in all_paraphrase:
            matched_pos += 1

        if pattern and target_type:
            for c in extracted_claims:
                if pattern in (c.get("faithful_paraphrase", "") + " " +
                               c.get("source_quote", "")).lower():
                    if p.get("quote_required"):
                        if c.get("source_quote", "").strip():
                            quote_matched += 1

                    if p.get("locator_required"):
                        if c.get("page") is not None:
                            locator_matched += 1

                    if c.get("claim_type", "") == target_type:
                        type_matched += 1

                    if p.get("hedging"):
                        if c.get("author_hedging") or _has_hedging(
                            c.get("faithful_paraphrase", "")
                        ):
                            hedging_matched += 1

                    if p.get("scope"):
                        if c.get("scope_description"):
                            scope_matched += 1
                    break

    negative_matches = 0
    for n in negatives:
        pattern = n.get("pattern", "").lower()
        if pattern and pattern in all_paraphrase:
            negative_matches += 1

    total_positives = len(positives)
    quote_expected = sum(1 for p in positives if p.get("quote_required"))
    locator_expected = sum(1 for p in positives if p.get("locator_required"))
    type_expected = sum(1 for p in positives if p.get("claim_type"))
    hedging_expected = sum(1 for p in positives if p.get("hedging"))
    scope_expected = sum(1 for p in positives if p.get("scope"))

    metrics = {
        "total_golden": len(golden),
        "positive_count": total_positives,
        "negative_count": len(negatives),
        "extracted_claims": len(extracted_claims),
        "positive_matches": matched_pos,
        "negative_matches": negative_matches,
        "recall": round(matched_pos / total_positives * 100, 1) if total_positives else 0,
        "negative_extraction": round(negative_matches / len(negatives) * 100, 1) if negatives else 0,
        "quote_match": round(quote_matched / quote_expected * 100, 1) if quote_expected else 100,
        "locator_completeness": round(locator_matched / locator_expected * 100, 1) if locator_expected else 100,
        "type_accuracy": round(type_matched / type_expected * 100, 1) if type_expected else 100,
        "hedging_preservation": round(hedging_matched / hedging_expected * 100, 1) if hedging_expected else 100,
        "scope_preservation": round(scope_matched / scope_expected * 100, 1) if scope_expected else 100,
    }

    thresholds = {
        "unsupported": 0,
        "negative_extraction": 0,
        "quote_match": 100,
        "locator_completeness": 100,
        "recall": 80,
        "type_accuracy": 85,
        "hedging_preservation": 95,
        "scope_preservation": 90,
    }

    passed = True
    for key, threshold in thresholds.items():
        actual = metrics.get(key, 0)
        if actual < threshold:
            passed = False
            metrics[f"{key}_threshold"] = threshold
            metrics[f"{key}_status"] = "FAIL" if key != "unsupported" else (
                "FAIL" if actual > 0 else "PASS"
            )

    metrics["all_thresholds_pass"] = passed
    return metrics


def _has_hedging(text: str) -> bool:
    hedging_words = ["may", "might", "could", "suggest", "potential",
                     "possibly", "likely", "appears", "indicate"]
    return any(w in text.lower() for w in hedging_words)
