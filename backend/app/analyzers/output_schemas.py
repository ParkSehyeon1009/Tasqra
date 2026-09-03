"""JSON 형식 외에 값의 타입·길이·허용 코드를 검증한다."""
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.schemas.extraction import DecisionExtraction, ScheduleKind

NonEmpty = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
# ⚠️ models/enums.py 의 DocumentType 은 9종이다. 여기는 **모델이 고를 수 있는
#   값**이라 더 좁다(BILLING·COST_SHEET 제외). prompts.CATEGORY_DESCRIPTIONS 의
#   주석 참고 — enum 이 프롬프트의 상위집합인 구조는 의도된 것이다.
CategoryCode = Literal["RFP", "PROPOSAL", "CONTRACT", "CONTRACT_CHANGE", "REPORT", "MEETING_NOTES", "ETC"]


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


# =============================================================================
# 결정사항 · 일정 추출
#
# 항목 자체는 schemas/extraction.py 의 DTO 를 **그대로 쓴다.** 날짜 순서 검증
# (starts_on <= ends_on)과 confidence 범위가 거기 있고, DecisionScheduleWriter 가
# 받는 타입도 그것이다. 여기서 다시 정의하면 두 벌이 되어 갈라진다.
#
# ⚠️ 감싸는 객체가 따로 필요한 이유: DTO 쪽 List 모델은 최상위가 **배열**인데
#   response_format 은 객체를 요구한다(json_object 는 배열 루트를 거절하고,
#   strict json_schema 도 객체 루트를 전제한다). FactsOutput 과 같은 모양이다.
#
# 한 구간에서 뽑는 개수를 제한한다. 상한이 없으면 모델이 문장마다 항목을 만들어
# 목록이 원문만큼 길어진다.
# =============================================================================

class DecisionsOutput(StrictOutput):
    decisions: list[DecisionExtraction] = Field(max_length=8)


# =============================================================================
# 일정 라벨링 — 모델은 날짜를 **쓰지 않고 고른다**
#
# 3B 모델은 날짜를 제목에 적고 날짜 필드를 비워둔다(실측 0/4, 0/3). 그래서
# 날짜 찾기는 date_finder.py 가 정규식으로 하고, 모델에게는 그 목록에서
# **id 로 고르게** 한다. GroundedSummaryOutput 의 evidence_ids 와 같은 방식이다.
#
# 이렇게 하면 모델이 없는 날짜를 만들 수 없다 — 고를 수 있는 것이 목록뿐이다.
# =============================================================================

class DatedItem(StrictOutput):
    # 하나면 그 날짜 자체, 둘이면 시작과 끝이다(PERIOD).
    date_ids: list[NonEmpty] = Field(min_length=1, max_length=2)
    title: NonEmpty = Field(max_length=300)
    kind: ScheduleKind
    confidence: float | None = Field(default=None, ge=0, le=1)
    reason: NonEmpty = Field(max_length=300)


class DatedItemsOutput(StrictOutput):
    items: list[DatedItem] = Field(max_length=20)
