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
    "FORMAT_FILE_TYPES",
    "PERIOD_REQUIRED_KINDS",
    "SUPPORTED_DELIVERABLE_FORMATS",
    "TEXT_PREVIEW_FORMATS",
    "DeliverableCreateRequest",
    "DeliverableContentResponse",
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
# 만드는 코드는 아직 둘이다. 나머지는 501 로 분명히 알린다. 값이 틀린 것(400)과
# 서버가 아직 못 하는 것(501)은 다른 상황이다.
#
# PDF 를 아직 안 한 이유는 한글 폰트까지 붙어야 해서 XLSX 와 다른 방에서
# 한다(2026-08-25 판단). XLSX 는 openpyxl 로 만든다(requirements.txt 추가).
SUPPORTED_DELIVERABLE_FORMATS = ("MD", "HTML", "XLSX")

# 본문을 **문자열로 돌려주는** 형식. `DeliverableContentResponse.body` 가 `str`
# 이라 XLSX(바이너리) 는 여기 없다 — `preview_deliverable_content` 가 이 상수로
# 막는다. `SUPPORTED_DELIVERABLE_FORMATS` 와 다른 이유: XLSX 는 **만들 수는
# 있지만**(생성·다운로드는 파일이라 바이너리를 그대로 쓴다) 이 텍스트 미리보기
# 응답에는 담을 수 없다 — "아직 못 만든다" 와는 다른 제약이다.
TEXT_PREVIEW_FORMATS = ("MD", "HTML")

# 형식별 파일 확장자와 MIME 타입. 저장(서비스)과 내려보내기(라우터)가 같은 값을
# 봐야 해서 한 곳에 둔다 — 갈리면 .md 파일을 text/html 로 주는 일이 생긴다.
FORMAT_FILE_TYPES = {
    "MD": ("md", "text/markdown; charset=utf-8"),
    "HTML": ("html", "text/html; charset=utf-8"),
    "XLSX": (
        "xlsx",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ),
}

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

    ⚠ `format` 을 빼거나 **빈 문자열로 보내면** `422 VALIDATION_ERROR` 다.
    `ErrorCode.FORMAT_REQUIRED` 를 쓰지 않는다 — error_codes.py 머리말이 "요청
    형식 오류는 Pydantic 이 먼저 막으므로 별도 코드를 두지 않는다" 로 정하고 있다.
    둘 다 422 이고, 어느 필드가 문제인지는 검증 응답의 `errors` 가 더 정확히
    알려준다. (`models/deliverable.py` 주석은 FORMAT_REQUIRED 를 가리키는데 그
    규칙이 정해지기 전에 쓴 것이다.)

    빈 문자열을 400(`INVALID_DOCUMENT_TYPE`)으로 두지 않는 이유
      "값이 틀렸다" 와 "아직 고르지 않았다" 는 사용자가 할 일이 다르다. 전자는
      잘못된 값을 고쳐야 하고 후자는 선택만 하면 된다. 빈 값에 "XLSX · HTML · MD ·
      PDF 중 하나여야 합니다" 를 띄우면 무엇이 잘못됐는지 알기 어렵다.
    """

    # min_length=1 이 있어야 **빈 문자열이 값으로 통과하지 않는다.**
    # 빈 값은 "고르지 않았다" 는 뜻이라 "값이 틀렸다"(400)가 아니라 422 로 막아야
    # 한다. 없는 필드와 빈 필드가 같은 응답을 받는 것도 화면 입장에서 자연스럽다.
    kind: str = Field(
        min_length=1,
        description="WEEKLY_REPORT · DECISION_LOG · MEETING_AGENDA · PROJECT_STATUS",
    )
    format: str = Field(
        min_length=1,
        description="XLSX · HTML · MD · PDF. 지금 만들 수 있는 것은 MD · HTML · XLSX 다",
    )
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

    # --- 갱신 필요 판정 (DLV-003-4) -----------------------------------------
    # 만든 뒤에 재료가 늘었는가. 화면이 "다시 만들기" 를 띄울 근거다.
    is_stale: bool = False
    # 무엇이 몇 건 늘었는지. {"documents": 2} 처럼 **늘어난 것만** 담는다.
    # 줄어든 것은 담지 않는다 — 문서를 지웠다고 보고서를 다시 만들 이유가 없고,
    # 이유를 못 밝히는 "갱신 필요" 는 사용자를 헷갈리게 한다.
    #
    # 화면이 이 값으로 문장을 만들 수 있다 — "문서 2건이 나중에 추가됨".
    # 서버가 문장을 만들지 않는 이유는 항목 이름을 화면이 이미 번역하고 있어서다.
    stale_changes: dict[str, int] = Field(default_factory=dict)



class DeliverableContentResponse(BaseModel):
    """만들지 않고 본문만 돌려주는 응답 (본문 미리보기).

    `DLV-001-2` 의 「미리보기」는 **건수** 미리보기다(완료 판정이 "건수가 보이고" 다).
    이것은 그것을 한 걸음 넓힌 것이고 **명세에 없던 항목**이다. 그전에는 만들어야
    내용을 볼 수 있었고, 확인하려고 만든 산출물이 이력에 쌓이는 것을 막을 방법이
    없었다.

    파일을 만들지 않으므로 `file_size`·`download_url`·`id` 가 없다. 이력에도 남지
    않는다. 그것이 이 응답의 요점이다.

    `format` 은 요청한 그대로다. 만들기와 **같은 형식 검사**를 거치므로 미리 본 형식은
    반드시 만들 수도 있다 — 미리보기만 되고 만들기는 안 되는 형식을 두지 않는다.
    """

    kind: str
    title: str
    # 요청한 형식 그대로. 화면이 이 값을 보고 «어떻게 그릴까» 를 정한다 —
    # HTML 이면 iframe, MD 면 글자다. 화면이 스스로 추측하지 않게 서버가 담아 준다.
    format: str
    period_from: date | None
    period_to: date | None
    # 본문 그대로.
    #
    # HTML 이면 `<!doctype>` 부터 `<style>` 까지 담긴 **완전한 문서**다
    # (deliverable_html.render_html). 화면은 이것을 `<iframe sandbox srcDoc>` 에
    # 넣는다 — dangerouslySetInnerHTML 로 심지 않는다. sandbox 가 스크립트·폼·부모
    # 접근을 막으므로 escape 에 구멍이 생겨도 실행되지 않는다.
    body: str
