"""LLM Provider abstraction for claim extraction.

Defines a protocol and provides two implementations:
- MockProvider: Returns fixed responses for testing (no API key needed).
- DeepSeekProvider: Calls the DeepSeek API with thinking mode support.
"""

import hashlib
import json
import os
import time
from dataclasses import dataclass, field
from typing import Any, Protocol

from evidence_agent.extraction.response_parser import parse_claim_response

# ── Data types ─────────────────────────────────────────

@dataclass
class ExtractionRequest:
    """Input for claim extraction."""

    task_description: str
    section_text: str
    section_heading: str | None = None
    page_start: int | None = None
    page_end: int | None = None
    section_type: str = "body"


@dataclass
class ExtractionResponse:
    """Output from claim extraction."""

    claims: list[dict[str, Any]] = field(default_factory=list)
    raw_response: str = ""
    model_name: str = ""
    prompt_version: str = ""
    input_hash: str = ""
    output_hash: str = ""
    error: str | None = None
    retries: int = 0


# ── Provider Protocol ──────────────────────────────────

class ClaimExtractionProvider(Protocol):
    """Protocol for claim extraction providers."""

    def extract_claims(self, request: ExtractionRequest) -> ExtractionResponse:
        ...

    @property
    def model_name(self) -> str:
        ...

    @property
    def prompt_version(self) -> str:
        ...


def _compute_hash(content: str) -> str:
    """Compute SHA-256 hash of a string."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


# ── Mock Provider ──────────────────────────────────────

class MockProvider:
    """Returns fixed, repeatable responses for testing.

    No API key required. Used by default in tests.
    """

    def __init__(self, fixed_claims: list[dict[str, Any]] | None = None) -> None:
        self._fixed_claims = fixed_claims or self._default_claims()

    @property
    def model_name(self) -> str:
        return "mock"

    @property
    def prompt_version(self) -> str:
        return "claim_extraction_v1"

    def extract_claims(self, request: ExtractionRequest) -> ExtractionResponse:
        input_content = json.dumps(
            {
                "task": request.task_description,
                "section": request.section_text[:200],
                "heading": request.section_heading,
            },
            ensure_ascii=False,
        )
        input_hash = _compute_hash(input_content)

        if len(request.section_text.strip()) < 20:
            return ExtractionResponse(
                claims=[],
                raw_response=json.dumps([]),
                model_name=self.model_name,
                prompt_version=self.prompt_version,
                input_hash=input_hash,
                output_hash=_compute_hash("[]"),
            )

        output = json.dumps(self._fixed_claims, ensure_ascii=False)
        return ExtractionResponse(
            claims=list(self._fixed_claims),
            raw_response=output,
            model_name=self.model_name,
            prompt_version=self.prompt_version,
            input_hash=input_hash,
            output_hash=_compute_hash(output),
        )

    @staticmethod
    def _default_claims() -> list[dict[str, Any]]:
        return [
            {
                "claim_type": "reported_result",
                "source_quote": "The solubility increased from 1.0 to 5.2 mg/mL.",
                "faithful_paraphrase": "溶解度从 1.0 增加到 5.2 mg/mL。",
                "evidence_basis_description": "基于 Figure 1 的相溶解度实验。",
                "scope_description": "在水溶液中 25°C 条件。",
                "author_hedging": None,
                "locator_hint": {
                    "page": 1,
                    "section_heading": "Results",
                    "figure_label": "Figure 1",
                    "table_label": None,
                },
                "entities": [],
            },
            {
                "claim_type": "author_interpretation",
                "source_quote": (
                    "This suggests that hydrogen bonding "
                    "plays a key role in the stabilization."
                ),
                "faithful_paraphrase": "作者认为氢键在稳定化中起关键作用。",
                "evidence_basis_description": "基于 FT-IR 和 NMR 数据推断。",
                "scope_description": None,
                "author_hedging": "suggests",
                "locator_hint": {
                    "page": 2,
                    "section_heading": "Discussion",
                    "figure_label": "Figure 3",
                    "table_label": None,
                },
                "entities": [],
            },
        ]


# ── DeepSeek Provider ──────────────────────────────────

class DeepSeekProvider:
    """Calls the DeepSeek API with thinking mode enabled.

    Requires EVIDENCE_AGENT_LLM_API_KEY environment variable.
    """

    def __init__(
        self,
        api_key: str | None = None,
        api_base: str | None = None,
        model: str | None = None,
        max_retries: int = 3,
    ) -> None:
        self._api_key = api_key or os.getenv("EVIDENCE_AGENT_LLM_API_KEY", "")
        self._api_base = (
            api_base
            or os.getenv("EVIDENCE_AGENT_LLM_API_BASE", "https://api.deepseek.com")
        )
        self._model: str = (
            model
            or os.getenv("EVIDENCE_AGENT_LLM_MODEL")
            or "deepseek-v4-pro"
        )
        self._max_retries = max_retries
        self._prompt_version = "claim_extraction_v1"

    @property
    def model_name(self) -> str:
        return self._model

    @property
    def prompt_version(self) -> str:
        return self._prompt_version

    def extract_claims(self, request: ExtractionRequest) -> ExtractionResponse:
        if not self._api_key:
            return ExtractionResponse(
                error="No API key configured. Set EVIDENCE_AGENT_LLM_API_KEY."
            )

        input_content = json.dumps(
            {
                "task": request.task_description,
                "section": request.section_text,
                "heading": request.section_heading,
                "page_range": f"{request.page_start}-{request.page_end}",
            },
            ensure_ascii=False,
        )
        input_hash = _compute_hash(input_content)

        last_error: str | None = None

        for attempt in range(1, self._max_retries + 1):
            try:
                raw = self._call_api(request)
                parsed = parse_claim_response(raw)
                output_hash = _compute_hash(raw)

                if parsed["status"] == "invalid_json":
                    if attempt < self._max_retries:
                        wait = 2**attempt
                        time.sleep(wait)
                        continue
                    return ExtractionResponse(
                        error=(
                            f"Invalid JSON after {self._max_retries} "
                            f"attempts: {parsed['errors']}"
                        ),
                        raw_response=raw,
                        model_name=self._model,
                        prompt_version=self._prompt_version,
                        input_hash=input_hash,
                        output_hash=output_hash,
                        retries=attempt,
                    )

                return ExtractionResponse(
                    claims=parsed["claims"],
                    raw_response=raw,
                    model_name=self._model,
                    prompt_version=self._prompt_version,
                    input_hash=input_hash,
                    output_hash=output_hash,
                    retries=attempt - 1,
                    error=(
                        parsed["errors"][0] if parsed["errors"] else None
                    ),
                )

            except Exception as e:
                last_error = str(e)
                if attempt < self._max_retries:
                    wait = 2**attempt
                    time.sleep(wait)

        return ExtractionResponse(
            error=last_error or "Unknown error",
            input_hash=input_hash,
            model_name=self._model,
            prompt_version=self._prompt_version,
            retries=self._max_retries,
        )

    def _call_api(self, request: ExtractionRequest) -> str:
        """Make the actual API call. Returns raw response text."""
        import urllib.request

        prompt = self._build_prompt(request)

        payload = json.dumps(
            {
                "model": self._model,
                "messages": [
                    {"role": "system", "content": self._get_system_prompt()},
                    {"role": "user", "content": prompt},
                ],
                "max_tokens": 8192,
                "response_format": {"type": "json_object"},
                "reasoning_effort": "max",
            }
        ).encode("utf-8")

        req = urllib.request.Request(
            f"{self._api_base}/v1/chat/completions",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self._api_key}",
            },
        )

        with urllib.request.urlopen(req, timeout=120) as resp:
            body: dict[str, Any] = json.loads(resp.read().decode("utf-8"))
            content: str = body["choices"][0]["message"]["content"]
            return content

    def _get_system_prompt(self) -> str:
        return (
            "You are a precise scientific literature extraction assistant. "
            "Extract claims exactly as stated by the authors. "
            "Preserve hedging language (suggests, may, possibly). "
            "Distinguish observations from interpretations. "
            "Always return valid JSON with a 'claims' array."
        )

    def _build_prompt(self, request: ExtractionRequest) -> str:
        return (
            f"Task: {request.task_description}\n\n"
            f"Section: {request.section_heading or 'Body'}\n"
            f"Pages: {request.page_start}-{request.page_end}\n\n"
            "Extract all author claims from the following text. "
            "For each claim, provide:\n"
            "- claim_type: one of [background_statement, method_statement, "
            "reported_observation, reported_result, author_interpretation, "
            "author_conclusion, author_hypothesis, author_limitation, future_work]\n"
            "- source_quote: exact text from the source\n"
            "- faithful_paraphrase: faithful restatement preserving hedging\n"
            "- evidence_basis_description: what experiments/figures support this\n"
            "- scope_description: conditions or limitations (null if not stated)\n"
            "- author_hedging: hedging words used (null if none)\n"
            "- locator_hint: {{page, section_heading, figure_label, table_label}}\n"
            "- entities: list of {{entity_type, display_name, role}}\n\n"
            f"Text:\n{request.section_text}\n\n"
            "Return a JSON object with a 'claims' array."
        )
