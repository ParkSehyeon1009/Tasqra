# =============================================================================
# 이 파일의 책임: 금액 관련 조회 엔드포인트다. 지금은 과거 유사 사업의 단가
#   선례 조회 하나뿐이다(SRH-002-3).
# 다른 파일과의 관계: services/amount_precedent_service.py 를 부르고
#   schemas/amount_precedent.py 를 돌려준다.
# Spring 비교: @RestController + @GetMapping 이다. Depends 는 생성자 주입에
#   해당하고, ProjectAccess 는 인터셉터가 넣어 주는 인증·권한 컨텍스트다.
#
# 의미 검색(POST /api/search)과 방식이 다른 이유 두 개
#   1. GET 이다. 검색은 질의가 문장이라 URL 이 길어지고, 검색어가 브라우저
#      이력·접근 로그에 남지 않아야 해서 POST 로 했다. 항목명은 짧고, 이미
#      문서에 적혀 있는 값이며, 범위는 서버가 계산한다. 조회라서 GET 이 맞다.
#   2. 경로에 project_id 가 있다. 검색은 범위가 "내 멤버십 전체" 일 수 있어
#      프로젝트 하위 리소스가 아니었다. 여기는 **현재 프로젝트가 반드시**
#      필요하다 — 그것을 빼고 찾는 것이 이 기능이다. 경로가 진짜로 그 프로젝트를
#      가리킨다.
#
# get_project_access 를 쓰는 이유
#   VIEWER 도 조회할 수 있어야 한다고 봤다. 금액 열람 권한 제한(AMT-003-1)은
#   VIEWER 노출 정책이 아직 미결이라, 그것이 정해지면 여기 의존성을 바꾼다.
#   지금 editor 로 잠그면 정책이 정해질 때 되돌려야 한다.
# =============================================================================

from fastapi import APIRouter, Depends, Query

from app.dependencies import ProjectAccess, get_amount_precedent_service, get_project_access
from app.schemas.amount_precedent import AmountPrecedentResponse
from app.services.amount_precedent_service import AmountPrecedentService

router = APIRouter(prefix="/api/projects/{project_id}", tags=["amount"])


@router.get("/amount-precedents", response_model=AmountPrecedentResponse)
def list_amount_precedents(
    item_name: str = Query(min_length=1, max_length=300, description="찾을 항목명. 예: 특급기술자"),
    limit: int = Query(20, ge=1, le=100, description="돌려줄 선례 수"),
    access: ProjectAccess = Depends(get_project_access),
    service: AmountPrecedentService = Depends(get_amount_precedent_service),
) -> AmountPrecedentResponse:
    return service.find_precedents(
        user_id=access.member.user_id,
        current_project_id=access.project.id,
        item_name=item_name,
        limit=limit,
    )
