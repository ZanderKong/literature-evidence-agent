"""Stable ID generation for all entity types.

Uses full UUID4 hex (32 chars) for collision resistance.
Prefixes:
  SRC-  Source
  AST-  SourceAsset
  TASK- ResearchTask
  RUN-  ProcessingRun
  CLM-  SourceClaim
  LOC-  ClaimLocator
  SEC-  Section
  REV-  ReviewDecision
  RVN-  ClaimRevision
  RVR-  ReviewRow
  RVB-  ReviewBatch
  ENT-  Entity
"""

import uuid
from collections.abc import Callable
from datetime import UTC, datetime


def _full_uid() -> str:
    """Generate a full UUID4 hex string (32 chars, no dashes)."""
    return uuid.uuid4().hex


# Allow injectable ID factories for testing
_id_factory: Callable[[], str] | None = None


def get_id_factory() -> Callable[[], str]:
    """Get the current ID factory. For testing, set_id_factory can inject."""
    if _id_factory is not None:
        return _id_factory
    return _full_uid


def set_id_factory(factory: Callable[[], str] | None) -> None:
    """Inject a deterministic ID factory (for testing)."""
    global _id_factory
    _id_factory = factory


def generate_source_id() -> str:
    """Generate a source ID like SRC-<32 hex>."""
    return f"SRC-{get_id_factory()()}"


def generate_asset_id() -> str:
    """Generate an asset ID like AST-<32 hex>."""
    return f"AST-{get_id_factory()()}"


def generate_task_id() -> str:
    """Generate a task ID like TASK-<32 hex>."""
    return f"TASK-{get_id_factory()()}"


def generate_claim_id() -> str:
    """Generate a claim ID like CLM-<32 hex>."""
    return f"CLM-{get_id_factory()()}"


def generate_locator_id() -> str:
    """Generate a locator ID like LOC-<32 hex>."""
    return f"LOC-{get_id_factory()()}"


def generate_section_id() -> str:
    """Generate a section ID like SEC-<32 hex>."""
    return f"SEC-{get_id_factory()()}"


def generate_run_id() -> str:
    """Generate a run ID like RUN-<32 hex>."""
    return f"RUN-{get_id_factory()()}"


def generate_review_id() -> str:
    """Generate a review ID like REV-<32 hex>."""
    return f"REV-{get_id_factory()()}"


def generate_revision_id() -> str:
    """Generate a revision ID like RVN-<32 hex>."""
    return f"RVN-{get_id_factory()()}"


def generate_batch_id() -> str:
    """Generate a review batch ID like RVB-<32 hex>."""
    return f"RVB-{get_id_factory()()}"


def generate_row_id() -> str:
    """Generate a review row ID like RVR-<32 hex>."""
    return f"RVR-{get_id_factory()()}"


def generate_entity_id() -> str:
    """Generate an entity ID like ENT-<32 hex>."""
    return f"ENT-{get_id_factory()()}"


def now_iso() -> str:
    """Current UTC time as ISO 8601 string."""
    return datetime.now(UTC).isoformat()
