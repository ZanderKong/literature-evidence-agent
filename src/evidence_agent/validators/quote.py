"""Deterministic validation of extracted claims.

Validates:
1. Schema compliance
2. Quote matching (exact, normalised, ambiguous, not_found)
3. Locator correctness
4. External data isolation (leakage check)
"""

import re
import unicodedata
from typing import Any


def _normalize(text: str) -> str:
    """Normalize text for comparison: unicode NFC, collapse whitespace."""
    # Unicode normalization
    text = unicodedata.normalize("NFC", text)
    # Collapse whitespace
    text = re.sub(r"\s+", " ", text)
    # Normalize hyphens
    text = text.replace("‐", "-").replace("‑", "-").replace("‒", "-")
    text = text.replace("\u2010", "-").replace("\u2011", "-")
    text = text.replace("\u2012", "-").replace("\u2013", "-")
    text = text.replace("\u2014", "-").replace("\u2015", "-")
    return text.strip()


def _normalize_newlines(text: str) -> str:
    """Normalize by also removing newlines that PDF parsers introduce."""
    text = text.replace("\n", " ").replace("\r", " ")
    return _normalize(text)


def match_quote(
    source_quote: str, section_text: str
) -> tuple[str, int | None, int | None]:
    """Match a source_quote against section text.

    Returns (match_status, char_start, char_end).

    Tries in order:
    1. Exact match
    2. Unicode normalised match
    3. Whitespace collapsed match
    4. Newline + unicode normalised match
    5. Not found
    """
    # 1. Exact match
    idx = section_text.find(source_quote)
    if idx >= 0:
        return ("exact", idx, idx + len(source_quote))

    # 2. Unicode normalised
    norm_quote = _normalize(source_quote)
    norm_text = _normalize(section_text)
    idx = norm_text.find(norm_quote)
    if idx >= 0:
        return ("normalised", idx, idx + len(norm_quote))

    # 3. Newline normalised (for PDF line breaks)
    nl_quote = _normalize_newlines(source_quote)
    nl_text = _normalize_newlines(section_text)
    idx = nl_text.find(nl_quote)
    if idx >= 0:
        # Check if unique
        second = nl_text.find(nl_quote, idx + 1)
        if second >= 0:
            return ("ambiguous", None, None)
        return ("normalised", idx, idx + len(nl_quote))

    # 4. Check for partial/substring match (ambiguous)
    # If quote is partially found in text
    words = norm_quote.split()
    if len(words) >= 5:
        found_words = sum(1 for w in words if w.lower() in norm_text.lower())
        if found_words / len(words) > 0.8:
            return ("ambiguous", None, None)

    return ("not_found", None, None)


def validate_schema(claim: dict[str, Any]) -> list[str]:
    """Validate claim schema. Returns list of error messages."""
    errors: list[str] = []

    required = [
        "claim_type",
        "source_quote",
        "faithful_paraphrase",
        "evidence_basis_description",
    ]
    for field in required:
        if field not in claim or not claim.get(field):
            errors.append(f"Missing required field: {field}")

    valid_types = {
        "background_statement",
        "method_statement",
        "reported_observation",
        "reported_result",
        "author_interpretation",
        "author_conclusion",
        "author_hypothesis",
        "author_limitation",
        "future_work",
    }
    claim_type = claim.get("claim_type", "")
    if claim_type and claim_type not in valid_types:
        errors.append(f"Invalid claim_type: {claim_type}")

    return errors


def check_leakage(claim: dict[str, Any]) -> list[str]:
    """Check that external data isolation is maintained. Returns errors."""
    errors: list[str] = []

    # Must not contain internal sample IDs or database references
    forbidden = [
        "internal_measurements",
        "internal_sample",
        "internal_db",
        "our_lab_id",
    ]
    for key, value in claim.items():
        if isinstance(value, str):
            for fb in forbidden:
                if fb in value.lower():
                    errors.append(
                        f"Forbidden internal reference '{fb}' in field '{key}'"
                    )

    return errors


def validate_claims(
    raw_claims: list[dict[str, Any]],
    sections: list[dict[str, Any]],
    pages: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Validate all raw claims.

    Returns (validated, failed_locator, invalid_schema).
    """
    validated: list[dict[str, Any]] = []
    failed_locator: list[dict[str, Any]] = []
    invalid_schema: list[dict[str, Any]] = []

    # Build text lookup by page
    text_by_page: dict[int, str] = {}
    for page_data in pages:
        text_by_page[page_data["page"]] = page_data.get("text", "")

    # Build all text concatenated (for section-level matching)
    all_section_text = "\n".join(s.get("text", "") for s in sections)

    for claim in raw_claims:
        claim_id = f"CLM-{len(validated) + len(failed_locator) + len(invalid_schema):06d}"

        # 1. Schema validation
        schema_errors = validate_schema(claim)
        if schema_errors:
            claim["_validation_errors"] = schema_errors
            claim["_claim_id"] = claim_id
            invalid_schema.append(claim)
            continue

        # 2. Quote matching
        source_quote = claim.get("source_quote", "")

        # Try matching against the section text for the claimed page
        locator = claim.get("locator_hint", {})
        claimed_page = locator.get("page")

        if claimed_page and claimed_page in text_by_page:
            page_text = text_by_page[claimed_page]
            match_status, start, end = match_quote(source_quote, page_text)
            if match_status in ("not_found", "ambiguous"):
                # Fall back to all sections
                match_status, start, end = match_quote(
                    source_quote, all_section_text
                )
        else:
            match_status, start, end = match_quote(
                source_quote, all_section_text
            )

        # 3. Classification
        if match_status in ("exact", "normalised"):
            # 4. Leakage check
            leakage_errors = check_leakage(claim)
            if leakage_errors:
                claim["_validation_errors"] = leakage_errors
                claim["_claim_id"] = claim_id
                claim["_quote_match_status"] = match_status
                failed_locator.append(claim)
                continue

            claim["_claim_id"] = claim_id
            claim["_quote_match_status"] = match_status
            claim["_quote_char_start"] = start
            claim["_quote_char_end"] = end
            claim["origin_scope"] = "external"
            claim["scientific_verification_status"] = "unverified"
            claim["record_review_status"] = "pending"
            validated.append(claim)
        else:
            claim["_claim_id"] = claim_id
            claim["_quote_match_status"] = match_status
            claim["_validation_error"] = f"Quote match: {match_status}"
            failed_locator.append(claim)

    return validated, failed_locator, invalid_schema
