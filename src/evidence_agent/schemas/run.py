"""Processing run schemas."""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class RunStatus(StrEnum):
    STARTED = "started"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ProcessingRun(BaseModel):
    run_id: str
    task_id: str | None = None
    source_id: str | None = None
    module_name: str
    model_name: str | None = None
    model_mode: str | None = None
    prompt_version: str | None = None
    parser_name: str | None = None
    parser_version: str | None = None
    code_commit: str | None = None
    input_hash: str
    output_hash: str | None = None
    status: RunStatus
    error_type: str | None = None
    error_message: str | None = None
    started_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    completed_at: str | None = None
