"""Review schemas."""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class ReviewDecision(StrEnum):
    APPROVE = "approve"
    APPROVE_WITH_EDITS = "approve_with_edits"
    REJECT = "reject"
    MARK_MISSING = "mark_missing"
    NEEDS_FOLLOWUP = "needs_followup"


class ReviewObjectType(StrEnum):
    CLAIM = "claim"
    SOURCE = "source"
    ENTITY_LINK = "entity_link"


class ReviewDecisionRecord(BaseModel):
    review_id: str
    object_type: ReviewObjectType
    object_id: str
    decision: ReviewDecision
    original_content_json: str
    edited_content_json: str | None = None
    reviewer: str
    review_reason: str | None = None
    reviewed_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())


class ClaimRevision(BaseModel):
    revision_id: str
    claim_id: str
    previous_content_json: str
    new_content_json: str
    changed_by: str
    change_reason: str
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
