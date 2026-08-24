# =============================================================================
# 이 파일의 책임: 산출물 API 의 요청·응답 스키마를 정의한다. 지금은 생성 대상
#   미리보기(DLV-001-2)만 있다.
#
# 다른 파일과의 관계: api/routes/deliverable_router.py 가 이 스키마로 주고받고
#   services/deliverable_service.py 가 채운다. 필드명은 snake_case 그대로 둔다.
#
# Spring 비교: @RestController 의 Request/Response DTO 다.
#
# 완료 판정이 스키마 모양을 정했다
#   DLV-001-2: "**LLM 호출 전에 건수가 보이고** 대상이 없으면 생성이 방지된다"
#   그래서 응답이 건수와 **can_generate** 를 함께 담는다. 화면이 건수를 보고
#   스스로 판단하게 두면 판단 규칙이 두 곳에 생긴다.
#
#   DLV-001-1: "형식을 고르지 않으면 생성 버튼이 비활성화된다"
#   미리보기는 형식과 무관하다 — 형식은 만들 때 필요하다. 그래서 미리보기 요청에
#   format 을 받지 않는다.
# =============================================================================

from datetime import date, datetime

from pydantic import BaseModel, Field

__all__ = [
    "DELIVERABLE_FORMATS",
    "DELIVERABLE_KIND_LABELS",
    "DELIVERABLE_KINDS",
    "PERIOD_REQUIRED_KINDS",
    "SUPPORTED_DELIVERABLE_FORMATS",
    "DeliverableCreateRequest",
    "DeliverablePreviewResponse",
    "DeliverableResponse",
    "PreviewCounts",
]

# models/deliverable.py 의 _KIND 와 같아야 한다. 리비전 0007 의 CHECK 가 근거다.
DELIVERABLE_KINDS = ("WEEKLY_REPORT", "DECISION_LOG", "MEETING_AGENDA", "PROJECT_STATUS")
# 기간이 필수인 유형. DB CHECK(ck_deliverable_period_required)와 같은 판단이다.
PERIOD_REQUIRED_KINDS = ("WEEKLY_REPORT",)

# models/deliverable.py 의 _FORMAT 과 같아야 한다. 리비전 0021 이 PDF 를 더했다.
DELIVERABLE_FORMATS = ("XLSX", "HTML", "MD", "PDF")
# 실제로 만들 수 있는 형식. **DB 가 허용하는 것과 다르다** — 허용값은 넷인데
# 만드는 코드는 아직 Markdown 하나다. 나머지는 501 로 분명히 알린다. 값이
# 틀린 것(400)과 서버가 아직 못 하는 것(501)은 다른 상황이다.
SUPPORTED_DELIVERABLE_FORMATS = ("MD",)

# 제목에 쓰는 사람이 읽는 이름. 화면의 KINDS 목록과 문구를 맞춘다.
DELIVERABLE_KIND_LABELS = {
    "WEEKLY_REPORT": "주간 보고서",
    "DECISION_LOG": "결정사항 대장",
    "MEETING_AGENDA": "다음 회의 안건",
    "PROJECT_STATUS": "프로젝트 현황",
}


class PreviewCounts(BaseModel):
    """산출물에 담길 재료의 건수.

    `completed_tasks` 는 리비전 0019 로 `tasks` 테이블이 생긴 뒤부터 실제로 센다.
    전에는 셀 수 없어서 `None` 이었다 — 이제 다른 재료와 같은 `int` 이고, 0 은
    "아직 셀 수 없다" 가 아니라 **정말 0건**이라는 뜻이다.
    """

    documents: int
    decisions: int
    schedule_items: int
    amount_items: int
    # 완료한 태스크. 주간 보고서·현황 한 장의 재료다(DLV-002-1 은 tasks.completed_at
    # 을 필수로 요구한다). 결정사항 대장·회의 안건에는 담기지 않아 0 이다.
    completed_tasks: int
    # 기간과 무관하다. 지금 남아 있는 승인 대기 건수다.
    pending_suggestions: int

    @property
    def countable_total(self) -> int:
        """셀 수 있는 재료의 합. 생성 가능 판정에 쓴다.

        완료한 태스크도 **더한다.** 명세가 주간 보고서의 내용으로 "문서·태스크·
        결정·기한·금액 변동" 을 나열하므로, 그 기간에 끝낸 일만 있어도 보고서에
        담을 것이 있다.

        `pending_suggestions` 는 **더하지 않는다.** 그것은 "담길 내용" 이 아니라
        "처리해야 할 일" 이라, 승인 대기만 있고 확정된 내용이 없으면 보고서는
        비어 있다.
        """
        return (
            self.documents
            + self.decisions
            + self.schedule_items
            + self.amount_items
            + self.completed_tasks
        )


class DeliverablePreviewResponse(BaseModel):
    kind: str
    period_from: date | None
    period_to: date | None
    counts: PreviewCounts
    # 만들 수 있는가. 담을 내용이 하나도 없으면 False 다 (DLV-001-2 완료 판정).
    can_generate: bool
    # can_generate 가 False 인 이유. 화면이 그대로 보여줄 수 있는 문장이다.
    # True 면 None.
    blocked_reason: str | None = None
    # 이 유형이 기간을 요구하는가. 화면이 날짜 입력을 띄울지 정한다.
    needs_period: bool
    # 셀 수 없는 재료의 이름. 화면이 "집계 전" 으로 표시한다.
    # `tasks` 테이블이 생겨 지금은 항상 빈 목록이다. **필드를 지우지 않는다** —
    # 다음에 또 못 세는 재료가 생기면 화면을 고치지 않고 여기로 알릴 수 있다.
    uncountable: list[str] = Field(default_factory=list)



class DeliverableCreateRequest(BaseModel):
    """산출물 만들기 요청 (POST /deliverables).

    `format` 에 **기본값을 두지 않는다.** DLV-001-1 완료 판정이 "형식을 고르지
    않으면 생성 버튼이 비활성화된다" 이므로 서버도 받지 않는다. 기본값을 두면
    나중에 "왜 md 로 나왔지" 가 생긴다.

    기간은 유형과 무관하게 받는다. 주간 보고서만 필수이고 나머지에서는 서버가
    무시한다 — 미리보기(GET)와 같은 규칙이라 화면이 유형별 규칙을 몰라도 된다.

    ⚠ `format` 을 빼면 `422 VALIDATION_ERROR` 다. `ErrorCode.FORMAT_REQUIRED` 를
    쓰지 않는다 — error_codes.py 머리말이 "요청 형식 오류는 Pydantic 이 먼저
    막으므로 별도 코드를 두지 않는다" 로 정하고 있다. 둘 다 422 이고, 필드가
    빠졌다는 사실은 검증 응답의 `errors` 가 더 정확히 알려준다.
    (`models/deliverable.py` 주석은 FORMAT_REQUIRED 를 가리키는데 그 규칙이
    정해지기 전에 쓴 것이다.)
    """

    kind: str = Field(description="WEEKLY_REPORT · DECISION_LOG · MEETING_AGENDA · PROJECT_STATUS")
    format: str = Field(description="XLSX · HTML · MD · PDF. 지금 만들 수 있는 것은 MD 다")
    period_from: date | None = None
    period_to: date | None = None


class DeliverableResponse(BaseModel):
    """만들어진 산출물 한 건.

    `source_counts` 는 **만든 시점의 재료 개수 스냅샷**이다. 나중에 지금 개수와
    비교해 "생성 후 문서가 2건 추가됨" 을 띄우는 근거가 된다(DLV-003-4).
    미리보기의 건수와 **같은 키**를 쓴다 — 그래야 다시 세어 비교할 수 있다.
    """

    id: int
    kind: str
    format: str
    title: str
    period_from: date | None
    period_to: date | None
    file_size: int | None
    source_counts: dict[str, int]
    generated_at: datetime
    # 파일을 받는 경로. 화면이 경로를 조립하지 않게 서버가 준다.
    download_url: str
