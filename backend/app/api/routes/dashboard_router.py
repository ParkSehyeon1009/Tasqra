# =============================================================================
# 이 파일의 책임: 프로젝트 단건·전역 포트폴리오 핵심 현황과 프로젝트
#   캘린더 조회 엔드포인트를 제공한다.
# 다른 파일과의 관계: services/dashboard_service.py 를 부르고
#   schemas/dashboard.py 를 돌려준다.
# Spring 비교: @RestController + @GetMapping 이다. ProjectAccess 는 인터셉터가
#   넣어 주는 인증·권한 컨텍스트에 해당한다.
#
# 지표를 하나로 묶어 한 번에 주는 이유
#   카드마다 엔드포인트를 두면 대시보드를 열 때 요청이 다섯 번 나가고, 그 사이에
#   문서가 늘면 카드끼리 숫자가 안 맞는다("문서 12건" 인데 "유형 분포 합 11").
#   한 응답으로 주면 같은 시점의 값이라 서로 맞는다. 대시보드는 지표를 함께 보는
#   화면이라 부분만 갱신할 이유도 없다.
#
# get_project_access 를 쓰는 이유
#   현황 조회는 VIEWER 도 할 수 있어야 한다. 프로젝트에 무슨 문서가 있는지는
#   멤버라면 문서 목록에서 이미 볼 수 있는 정보이고, 대시보드는 그것을 세어
#   보여주는 것이라 더 넓은 권한을 요구할 근거가 없다.
#
#   다만 금액 승인 대기 건수는 amount-precedents 와 같은 상황에 있다 — 금액
#   열람 권한 제한(AMT-003-1)의 VIEWER 정책이 아직 미결이다. 정책이 정해져
#   VIEWER 에게 금액을 감춰야 한다면, 이 의존성을 바꾸는 것이 아니라
#   pending_amount_items 만 가리는 편이 맞다. 나머지 지표는 VIEWER 가 봐도
#   되는 값이라 엔드포인트 전체를 잠그면 과하다.
# =============================================================================

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query

from app.dependencies import (
    ProjectAccess,
    get_current_user,
    get_dashboard_service,
    get_project_access,
)
from app.models.user import User
from app.schemas.dashboard import (
    DashboardCalendarResponse,
    DashboardResponse,
    PortfolioDashboardResponse,
)
from app.services.dashboard_service import DashboardService

router = APIRouter(prefix="/api/projects/{project_id}", tags=["dashboard"])
portfolio_router = APIRouter(prefix="/api/portfolio", tags=["dashboard"])


@portfolio_router.get("/dashboard", response_model=PortfolioDashboardResponse)
def get_portfolio_dashboard(
    recent_document_limit: int = Query(
        5, ge=1, le=20, description="프로젝트마다 최근 문서를 몇 건까지 돌려줄지"
    ),
    activity_limit: int = Query(
        20, ge=1, le=100, description="전체 프로젝트의 최근 태스크 활동 수"
    ),
    user: User = Depends(get_current_user),
    service: DashboardService = Depends(get_dashboard_service),
) -> PortfolioDashboardResponse:
    return service.get_portfolio(
        user_id=user.id,
        recent_document_limit=recent_document_limit,
        activity_limit=activity_limit,
    )


@router.get("/dashboard", response_model=DashboardResponse)
def get_dashboard(
    recent_limit: int = Query(
        5, ge=1, le=20, description="최근 문서를 몇 건까지 돌려줄지"
    ),
    access: ProjectAccess = Depends(get_project_access),
    service: DashboardService = Depends(get_dashboard_service),
) -> DashboardResponse:
    return service.get_overview(
        project_id=access.project.id,
        recent_limit=recent_limit,
    )


@router.get("/dashboard/calendar", response_model=DashboardCalendarResponse)
def get_dashboard_calendar(
    from_: date = Query(alias="from", description="달력 조회 시작일"),
    to: date = Query(description="달력 조회 종료일"),
    access: ProjectAccess = Depends(get_project_access),
    service: DashboardService = Depends(get_dashboard_service),
) -> DashboardCalendarResponse:
    if from_ > to:
        raise HTTPException(status_code=422, detail="조회 시작일은 종료일보다 늦을 수 없습니다.")
    return service.get_calendar(
        project_id=access.project.id,
        starts_on=from_,
        ends_on=to,
    )
