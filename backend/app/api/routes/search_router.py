# =============================================================================
# 이 파일의 책임: 의미 검색 API(SRH-001)의 HTTP 경계를 정의한다.
#   요청을 받아 서비스에 넘기고 응답 스키마로 돌려준다. 검색 로직은 두지 않는다.
#
# 왜 /api/projects/{project_id}/search 가 아니라 /api/search 인가
#   검색 범위가 "내가 멤버인 프로젝트 전체"일 수 있어서다. 경로에 project_id 를
#   두고 전체 검색일 때 그것을 무시하면, 경로가 실제 동작과 다른 것을 가리킨다.
#   범위는 본문의 project_ids 로 받는다.
#     null        -> 내가 멤버인 모든 프로젝트
#     [3]         -> 그 프로젝트만
#     [3, 7]      -> 골라서 몇 개
#   화면의 토글이 그대로 이 값에 대응하므로 프론트가 단순해진다.
#
# 왜 GET 이 아니라 POST 인가
#   1. 질의가 문장이다. URL 에 넣으면 한글이 퍼센트 인코딩되어 길어진다.
#   2. 범위(project_ids)가 배열이고 앞으로 필터가 더 늘어난다
#      (문서 유형 · 기간 · SRH-004 하이브리드 가중치).
#   3. 검색 질의가 브라우저 이력과 서버 접근 로그에 남지 않는다. 조달 문서를
#      다루므로 "무엇을 찾고 있는지"가 사업 정보다.
#
# 다른 파일과의 관계: dependencies.get_current_user 로 사용자를 확인하고,
#   services/search_service.py 가 멤버십 검증과 검색을 한다. main.py 가 이
#   router 를 include_router 로 등록한다.
#
#   권한 검사를 get_project_access 로 하지 않는 이유: 그 의존성은 경로의
#   project_id 하나를 검사한다. 여기는 경로에 프로젝트가 없고 범위가 여러 개일
#   수 있다. 대신 서비스가 멤버십을 확인하고, 멤버가 아닌 id 가 섞이면
#   PROJECT_NOT_FOUND 로 막는다 — 보장 수준은 같다.
#
# Spring 비교: @RestController + @PostMapping 이다. Depends(get_current_user) 는
#   @AuthenticationPrincipal 자리에 해당한다.
# =============================================================================

from fastapi import APIRouter, Depends

from app.dependencies import get_current_user, get_search_service
from app.models.user import User
from app.schemas.search import (
    HybridSearchRequest,
    KeywordSearchRequest,
    SearchRequest,
    SearchResponse,
)
from app.services.search_service import SearchService

router = APIRouter(prefix="/api", tags=["search"])


@router.post("/search", response_model=SearchResponse)
def search_documents(
    request: SearchRequest,
    user: User = Depends(get_current_user),
    service: SearchService = Depends(get_search_service),
) -> SearchResponse:
    """의미 검색을 한다.

    범위는 request.project_ids 로 정한다. None 이면 내가 멤버인 전체다.
    멤버가 아닌 프로젝트를 지정하면 404 로 막는다.
    """
    return service.search(user.id, request)


@router.post("/search/keyword", response_model=SearchResponse)
def search_keyword(
    request: KeywordSearchRequest,
    user: User = Depends(get_current_user),
    service: SearchService = Depends(get_search_service),
) -> SearchResponse:
    """키워드 검색을 한다 (SRH-003).

    본문에 검색어가 **그대로 들어 있는** 조각을 찾는다. 문서번호·고유명사·금액
    처럼 의미 검색이 놓치는 것을 위한 것이다.

    `/api/search` 를 고치지 않고 엔드포인트를 따로 둔 이유
      의미 검색(SRH-001)은 이미 구현됨이고 프론트가 쓰고 있다. 요청 스키마에
      `mode` 를 더하면 그 계약을 고쳐야 하고 회귀 위험이 생긴다. 나중에
      하이브리드(SRH-004)가 둘을 합칠 때 `/api/search/hybrid` 를 하나 더 두면
      세 방식을 나란히 놓고 비교할 수 있다.

    응답은 `/api/search` 와 **같은 모양**이다. 키워드에서만 채워지는 세 필드가
    있다 — `match_kind`("keyword") · `match_count` · `match_offset`.
    의미 검색 응답에서는 그 셋이 `null` 이다.

    범위·권한은 의미 검색과 같다. 멤버가 아닌 프로젝트를 지정하면 404 다.
    검색어가 너무 짧으면 400 `KEYWORD_TOO_SHORT` 다.
    """
    return service.search_keyword(user.id, request)


@router.post("/search/hybrid", response_model=SearchResponse)
def search_hybrid(
    request: HybridSearchRequest,
    user: User = Depends(get_current_user),
    service: SearchService = Depends(get_search_service),
) -> SearchResponse:
    """의미 검색과 키워드 검색을 한 순위로 합친다 (SRH-004).

    **화면이 쓰는 것은 이 엔드포인트다.** `/api/search` 와 `/api/search/keyword` 는
    각각을 따로 재보거나 비교할 때 쓴다.

    사용자는 방식을 고르지 않는다 — 검색창이 하나이고, 어느 쪽으로 걸렸는지는
    결과의 `match_kind`(`"vector"`·`"keyword"`·`"both"`)로만 드러난다.

    순서는 RRF(`Σ 1/(k + 순위)`)로 정한다. 두 점수는 스케일이 달라 직접 더할 수
    없다 — 코사인 유사도 `0.8` 과 트라이그램 유사도 `0.8` 은 다른 뜻이다.
    순서의 근거는 `fused_score`·`vector_rank`·`keyword_rank` 로 응답에 담는다.

    검색어가 짧으면 **키워드 쪽만 건너뛰고 의미 검색으로 답한다.** 오류를 내지
    않는다 — 검색창 하나에 무엇을 넣어도 결과가 나와야 한다.

    `candidates` 는 두 방식에서 각각 가져올 후보 수다. 이 값이
    **재순위(SRH-002-1)의 상한을 정한다** — 리랭커는 받은 후보 안에서 순서만
    바꾸므로 후보에 없는 정답은 올릴 수 없다.
    """
    return service.search_hybrid(user.id, request)


@router.post("/search/explain", response_model=dict)
def explain_search(
    request: SearchRequest,
    user: User = Depends(get_current_user),
    service: SearchService = Depends(get_search_service),
) -> dict:
    """검색 실행계획을 돌려준다 (검증용).

    리비전 0014 에서 project_id 를 역정규화한 근거가 "조건이 인덱스 스캔 단계로
    내려간다"였는데, 청크가 0행이던 동안에는 확인할 수 없었다. 이 엔드포인트로
    계획을 눈으로 본다. 단일 프로젝트(=)와 여러 프로젝트(IN)의 계획이 같은지도
    여기서 비교한다.

    운영에 필요한 기능이 아니다. 검증이 끝나면 지우거나 관리자 전용으로 옮긴다.
    """
    return {"plan": service.explain(user.id, request)}
