"""Research task schemas."""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class TaskMode(StrEnum):
    ANALYSE_UPLOADED = "analyse_uploaded"
    SOURCE_COMPLETE_ANALYSIS = "source_complete_analysis"
    EVIDENCE_QUERY = "evidence_query"


class AnalysisDepth(StrEnum):
    TASK_FOCUSED = "task_focused"
    SOURCE_COMPLETE = "source_complete"


class TaskStatus(StrEnum):
    CREATED = "created"
    RUNNING = "running"
    REVIEW = "review"
    COMPLETED = "completed"
    FAILED = "failed"


class ResearchTask(BaseModel):
    task_id: str
    title: str
    user_request: str
    research_background: str | None = None
    task_mode: TaskMode
    analysis_depth: AnalysisDepth
    status: TaskStatus = TaskStatus.CREATED
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
