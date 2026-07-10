"""Stable ID generation for all entity types."""

import uuid
from datetime import datetime


def _short_uid() -> str:
    """Generate a short unique identifier (8 hex chars)."""
    return uuid.uuid4().hex[:8]


def generate_source_id() -> str:
    """Generate a source ID like SRC-a1b2c3d4."""
    return f"SRC-{_short_uid()}"


def generate_asset_id() -> str:
    """Generate an asset ID like AST-a1b2c3d4."""
    return f"AST-{_short_uid()}"


def generate_task_id() -> str:
    """Generate a task ID like TASK-a1b2c3d4."""
    return f"TASK-{_short_uid()}"


def generate_claim_id() -> str:
    """Generate a claim ID like CLM-a1b2c3d4."""
    return f"CLM-{_short_uid()}"


def generate_locator_id() -> str:
    """Generate a locator ID like LOC-a1b2c3d4."""
    return f"LOC-{_short_uid()}"


def generate_section_id() -> str:
    """Generate a section ID like SEC-a1b2c3d4."""
    return f"SEC-{_short_uid()}"


def generate_run_id() -> str:
    """Generate a run ID like RUN-a1b2c3d4."""
    return f"RUN-{_short_uid()}"


def generate_review_id() -> str:
    """Generate a review ID like REV-a1b2c3d4."""
    return f"REV-{_short_uid()}"


def generate_revision_id() -> str:
    """Generate a revision ID like RVN-a1b2c3d4."""
    return f"RVN-{_short_uid()}"


def generate_entity_id() -> str:
    """Generate an entity ID like ENT-a1b2c3d4."""
    return f"ENT-{_short_uid()}"


def now_iso() -> str:
    """Current UTC time as ISO 8601 string."""
    return datetime.utcnow().isoformat()
