# ① 책임: LLM이 반환한 결정사항·일정/기한 JSON의 구조와 값 범위를 검증한다.
# ② 관계: analyzers/extraction_parser.py가 이 DTO를 사용하며, DB 저장·승인 상태는 다루지 않는다.
# ③ Spring 비교: Pydantic DTO는 Jackson 역직렬화 뒤 Bean Validation을 적용하는 Request/Response DTO다.

from datetime import date, time
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, RootModel, model_validator


class DecisionStatus(str, Enum):
    """결정 자체의 상태. AI 제안 승인 상태인 Decision.decision과 별개다."""

    DECIDED = "DECIDED"
    PENDING = "PENDING"
    REVERSED = "REVERSED"


class ScheduleKind(str, Enum):
    """schedule_items.kind DB CHECK 제약과 같은 일정 종류다."""

    MILESTONE = "MILESTONE"
    DEADLINE = "DEADLINE"
    MEETING = "MEETING"
    PERIOD = "PERIOD"


class DecisionExtraction(BaseModel):
    """문서에서 추출한 결정사항 한 건이다."""

    model_config = ConfigDict(extra="forbid", strict=True)

    title: str = Field(min_length=1, max_length=300)
    content: str | None = None
    evidence_text: str | None = None
    status: DecisionStatus
    decision_type: str | None = Field(default=None, max_length=40)
    decided_on: date | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)
    reason: str = Field(min_length=1)


class ScheduleItemExtraction(BaseModel):
    """문서에서 추출한 일정 또는 기한 한 건이다."""

    model_config = ConfigDict(extra="forbid", strict=True)

    title: str = Field(min_length=1, max_length=300)
    evidence_text: str | None = None
    kind: ScheduleKind
    starts_on: date | None = None
    ends_on: date | None = None
    starts_time: time | None = None
    ends_time: time | None = None
    relative_expression: str | None = Field(default=None, max_length=300)
    temporal_type: str | None = Field(default=None, max_length=40)
    precision: str | None = Field(default=None, max_length=20)
    anchor_event: str | None = Field(default=None, max_length=120)
    calendar_rule: str | None = Field(default=None, max_length=30)
    condition: str | None = Field(default=None, max_length=500)
    tentative: bool = False
    confidence: float | None = Field(default=None, ge=0, le=1)
    reason: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_date_order(self) -> "ScheduleItemExtraction":
        if (
            self.starts_on is not None
            and self.ends_on is not None
            and self.starts_on > self.ends_on
        ):
            raise ValueError("starts_on must be on or before ends_on")
        return self


class DecisionExtractionList(RootModel[list[DecisionExtraction]]):
    """결정사항 JSON 최상위가 배열임을 검증한다."""


class ScheduleItemExtractionList(RootModel[list[ScheduleItemExtraction]]):
    """일정/기한 JSON 최상위가 배열임을 검증한다."""


class TaskSuggestionExtraction(BaseModel):
    """원문 행동 후보에 묶인 실행 가능한 태스크 제안."""

    model_config = ConfigDict(extra="forbid", strict=True)

    title: str = Field(min_length=1, max_length=300)
    description: str | None = None
    due_on: date | None = None
    actor: str | None = Field(default=None, max_length=160)
    actor_scope: str | None = Field(default=None, max_length=30)
    statement_type: str = Field(default="OBLIGATION", max_length=40)
    task_kind: str | None = Field(default=None, max_length=40)
    modality: str | None = Field(default=None, max_length=30)
    recipient: str | None = Field(default=None, max_length=160)
    relative_expression: str | None = Field(default=None, max_length=300)
    condition: str | None = Field(default=None, max_length=500)
    evidence_text: str = Field(min_length=1)
    confidence: float | None = Field(default=None, ge=0, le=1)
    quality_score: float = Field(ge=0, le=1)
    reason: str = Field(min_length=1)


class TaskSuggestionExtractionList(RootModel[list[TaskSuggestionExtraction]]):
    pass
