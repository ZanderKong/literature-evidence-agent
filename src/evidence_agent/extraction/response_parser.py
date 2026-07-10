"""Parse LLM responses into structured claims."""

import json
import re
from typing import Any

from evidence_agent.schemas.claim import ClaimType


def _strip_markdown_fence(text: str) -> str:
    """Remove markdown JSON fences like ```json ... ```."""
    text = text.strip()
    # Remove ```json or ``` block
    fence_pattern = re.compile(r"^```(?:json)?\s*\n?(.*?)\n?```$", re.DOTALL)
    match = fence_pattern.match(text)
    if match:
        return match.group(1).strip()
    return text


def _try_repair_json(text: str) -> str:
    """Attempt simple JSON structural repairs. Returns repaired text or original."""
    # Count braces
    text = text.strip()
    open_braces = text.count("{")
    close_braces = text.count("}")

    if open_braces > close_braces:
        text += "}" * (open_braces - close_braces)
    elif close_braces > open_braces:
        # Try to fix by trimming
        pass

    return text


def parse_claim_response(raw_response: str) -> dict[str, Any]:
    """Parse a raw LLM response into structured claim data.

    Returns dict with:
        - status: 'ok' | 'invalid_json' | 'invalid_schema' | 'empty'
        - claims: list of validated claim dicts
        - errors: list of error messages
        - raw: the original raw response
    """
    result: dict[str, Any] = {
        "status": "ok",
        "claims": [],
        "errors": [],
        "raw": raw_response,
    }

    if not raw_response or not raw_response.strip():
        result["status"] = "empty"
        result["errors"].append("Empty response from model")
        return result

    # 1. Strip markdown fence
    cleaned = _strip_markdown_fence(raw_response)

    # 2. Parse JSON
    data: Any
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        # Try repair once
        cleaned = _try_repair_json(cleaned)
        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError as e:
            result["status"] = "invalid_json"
            result["errors"].append(f"JSON parse error: {e}")
            return result

    # 3. Extract claims array
    claims_raw: list[Any] = []
    if isinstance(data, dict):
        claims_raw = data.get("claims", [])
    elif isinstance(data, list):
        # Model returned top-level array
        claims_raw = data
    else:
        result["status"] = "invalid_json"
        result["errors"].append(
            f"Expected JSON object or array, got {type(data).__name__}"
        )
        return result

    if not isinstance(claims_raw, list):
        result["status"] = "invalid_json"
        result["errors"].append("'claims' field is not an array")
        return result

    # 4. Validate each claim
    valid_types = set(ClaimType.__members__.values())
    for i, claim_data in enumerate(claims_raw):
        if not isinstance(claim_data, dict):
            result["errors"].append(
                f"Claim {i}: expected object, got {type(claim_data).__name__}"
            )
            continue

        # Basic field validation
        errors: list[str] = []

        claim_type = claim_data.get("claim_type", "")
        if not claim_type:
            errors.append("Missing claim_type")
        elif claim_type not in valid_types:
            errors.append(f"Invalid claim_type: {claim_type}")

        source_quote = claim_data.get("source_quote", "")
        if not source_quote or not source_quote.strip():
            errors.append("Missing or empty source_quote")

        paraphrase = claim_data.get("faithful_paraphrase", "")
        if not paraphrase or not paraphrase.strip():
            errors.append("Missing or empty faithful_paraphrase")

        basis = claim_data.get("evidence_basis_description", "")
        if not basis or not basis.strip():
            errors.append("Missing or empty evidence_basis_description")

        if errors:
            result["errors"].append(
                f"Claim {i} ({claim_type}): {'; '.join(errors)}"
            )
            continue

        claim_data["_parsed_index"] = i
        claim_data["_claim_type_valid"] = True
        result["claims"].append(claim_data)

    if not result["claims"]:
        if not result["errors"]:
            result["status"] = "empty"
            result["errors"].append("Response contained no valid claims")
        else:
            result["status"] = "invalid_schema"

    return result
