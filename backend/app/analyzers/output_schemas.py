"""JSON 형식 외에 값의 타입·길이·허용 코드를 검증한다."""
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

NonEmpty = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
CategoryCode = Literal["RFP", "PROPOSAL", "COST_SHEET", "CONTRACT", "CONTRACT_CHANGE", "REPORT", "MEETING_NOTES", "ETC"]


class StrictOutput(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")


class SummaryOutput(StrictOutput):
    summary: NonEmpty = Field(max_length=300)


class OverviewOutput(StrictOutput):
    summary: NonEmpty = Field(max_length=250)


class CategoryOutput(StrictOutput):
    category: CategoryCode
    reason: NonEmpty = Field(max_length=500)


class Fact(StrictOutput):
    quote: NonEmpty = Field(max_length=240)
    status: Literal["확정", "제안", "취소", "불명"]


class FactsOutput(StrictOutput):
    facts: list[Fact] = Field(max_length=6)


class SelectionOutput(StrictOutput):
    selected_ids: list[NonEmpty] = Field(min_length=1)


class GroundedSummaryOutput(SummaryOutput):
    evidence_ids: list[NonEmpty] = Field(min_length=1)
