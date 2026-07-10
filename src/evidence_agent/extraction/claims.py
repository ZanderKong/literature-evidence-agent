"""Claim extraction from parsed document sections."""

import json
import re
from pathlib import Path
from typing import Any

from evidence_agent.extraction.provider import (
    ClaimExtractionProvider,
    ExtractionRequest,
    MockProvider,
)


def _filter_references(text: str) -> str:
    """Remove reference list content (rough heuristic)."""
    # Remove lines that look like reference entries: [1], [1-3], etc.
    ref_pattern = re.compile(r"^\s*\[\d+[\d,\-\s]*\].*$", re.MULTILINE)
    return ref_pattern.sub("", text)


def _filter_headers_footers(text: str) -> str:
    """Remove common header/footer patterns."""
    # Remove very short lines that repeat across pages
    lines = text.split("\n")
    filtered = [line for line in lines if len(line.strip()) > 3]
    return "\n".join(filtered)


def _chunk_section(
    section: dict[str, Any], max_chars: int = 3000
) -> list[dict[str, Any]]:
    """Split a long section into manageable chunks with overlap."""
    text = section.get("text", "")
    if len(text) <= max_chars:
        return [section]

    chunks: list[dict[str, Any]] = []
    paragraphs = text.split("\n\n")
    current_chunk = ""
    page_start = section.get("page_start")
    page_end = section.get("page_end")

    for para in paragraphs:
        if len(current_chunk) + len(para) > max_chars and current_chunk:
            chunks.append(
                {
                    "section_type": section.get("section_type", "body"),
                    "heading": section.get("heading"),
                    "page_start": page_start,
                    "page_end": page_end,
                    "text": current_chunk.strip(),
                }
            )
            current_chunk = para
        else:
            current_chunk += "\n\n" + para if current_chunk else para

    if current_chunk.strip():
        chunks.append(
            {
                "section_type": section.get("section_type", "body"),
                "heading": section.get("heading"),
                "page_start": page_start,
                "page_end": page_end,
                "text": current_chunk.strip(),
            }
        )

    return chunks


def extract_claims_from_source(
    sections: list[dict[str, Any]],
    task_description: str = "Extract all author claims",
    analysis_depth: str = "source_complete",
    provider: ClaimExtractionProvider | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Extract claims from parsed sections.

    Args:
        sections: List of parsed section dicts.
        task_description: What claims to extract.
        analysis_depth: 'task_focused' or 'source_complete'.
        provider: LLM provider (default MockProvider).

    Returns:
        (raw_claims, extraction_report)
    """
    if provider is None:
        provider = MockProvider()

    all_claims: list[dict[str, Any]] = []
    blocks_processed = 0
    blocks_failed = 0

    for section in sections:
        # Skip references
        if section.get("section_type") == "references":
            continue

        # Preprocess text
        text = section.get("text", "")
        text = _filter_references(text)
        text = _filter_headers_footers(text)

        if len(text.strip()) < 50:
            continue

        # Chunk long sections
        chunks = _chunk_section({**section, "text": text})

        for chunk in chunks:
            blocks_processed += 1

            request = ExtractionRequest(
                task_description=task_description,
                section_text=chunk["text"],
                section_heading=chunk.get("heading"),
                page_start=chunk.get("page_start"),
                page_end=chunk.get("page_end"),
                section_type=chunk.get("section_type", "body"),
            )

            response = provider.extract_claims(request)

            if response.error:
                blocks_failed += 1
                continue

            # Tag claims with metadata
            for claim in response.claims:
                claim["_block_section_type"] = chunk.get("section_type")
                claim["_block_page_start"] = chunk.get("page_start")
                claim["_block_page_end"] = chunk.get("page_end")
                claim["_block_heading"] = chunk.get("heading")
                claim["_model_name"] = response.model_name
                claim["_prompt_version"] = response.prompt_version

            all_claims.extend(response.claims)

    # Deduplicate exact quote matches within the same source
    seen_quotes: set[str] = set()
    deduped: list[dict[str, Any]] = []
    for claim in all_claims:
        quote = claim.get("source_quote", "").strip()
        if quote and quote not in seen_quotes:
            seen_quotes.add(quote)
            deduped.append(claim)

    report: dict[str, Any] = {
        "blocks_processed": blocks_processed,
        "blocks_failed": blocks_failed,
        "candidate_claims": len(all_claims),
        "deduplicated_claims": len(deduped),
        "analysis_depth": analysis_depth,
    }

    return deduped, report


def save_raw_claims(
    claims: list[dict[str, Any]], output_path: Path
) -> None:
    """Save raw claims to JSONL file."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        for claim in claims:
            f.write(json.dumps(claim, ensure_ascii=False) + "\n")
