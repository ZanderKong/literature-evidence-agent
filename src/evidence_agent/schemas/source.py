"""Source schemas."""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field, field_validator


class SourceType(StrEnum):
    JOURNAL_ARTICLE = "journal_article"
    PREPRINT = "preprint"
    CONFERENCE_PAPER = "conference_paper"
    TECHNICAL_REPORT = "technical_report"
    PRODUCT_DOCUMENTATION = "product_documentation"
    OTHER = "other"


class ScientificVerificationStatus(StrEnum):
    UNVERIFIED = "unverified"
    INTERNALLY_REPRODUCED = "internally_reproduced"
    INDEPENDENTLY_CONFIRMED = "independently_confirmed"
    CONTRADICTED = "contradicted"


class AssetType(StrEnum):
    MAIN_DOCUMENT = "main_document"
    SUPPLEMENTARY = "supplementary"
    ATTACHMENT = "attachment"


class Source(BaseModel):
    source_id: str
    source_type: SourceType
    title: str | None = None
    authors_json: str = "[]"
    organisation: str | None = None
    publication_date: str | None = None
    doi: str | None = None
    language: str | None = None
    version_label: str | None = None
    original_file_sha256: str
    origin_scope: str = "external"
    scientific_verification_status: ScientificVerificationStatus = (
        ScientificVerificationStatus.UNVERIFIED
    )
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())

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


class SourceAsset(BaseModel):
    asset_id: str
    source_id: str
    asset_type: AssetType
    relative_path: str
    mime_type: str
    sha256: str
    file_size: int
    acquired_from: str | None = None
    acquired_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())

    @field_validator("file_size")
    @classmethod
    def file_size_non_negative(cls, v: int) -> int:
        if v < 0:
            raise ValueError("file_size must be >= 0")
        return v
