from datetime import date, datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class TaskStatus(str, Enum):
    TODO = "TODO"
    IN_PROGRESS = "IN_PROGRESS"
    DONE = "DONE"


class TaskType(str, Enum):
    DEVELOPMENT = "DEVELOPMENT"
    DESIGN = "DESIGN"
    INFRA = "INFRA"
    DOCUMENT = "DOCUMENT"
    OTHER = "OTHER"


class TaskCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    description: str | None = None
    type: TaskType = TaskType.OTHER
    assignee_id: int | None = None
    due_on: date | None = None


class TaskUpdateRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    description: str | None = None
    type: TaskType | None = None
    status: TaskStatus | None = None
    assignee_id: int | None = None
    due_on: date | None = None

    @model_validator(mode="after")
    def require_change(self):
        if not self.model_fields_set:
            raise ValueError("변경할 태스크 정보가 필요합니다.")
        return self


class TaskAssigneeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str


class TaskResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    title: str
    description: str | None
    type: str
    status: str
    assignee: TaskAssigneeResponse | None
    due_on: date | None
    completed_at: datetime | None
    created_by: int | None
    created_at: datetime
    updated_at: datetime
