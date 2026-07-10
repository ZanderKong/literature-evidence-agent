"""Deterministic validation of extracted claims.

Validates:
1. Schema compliance
2. Quote matching (exact, normalised, ambiguous, not_found)
3. Locator correctness (page, figure, table cross-reference)
4. External data isolation (leakage check)
"""

import re
import unicodedata
from typing import Any


def _normalize(text: str) -> str:
    """Normalize text: NFC unicode, collapse whitespace, normalize hyphens."""
    text = unicodedata.normalize("NFC", text)
    text = re.sub(r"\s+", " ", text)
    text = text.replace("\u2010", "-").replace("\u2011", "-")
    text = text.replace("\u2012", "-").replace("\u2013", "-")
    text = text.replace("\u2014", "-").replace("\u2015", "-")
    return text.strip()


def _normalize_newlines(text: str) -> str:
    """Normalize newlines (PDF artifact) and unicode."""
    text = text.replace("\n", " ").replace("\r", " ")
    return _normalize(text)


def match_quote(
    source_quote: str, section_text: str
) -> tuple[str, int | None, int | None]:
    """Match source_quote against text. Returns (status, start, end)."""
    # 1. Exact
    idx = section_text.find(source_quote)
    if idx >= 0:
        return ("exact", idx, idx + len(source_quote))

    # 2. Unicode normalised
    nq = _normalize(source_quote)
    nt = _normalize(section_text)
    idx = nt.find(nq)
    if idx >= 0:
        return ("normalised", idx, idx + len(nq))

    # 3. Newline + unicode
    nlq = _normalize_newlines(source_quote)
    nlt = _normalize_newlines(section_text)
    idx = nlt.find(nlq)
    if idx >= 0:
        second = nlt.find(nlq, idx + 1)
        if second >= 0:
            return ("ambiguous", None, None)
        return ("normalised", idx, idx + len(nlq))

    # 4. Partial — ambiguous
    words = nq.split() if source_quote else []
    if len(words) >= 5:
        found = sum(1 for w in words if w.lower() in nt.lower())
        if found / len(words) > 0.8:
            return ("ambiguous", None, None)

    return ("not_found", None, None)


def validate_schema(claim: dict[str, Any]) -> list[str]:
    """Validate claim schema. Returns error messages."""
    errors: list[str] = []
    for f in ["claim_type", "source_quote", "faithful_paraphrase",
              "evidence_basis_description"]:
        if not claim.get(f):
            errors.append(f"Missing required field: {f}")

    valid_types = {
        "background_statement", "method_statement", "reported_observation",
        "reported_result", "author_interpretation", "author_conclusion",
        "author_hypothesis", "author_limitation", "future_work",
    }
    ct = claim.get("claim_type", "")
    if ct and ct not in valid_types:
        errors.append(f"Invalid claim_type: {ct}")
    return errors


def check_leakage(claim: dict[str, Any]) -> list[str]:
    """Check external data isolation."""
    errors: list[str] = []
    forbidden = ["internal_measurements", "internal_sample",
                 "internal_db", "our_lab_id"]
    for key, value in claim.items():
        if isinstance(value, str):
            for fb in forbidden:
                if fb in value.lower():
                    errors.append(
                        f"Forbidden reference '{fb}' in field '{key}'"
                    )
    return errors


def validate_claims(
    raw_claims: list[dict[str, Any]],
    sections: list[dict[str, Any]],
    pages: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Validate all raw claims. Returns (validated, failed_locator, invalid_schema)."""
    validated: list[dict[str, Any]] = []
    failed_locator: list[dict[str, Any]] = []
    invalid_schema: list[dict[str, Any]] = []

    text_by_page: dict[int, str] = {}
    for p in pages:
        text_by_page[p["page"]] = p.get("text", "")

    all_text = "\n".join(s.get("text", "") for s in sections)

    for i, claim in enumerate(raw_claims):
        cid = f"CLM-{i:06d}"

        # 1. Schema
        se = validate_schema(claim)
        if se:
            claim["_validation_errors"] = se
            claim["_claim_id"] = cid
            invalid_schema.append(claim)
            continue

        # 2. Quote matching
        sq = claim.get("source_quote", "")
        loc = claim.get("locator_hint", {})
        cp = loc.get("page")
        match_status = "not_found"
        start = end = None

        if cp and cp in text_by_page:
            match_status, start, end = match_quote(sq, text_by_page[cp])

        if match_status in ("not_found", "ambiguous"):
            match_status, start, end = match_quote(sq, all_text)
            # Correct page if found
            if match_status in ("exact", "normalised") and cp:
                for pn, pt in text_by_page.items():
                    ps, _, _ = match_quote(sq, pt)
                    if ps in ("exact", "normalised"):
                        loc["page"] = pn
                        loc["_page_corrected"] = True
                        break

        # 3. Locator validation
        loc_errs: list[str] = []
        fp = loc.get("page")
        if fp is not None and fp not in text_by_page:
            loc_errs.append(f"Page {fp} does not exist")

        # Figure label check
        fl = loc.get("figure_label")
        if fl:
            found = any(fl.lower() in pt.lower()
                       for pt in text_by_page.values())
            if not found:
                loc["_figure_not_found"] = True
                loc_errs.append(f"Figure '{fl}' not in source")

        # Table label check
        tl = loc.get("table_label")
        if tl:
            found = any(tl.lower() in pt.lower()
                       for pt in text_by_page.values())
            if not found:
                loc["_table_not_found"] = True
                loc_errs.append(f"Table '{tl}' not in source")

        # Confidence
        if fp and match_status == "exact":
            loc["_locator_confidence"] = "high"
        elif fp and match_status == "normalised":
            loc["_locator_confidence"] = "medium"
        elif match_status in ("exact", "normalised"):
            loc["_locator_confidence"] = "low"

        if loc_errs:
            loc["_locator_errors"] = loc_errs

        # 4. Classify
        if match_status in ("exact", "normalised"):
            le = check_leakage(claim)
            if le:
                claim["_validation_errors"] = le
                claim["_claim_id"] = cid
                claim["_quote_match_status"] = match_status
                failed_locator.append(claim)
                continue

            claim["_claim_id"] = cid
            claim["_quote_match_status"] = match_status
            claim["_quote_char_start"] = start
            claim["_quote_char_end"] = end
            claim["origin_scope"] = "external"
            claim["scientific_verification_status"] = "unverified"
            claim["record_review_status"] = "pending"
            validated.append(claim)
        else:
            claim["_claim_id"] = cid
            claim["_quote_match_status"] = match_status
            claim["_validation_error"] = f"Quote: {match_status}"
            failed_locator.append(claim)

    return validated, failed_locator, invalid_schema
