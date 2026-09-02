from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field


class TaskSuggestionRow(BaseModel):
    id: int
    document_id: int | None
    title: str
    description: str | None
    due_on: date | None
    actor: str | None
    evidence_text: str
    confidence: Decimal | None
    quality_score: Decimal
    reason: str
    decision: Literal["PENDING", "APPROVED", "EDITED", "REJECTED"]
    decided_by: int | None
    decided_at: datetime | None
    created_task_id: int | None
    source_text_revision: int


class TaskSuggestionListResponse(BaseModel):
    items: list[TaskSuggestionRow]
    total: int


class TaskSuggestionUpdateRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    description: str | None = None
    due_on: date | None = None
    assignee_id: int | None = None
