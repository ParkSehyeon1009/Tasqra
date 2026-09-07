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
    # 🔑 **프롬프트는 200자, 여기는 250자다. 일부러 다르다** (2026-09-03).
    #   맞추려고 하지 마시라. prompts.SUMMARY_RULES 의 긴 주석에 근거가 있다.
    #
    #   요약하면 — 배포 모델(sum-v6, q8_0)을 실제 문서 25건으로 재니 중앙 175자에
    #   꼬리가 242자였다. 200 을 넘긴 8건은 환각 0 · 다국어 0 으로 내용이 정확해서,
    #   상한 때문에만 버려지고 있었다(통과 68% -> 100%). 그래서 검증은 250 으로 푼다.
    #   반대로 프롬프트의 숫자를 250 으로 올리면 모델이 그만큼 늘려 써서
    #   275자까지 나온다(실측). 그래서 지시는 200 으로 좁게 유지한다.
    #
    #   GroundedSummaryOutput 도 이것을 상속하므로 함께 따라간다.
    summary: NonEmpty = Field(max_length=250)


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
# 기능별 요약 — 수행할 과업. 한 항목이 태스크 제안 하나가 된다.
#
# 결정사항과 달리 DTO 를 빌려오지 않고 여기서 정의한다. 아직 제안 테이블
# (task_suggestions)이 없어 대응하는 DTO 가 없기 때문이다. 테이블을 만들 때
# schemas/ 쪽으로 옮기고 여기서는 그것을 쓰도록 바꿀 것.
#
# 🔑 **프롬프트는 30자·150자, 여기는 40자·200자다. 일부러 다르다.**
#   SummaryOutput 의 200/250 과 **같은 이유이고 같은 방향**이다(위 주석 참고).
#   맞추려고 하지 마시라.
#
# ⚠️ **max_length 는 모델을 짧게 쓰게 하지 않는다. 거기서 자른다.**
#   결과는 유효한 JSON 이고 이 검증도 통과한다 — 아무도 못 잡는다.
#
#   2026-09-04 실측(실제 문서 22건, 청크 경로, 항목 194개):
#       name    30자 정확히  3개
#       summary 150자 정확히 10개
#   그 13개를 열어보니 전부 **말 중간에서 끊겨** 있었다:
#       "AI 엣지 센서 기반 비식별 행동 분석 및 아나몰픽 3"
#       "...체험자 안전 활동 통계를 조회하며 존별로"
#   30자·150자로는 도시재생·전사체 같은 문서의 과업 이름을 담지 못한다.
#
#   반대로 **프롬프트의 숫자를 올리면 안 된다.** 요약에서 실측했다 — 모델은
#   들은 숫자만큼 늘려 쓴다(200→250 으로 바꾸니 최대 242자가 275자가 됐다).
#   게다가 이 모델은 「30자 이내」·「150자 이내」를 보고 학습했으므로, 숫자를
#   바꾸면 학습·서비스 불일치를 새로 만드는 셈이다.
#
#   즉 **좁게 시키고 넓게 검증한다.**
#
# ⚠️ 상한에 **딱 맞는** 값은 여전히 잘린 것으로 의심해야 한다. 40/200 으로
#   올려도 더 긴 것이 있으면 거기서 끊긴다 — features_analyzer 가 그 개수를
#   at_length_cap 으로 센다. 그 값이 크면 상한을 다시 볼 것.
#
# ⚠️ max_length 12(항목 수)는 **프롬프트와 같게 둔다.** 이쪽은 잘림이 아니라
#   「몇 개까지 뽑을까」라 성격이 다르고, 전체 상한은 AI_MAX_FEATURES 가 건다.
# =============================================================================

class Feature(StrictOutput):
    name: NonEmpty = Field(max_length=40)
    summary: NonEmpty = Field(max_length=200)


class FeaturesOutput(StrictOutput):
    # 한 구간에서 뽑는 개수. 전체 상한은 분석기가 따로 건다 — 구간이 20개면
    # 이 값만으로는 240개가 될 수 있기 때문이다.
    features: list[Feature] = Field(max_length=12)


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
