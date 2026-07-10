"""Claim schemas — the core data model."""

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, ValidationInfo, field_validator


class ClaimType(StrEnum):
    BACKGROUND = "background_statement"
    METHOD = "method_statement"
    OBSERVATION = "reported_observation"
    RESULT = "reported_result"
    INTERPRETATION = "author_interpretation"
    CONCLUSION = "author_conclusion"
    HYPOTHESIS = "author_hypothesis"
    LIMITATION = "author_limitation"
    FUTURE_WORK = "future_work"


class RecordReviewStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    APPROVED_WITH_EDITS = "approved_with_edits"
    REJECTED = "rejected"


class QuoteMatchStatus(StrEnum):
    EXACT = "exact"
    NORMALISED = "normalised"
    AMBIGUOUS = "ambiguous"
    NOT_FOUND = "not_found"


class LocatorConfidence(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class ScientificVerificationStatus(StrEnum):
    UNVERIFIED = "unverified"
    INTERNALLY_REPRODUCED = "internally_reproduced"
    INDEPENDENTLY_CONFIRMED = "independently_confirmed"
    CONTRADICTED = "contradicted"


class ClaimLocator(BaseModel):
    locator_id: str
    claim_id: str
    section_id: str | None = None
    page: int | None = None
    paragraph_index: int | None = None
    figure_label: str | None = None
    table_label: str | None = None
    supplementary_label: str | None = None
    character_start: int | None = None
    character_end: int | None = None
    locator_confidence: LocatorConfidence

    @field_validator("character_end")
    @classmethod
    def char_end_ge_start(
        cls, v: int | None, info: ValidationInfo
    ) -> int | None:
        char_start: Any = info.data.get("character_start")
        if v is not None and char_start is not None and v < char_start:
            raise ValueError("character_end must be >= character_start")
        return v


class SourceClaim(BaseModel):
    claim_id: str
    source_id: str
    task_id: str | None = None
    claim_type: ClaimType
    source_quote: str
    faithful_paraphrase: str
    evidence_basis_description: str
    scope_description: str | None = None
    author_hedging: str | None = None
    origin_scope: str = "external"
    record_review_status: RecordReviewStatus = RecordReviewStatus.PENDING
    scientific_verification_status: ScientificVerificationStatus = (
        ScientificVerificationStatus.UNVERIFIED
    )
    quote_match_status: QuoteMatchStatus = QuoteMatchStatus.NOT_FOUND
    created_by_run_id: str
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())

    @field_validator("source_quote")
    @classmethod
    def quote_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("source_quote must not be empty")
        return v

    @field_validator("faithful_paraphrase")
    @classmethod
    def paraphrase_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("faithful_paraphrase must not be empty")
        return v

    @field_validator("origin_scope")
    @classmethod
    def origin_must_be_external(cls, v: str) -> str:
        if v != "external":
            raise ValueError("origin_scope must be 'external'")
        return v

    @field_validator("scientific_verification_status")
    @classmethod
    def only_unverified_in_round1(
        cls, v: ScientificVerificationStatus
    ) -> ScientificVerificationStatus:
        if v != ScientificVerificationStatus.UNVERIFIED:
            raise ValueError(
                "scientific_verification_status must be 'unverified' in Round 1"
            )
        return v


class EntityType(StrEnum):
    MATERIAL = "material"
    COMPOUND = "compound"
    PRODUCT = "product"
    METHOD = "method"
    INSTRUMENT = "instrument"
    PROPERTY = "property"
    PROCESS = "process"
    COMPANY = "company"
    AUTHOR = "author"
    INSTITUTION = "institution"
    APPLICATION = "application"


class EntityRole(StrEnum):
    SUBJECT = "subject"
    OBJECT = "object"
    MATERIAL = "material"
    METHOD = "method"
    PROPERTY = "property"
    CONDITION = "condition"
    APPLICATION = "application"


class Entity(BaseModel):
    entity_id: str
    entity_type: EntityType
    canonical_name: str
    display_name: str
    normalised_name: str
    aliases_json: str = "[]"
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())


class ClaimEntityLink(BaseModel):
    claim_id: str
    entity_id: str
    role: EntityRole
