"""Golden evaluation module — deterministic offline annotation conformance.

Provides:
- load_annotations(path) — load golden annotation JSONL
- load_extracted_claims(path) — load extracted claims JSONL
- evaluate_annotations(annotations, claims) — per-annotation evaluation
- validate_thresholds(metrics) — check against defined thresholds
- write_report(result, output_path) — write JSON report
"""

import json
from pathlib import Path
from typing import Any

GOLDEN_THRESHOLDS = {
    "recall": 80,
    "type_accuracy": 85,
    "hedging_preservation": 95,
    "scope_preservation": 90,
    "quote_match": 100,
    "locator_completeness": 100,
}


def load_annotations(path: Path) -> list[dict[str, Any]]:
    if path.suffix == ".jsonl":
        rows = []
        for line in path.read_text(encoding="utf-8").strip().split("\n"):
            if line.strip():
                rows.append(json.loads(line))
        return rows
    result = json.loads(path.read_text(encoding="utf-8"))
    return list(result)


def load_extracted_claims(path: Path) -> list[dict[str, Any]]:
    rows = []
    for line in path.read_text(encoding="utf-8").strip().split("\n"):
        if line.strip():
            rows.append(json.loads(line))
    return rows


def evaluate_annotations(
    annotations: list[dict[str, Any]],
    claims: list[dict[str, Any]],
) -> dict[str, Any]:
    positives = [a for a in annotations if a.get("must_extract")]
    negatives = [a for a in annotations if not a.get("must_extract")]

    matched_pos = 0
    quote_matched = 0
    locator_matched = 0
    type_matched = 0
    hedging_matched = 0
    scope_matched = 0
    per_annotation: list[dict[str, Any]] = []

    for p in positives:
        target_quote = (p.get("source_quote") or "").strip()
        target_type = p.get("claim_type", "")
        best = _find_best_match(claims, target_quote)

        status = "matched" if best else "unmatched"
        item = {
            "annotation_id": p.get("annotation_id", ""),
            "status": status,
            "expected_quote": target_quote[:100],
            "best_match_quote": (best.get("source_quote", "")[:100]) if best else "",
        }

        if best:
            matched_pos += 1
            if best.get("source_quote", "").strip():
                quote_matched += 1
                item["quote_ok"] = True
            else:
                item["quote_ok"] = False
            if best.get("page") is not None:
                locator_matched += 1
                item["locator_ok"] = True
            else:
                item["locator_ok"] = False
            if best.get("claim_type", "") == target_type:
                type_matched += 1
                item["type_ok"] = True
            else:
                item["type_ok"] = False
            if p.get("author_hedging"):
                if best.get("author_hedging") or _has_hedging(
                    best.get("faithful_paraphrase", "")
                ):
                    hedging_matched += 1
                    item["hedging_ok"] = True
                else:
                    item["hedging_ok"] = False
            if p.get("scope_description"):
                if best.get("scope_description"):
                    scope_matched += 1
                    item["scope_ok"] = True
                else:
                    item["scope_ok"] = False
        per_annotation.append(item)

    negative_matches = 0
    for n in negatives:
        neg_quote = (n.get("source_quote") or "").strip()
        if neg_quote and _find_best_match(claims, neg_quote):
            negative_matches += 1

    unsupported_accepted = 0
    positive_quotes = {(p.get("source_quote") or "").strip() for p in positives}
    for c in claims:
        quote = (c.get("source_quote") or "").strip()
        if quote and quote not in positive_quotes:
            is_negative = any(
                (n.get("source_quote") or "").strip() in quote for n in negatives
            )
            if not is_negative:
                unsupported_accepted += 1

    tp = len(positives)
    tn = len(negatives)
    quote_exp = sum(1 for p in positives if p.get("source_quote", "").strip())
    locator_exp = len(positives)
    type_exp = sum(1 for p in positives if p.get("claim_type"))
    hedging_exp = sum(1 for p in positives if p.get("author_hedging"))
    scope_exp = sum(1 for p in positives if p.get("scope_description"))

    metrics: dict[str, Any] = {
        "total_annotations": len(annotations),
        "positive_count": tp, "negative_count": tn,
        "claim_count": len(claims),
        "positive_matches": matched_pos,
        "negative_matches": negative_matches,
        "unsupported_accepted": unsupported_accepted,
        "recall": _pct(matched_pos, tp),
        "negative_extraction": _pct(negative_matches, tn),
        "quote_match": _pct(quote_matched, quote_exp),
        "locator_completeness": _pct(locator_matched, locator_exp),
        "type_accuracy": _pct(type_matched, type_exp),
        "hedging_preservation": _pct(hedging_matched, hedging_exp),
        "scope_preservation": _pct(scope_matched, scope_exp),
    }

    thresholds: dict[str, float] = dict(GOLDEN_THRESHOLDS)
    thresholds["negative_extraction"] = 0.0
    thresholds["unsupported_accepted"] = 0.0

    all_pass = True
    for key, threshold in thresholds.items():
        actual: float = metrics.get(key, 0.0)
        if key in ("negative_extraction", "unsupported_accepted"):
            if actual > threshold:
                metrics[f"{key}_status"] = "FAIL"
                all_pass = False
        elif actual < threshold:
            metrics[f"{key}_status"] = "FAIL"
            all_pass = False

    metrics["all_thresholds_pass"] = all_pass

    return {
        "schema_version": 1,
        "evaluation_type": "offline_deterministic_fixture",
        "annotation_count": len(annotations),
        "claim_count": len(claims),
        "metrics": metrics,
        "thresholds": thresholds,
        "all_thresholds_pass": all_pass,
        "per_annotation": per_annotation,
        "limitations": [
            "Offline deterministic conformance — not live model quality evaluation",
            "Annotations defined from controlled fixture content",
        ],
    }


def validate_thresholds(metrics: dict[str, Any]) -> bool:
    return bool(metrics.get("all_thresholds_pass", False))


def write_report(result: dict[str, Any], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(result, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def _find_best_match(
    claims: list[dict[str, Any]], target_quote: str | None,
) -> dict[str, Any] | None:
    if not target_quote:
        return None
    tq = target_quote.lower().strip()
    for c in claims:
        sq = (c.get("source_quote") or "").lower().strip()
        if tq in sq or _fuzzy(tq, sq):
            return c
    return None


def _fuzzy(target: str, candidate: str) -> bool:
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
