# =============================================================================
# 이 파일의 책임: 결정사항·일정 제안 검토 API의 요청·응답 DTO를 정의한다.
# 다른 파일과의 관계: decision_schedule_router.py가 요청을 받고 review service가
#   ORM 모델을 이 DTO로 바꾼다. LLM 출력 DTO(extraction.py)와는 경계가 다르다.
# Spring 비교: @RequestBody + Bean Validation DTO와 조회 전용 Response DTO다.
# =============================================================================

from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, model_validator

DecisionStatus = Literal["DECIDED", "PENDING", "REVERSED"]
ScheduleKind = Literal["MILESTONE", "DEADLINE", "MEETING", "PERIOD"]
SuggestionDecision = Literal["PENDING", "APPROVED", "EDITED", "REJECTED"]


class SuggestionRow(BaseModel):
    """결정사항과 일정에 공통인 검토 정보."""

    id: int
    document_id: int | None
    filename: str | None
    confidence: Decimal | None
    reason: str
    decision: SuggestionDecision
    decided_by: int | None
    decided_at: datetime | None
    source_text_revision: int
    current_text_revision: int | None
    stale: bool


class DecisionRow(SuggestionRow):
    title: str
    content: str | None
    status: DecisionStatus
    superseded_by: int | None
    decided_on: date | None


class ScheduleItemRow(SuggestionRow):
    title: str
    kind: ScheduleKind
    starts_on: date | None
    ends_on: date | None


class DecisionListResponse(BaseModel):
    items: list[DecisionRow] = Field(default_factory=list)
    total: int
    returned: int
    truncated: bool
    limit: int
    included_decisions: list[SuggestionDecision] = Field(default_factory=list)


class ScheduleItemListResponse(BaseModel):
    items: list[ScheduleItemRow] = Field(default_factory=list)
    total: int
    returned: int
    truncated: bool
    limit: int
    included_decisions: list[SuggestionDecision] = Field(default_factory=list)


class DecisionUpdateRequest(BaseModel):
    """결정사항을 고쳐 `EDITED`로 승인하는 요청."""

    title: str | None = Field(default=None, min_length=1, max_length=300)
    content: str | None = None
    status: DecisionStatus | None = None
    decided_on: date | None = None

    @model_validator(mode="after")
    def require_change(self) -> "DecisionUpdateRequest":
        if not self.model_fields_set:
            raise ValueError("고칠 값을 하나 이상 보내야 합니다.")
        if "title" in self.model_fields_set and self.title is None:
            raise ValueError("제목은 비울 수 없습니다.")
        if "status" in self.model_fields_set and self.status is None:
            raise ValueError("결정 상태는 비울 수 없습니다.")
        return self


class ScheduleItemUpdateRequest(BaseModel):
    """일정·기한을 고쳐 `EDITED`로 승인하는 요청."""

    title: str | None = Field(default=None, min_length=1, max_length=300)
    kind: ScheduleKind | None = None
    starts_on: date | None = None
    ends_on: date | None = None

    @model_validator(mode="after")
    def validate_change(self) -> "ScheduleItemUpdateRequest":
        if not self.model_fields_set:
            raise ValueError("고칠 값을 하나 이상 보내야 합니다.")
        if "title" in self.model_fields_set and self.title is None:
            raise ValueError("제목은 비울 수 없습니다.")
        if "kind" in self.model_fields_set and self.kind is None:
            raise ValueError("일정 종류는 비울 수 없습니다.")
        if self.starts_on and self.ends_on and self.starts_on > self.ends_on:
            raise ValueError("시작일은 종료일보다 늦을 수 없습니다.")
        return self
