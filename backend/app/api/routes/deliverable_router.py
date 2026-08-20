# =============================================================================
# 이 파일의 책임: 산출물 API 의 HTTP 경계를 정의한다. 지금은 생성 대상
#   미리보기(DLV-001-2)만 있다.
#
# 다른 파일과의 관계: services/deliverable_service.py 가 판단하고
#   schemas/deliverable.py 가 계약이다. main.py 에서 include_router 로 등록한다.
#
# Spring 비교: @RestController 다. get_project_access 가 @PreAuthorize 자리다.
#
# 경로가 팀 계약서에 이미 정해져 있다
#   API v2「예정」 시트 19행: GET /api/projects/{project_id}/deliverables/preview
#   그대로 쓴다. 검색(SRH-001)에서 경로를 바꿔야 했던 것과 달리 여기는 범위가
#   프로젝트 하나로 정해져 있어 프로젝트 아래에 두는 것이 맞다.
#
# GET 인 이유
#   읽기만 하고 부수효과가 없다. 질의가 짧고(kind·날짜 둘) 배열도 없다.
#   검색을 POST 로 둔 이유(한글 문장 질의 · 검색어가 로그에 남지 않아야 함)가
#   여기에는 없다.
#
# ⚠ 만들기(POST)는 이 PR 에 없다
#   미리보기만 먼저 낸다. 완료 판정이 "**LLM 호출 전에** 건수가 보이고 대상이
#   없으면 생성이 방지된다" 이므로, 미리보기가 먼저 있어야 만들기가 그것을 전제로
#   설계된다. 만들기는 DLV-002-1 이고 별도 작업이다.
# =============================================================================

from datetime import date

from fastapi import APIRouter, Depends, Query

from app.dependencies import (
    ProjectAccess,
    get_deliverable_service,
    get_project_access,
)
from app.schemas.deliverable import DeliverablePreviewResponse
from app.services.deliverable_service import DeliverableService

router = APIRouter(prefix="/api/projects/{project_id}", tags=["deliverables"])


@router.get("/deliverables/preview", response_model=DeliverablePreviewResponse)
def preview_deliverable(
    kind: str = Query(
        description="WEEKLY_REPORT · DECISION_LOG · MEETING_AGENDA · PROJECT_STATUS",
    ),
    period_from: date | None = Query(
        None, description="주간 보고서만 필수. 다른 유형에서는 무시된다"
    ),
    period_to: date | None = Query(None, description="같음"),
    access: ProjectAccess = Depends(get_project_access),
    service: DeliverableService = Depends(get_deliverable_service),
) -> DeliverablePreviewResponse:
    """산출물에 담길 건수를 미리 보여준다 (DLV-001-2).

    **AI 를 부르기 전에** 건수를 돌려준다. 빈 보고서와 헛 호출을 막는 것이 목적이다.

    유형마다 세는 대상이 다르다.

    | kind | 기간 | 담기는 것 |
    |---|---|---|
    | `WEEKLY_REPORT` | **필수** | 기간 안의 문서·결정·일정·금액 |
    | `DECISION_LOG` | 무시 | 결정 **전부** |
    | `MEETING_AGENDA` | 무시 | **미결 결정만** (`status='PENDING'`) |
    | `PROJECT_STATUS` | 무시 | 현재 상태 전부 |

    `can_generate` 가 `false` 면 만들 수 없고 `blocked_reason` 에 이유가 있다.
    화면이 그 문장을 그대로 보여줄 수 있다.

    **`counts.completed_tasks` 가 `null` 인 것은 0건이 아니라 "아직 셀 수 없다"** 다
    (`tasks` 테이블 미구현). 화면에서 0 으로 바꾸면 안 된다.

    오류
      `422 PERIOD_REQUIRED`         주간 보고서인데 기간이 없다
      `422 INVALID_PROJECT_DATES`   시작일이 종료일보다 늦다
      `400 INVALID_DOCUMENT_TYPE`   kind 가 네 값 중 하나가 아니다
      `404`                         내가 멤버가 아닌 프로젝트
    """
    return service.preview(
        access.project.id,
        kind=kind,
        period_from=period_from,
        period_to=period_to,
    )
