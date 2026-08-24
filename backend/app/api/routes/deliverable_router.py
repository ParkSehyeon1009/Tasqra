# =============================================================================
# 이 파일의 책임: 산출물 API 의 HTTP 경계를 정의한다. 생성 대상 미리보기
#   (DLV-001-2) · 만들기(DLV-002-x) · 다운로드(DLV-003-3) 셋이다.
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
# 만들기가 미리보기를 그대로 부른다
#   완료 판정이 "**LLM 호출 전에** 건수가 보이고 대상이 없으면 생성이 방지된다"
#   이므로 미리보기가 먼저 있었고, 만들기는 그것을 전제로 설계했다. 만들기는
#   자기만의 집계를 갖지 않는다 — 그러면 "미리보기는 12건, 보고서는 9건" 이 생긴다.
#
# ⚠ 지금 만들 수 있는 형식은 Markdown 하나다
#   DB 는 XLSX·HTML·MD·PDF 를 허용하지만(리비전 0021) 만드는 코드는 MD 만 있다.
#   나머지는 501 로 분명히 알린다. 형식을 늘리는 것은 별도 작업이고, XLSX·PDF 는
#   새 라이브러리가 필요해 팀 이미지 크기에 영향을 준다.
# =============================================================================

from datetime import date

from fastapi import APIRouter, Depends, Query
from fastapi.responses import FileResponse

from app.dependencies import (
    ProjectAccess,
    get_deliverable_service,
    get_project_access,
    get_project_editor_access,
)
from app.schemas.deliverable import (
    DeliverableCreateRequest,
    DeliverablePreviewResponse,
    DeliverableResponse,
)
from app.services.deliverable_service import DeliverableService

router = APIRouter(prefix="/api/projects/{project_id}", tags=["deliverables"])


def _to_response(project_id: int, row) -> DeliverableResponse:
    """이력 한 건을 응답으로. 다운로드 경로를 **서버가** 만든다.

    화면이 경로를 조립하면 경로를 바꿀 때 양쪽을 고쳐야 한다.
    """
    return DeliverableResponse(
        id=row.id,
        kind=row.kind,
        format=row.format,
        title=row.title,
        period_from=row.period_from,
        period_to=row.period_to,
        file_size=row.file_size,
        source_counts=row.source_counts_json,
        generated_at=row.generated_at,
        download_url=f"/api/projects/{project_id}/deliverables/{row.id}/file",
    )


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
    | `WEEKLY_REPORT` | **필수** | 기간 안의 문서·완료한 태스크·결정·일정·금액 |
    | `DECISION_LOG` | 무시 | 결정 **전부** |
    | `MEETING_AGENDA` | 무시 | **미결 결정만** (`status='PENDING'`) |
    | `PROJECT_STATUS` | 무시 | 현재 상태 전부 |

    `can_generate` 가 `false` 면 만들 수 없고 `blocked_reason` 에 이유가 있다.
    화면이 그 문장을 그대로 보여줄 수 있다.

    `counts.completed_tasks` 는 리비전 0019 로 `tasks` 테이블이 생긴 뒤부터 실제
    건수다. 상태가 `DONE` 이고 `completed_at` 이 기간에 드는 태스크만 센다. 전에는
    셀 수 없어 `null` 이었고, 지금은 0 이 정말 0건이라는 뜻이다.

    `uncountable` 은 셀 수 없는 재료의 이름이며 지금은 빈 목록이다. 다음에 못 세는
    재료가 생기면 여기에 담아 보낸다.

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



@router.post("/deliverables", response_model=DeliverableResponse, status_code=201)
def create_deliverable(
    request: DeliverableCreateRequest,
    access: ProjectAccess = Depends(get_project_editor_access),
    service: DeliverableService = Depends(get_deliverable_service),
) -> DeliverableResponse:
    """산출물을 만든다 (DLV-002-x).

    경로는 팀 계약서 43행에 이미 정해져 있다 — `POST /api/projects/{pid}/deliverables`.

    **미리보기와 같은 규칙으로 센다.** 만들기가 자기만의 집계를 갖지 않으므로
    "미리보기는 12건이라 했는데 보고서는 9건" 이 생기지 않는다.

    ⚠️ 지금 만들 수 있는 형식은 **Markdown 하나**다. `XLSX`·`HTML`·`PDF` 는 DB 가
    허용하는 값이지만 만드는 코드가 아직 없어 `501` 을 낸다. 값이 틀린 것(400)과
    서버가 아직 못 하는 것(501)은 다른 상황이라 구분한다.

    ⚠️ 개요 문장은 아직 비어 있다. `DLV-002-1` 완료 판정의 "LLM 호출은 개요 1회"
    가 붙지 않았다. 표는 모두 실제 자료이고, 개요 자리에 비었다고 적는다 —
    없는 문장을 지어내지 않는다.

    편집 권한이 필요하다(`VIEWER` 는 만들 수 없다). 읽기 전용 참여자가 프로젝트에
    파일과 이력을 남기는 것은 역할의 뜻과 맞지 않는다.

    오류
      `400 INVALID_DOCUMENT_TYPE`         kind 나 format 이 허용값이 아니다
      `422 DELIVERABLE_EMPTY`             담을 내용이 없다. 이유가 detail 에 있다
      `422 PERIOD_REQUIRED`               주간 보고서인데 기간이 없다
      `422 INVALID_PROJECT_DATES`         시작일이 종료일보다 늦다
      `501 DELIVERABLE_FORMAT_NOT_READY`  아직 못 만드는 형식이다
      `403 PROJECT_FORBIDDEN`             VIEWER 다
    """
    row = service.generate(
        access.project.id,
        kind=request.kind,
        deliverable_format=request.format,
        period_from=request.period_from,
        period_to=request.period_to,
        user_id=access.member.user_id,
    )
    return _to_response(access.project.id, row)


@router.get("/deliverables/{deliverable_id}/file")
def download_deliverable(
    deliverable_id: int,
    access: ProjectAccess = Depends(get_project_access),
    service: DeliverableService = Depends(get_deliverable_service),
) -> FileResponse:
    """만들어 둔 산출물을 내려받는다 (DLV-003-3).

    경로는 계약서 45행 그대로다. 계약서 본문의 예시에는
    `/api/deliverables/9/file` 로 적혀 있는데 **표(45행)와 어긋난다.** 표를 따랐다 —
    다른 엔드포인트가 모두 프로젝트 아래에 있고, 권한도 프로젝트 단위로 판정한다.

    조회는 `VIEWER` 에게도 열어 둔다. 만드는 것과 보는 것은 다른 권한이다.

    받을 때의 파일 이름은 **제목으로** 만든다. 저장은 uuid 이름으로 하지만
    사용자에게는 "주간 보고서 2026-08-04 ~ 2026-08-10.md" 가 보여야 한다.

    오류
      `404 DELIVERABLE_NOT_FOUND`     이 프로젝트에 그 산출물이 없다
      `410 DELIVERABLE_FILE_MISSING`  이력은 있는데 파일이 사라졌다
    """
    row = service.open_file(access.project.id, deliverable_id)
    extension = row.format.lower()
    return FileResponse(
        row.file_path,
        # 한글 제목이라 브라우저가 알아볼 수 있게 FileResponse 가 RFC 5987 로
        # 인코딩해 준다. 여기서 직접 헤더를 만들지 않는다.
        filename=f"{row.title}.{extension}",
        media_type="text/markdown; charset=utf-8",
    )



@router.get("/deliverables", response_model=list[DeliverableResponse])
def list_deliverables(
    access: ProjectAccess = Depends(get_project_access),
    service: DeliverableService = Depends(get_deliverable_service),
) -> list[DeliverableResponse]:
    """만든 산출물 이력 (DLV-003-3). 계약서 44행.

    최근에 만든 것이 먼저 온다. 페이지를 나누지 않는다 — 산출물은 프로젝트당
    수십 건 규모이고 화면이 한 번에 보여준다.

    조회는 `VIEWER` 에게도 열어 둔다. 만드는 것과 보는 것은 다른 권한이다.

    ⚠️ 파일이 남아 있는지는 확인하지 않는다. 목록에서 건마다 디스크를 보면 파일
    수만큼 접근이 생긴다. 없어진 파일은 받으려 할 때 `410` 으로 알린다.
    """
    return [
        _to_response(access.project.id, row)
        for row in service.list_history(access.project.id)
    ]


@router.delete("/deliverables/{deliverable_id}", status_code=204)
def delete_deliverable(
    deliverable_id: int,
    access: ProjectAccess = Depends(get_project_editor_access),
    service: DeliverableService = Depends(get_deliverable_service),
) -> None:
    """산출물을 이력에서 지우고 파일도 지운다. 계약서 46행.

    편집 권한이 필요하다. 만들 수 없는 사람이 지울 수 있으면 안 된다.

    이력을 먼저 지우고 파일을 나중에 지운다 — 거꾸로 하면 실패했을 때 "목록에
    있는데 받을 수 없는" 행이 남는다. 자세한 이유는 서비스 주석에 있다.

    오류
      `404 DELIVERABLE_NOT_FOUND`  이 프로젝트에 그 산출물이 없다
      `403 PROJECT_FORBIDDEN`      VIEWER 다
    """
    service.delete(access.project.id, deliverable_id)
