# =============================================================================
# 이 파일의 책임: 금액 관련 조회 엔드포인트다. 둘 있다 —
#   ① 과거 유사 사업의 단가 선례 조회 (SRH-002-3)
#   ② 프로젝트 금액 현황 (AMT-002-2 집계 + AMT-002-1 검산)
# 다른 파일과의 관계: services/amount_precedent_service.py ·
#   services/amount_summary_service.py 를 부르고 schemas/amount_precedent.py ·
#   schemas/amount_summary.py 를 돌려준다.
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

from app.dependencies import (
    ProjectAccess,
    get_amount_precedent_service,
    get_amount_summary_service,
    get_project_access,
    get_project_amount_access,
)
from app.schemas.amount_item import AmountItemListResponse
from app.schemas.amount_precedent import AmountPrecedentResponse
from app.schemas.amount_summary import AmountSummaryResponse
from app.services.amount_precedent_service import AmountPrecedentService
from app.services.amount_summary_service import AmountSummaryService

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


@router.get("/amount-summary", response_model=AmountSummaryResponse)
def get_amount_summary(
    access: ProjectAccess = Depends(get_project_amount_access),
    service: AmountSummaryService = Depends(get_amount_summary_service),
) -> AmountSummaryResponse:
    """프로젝트 금액 현황 (`AMT-002-2` 집계 · `AMT-002-1` 검산).

    경로는 팀 API 계약서 50행에 정해져 있던 것을 그대로 씁니다.

    **승인된 항목만 셉니다** (`APPROVED`·`EDITED`). `PENDING`·`REJECTED` 는
    빠집니다 — *"승인 전에는 어디에도 반영되지 않고"*(`AMT-001-2` 완료 판정).
    `EDITED` 를 넣는 것은 사람이 값을 고쳐 확정한 것이라서입니다.

    응답에 **합계에 들어가지 않은 것**도 담습니다.

    | 필드 | 뜻 |
    |---|---|
    | `excluded_no_amount` | 문서에 금액이 안 적혀 더할 수 없던 항목 수 |
    | `unverifiable_line_count` | 수량·단가가 없어 검산 못 한 항목 수 (오류 아님) |
    | `line_mismatches` | 수량 x 단가와 금액이 어긋난 항목 |

    합계만 주면 사용자가 그것을 전부로 읽습니다. **금액이 안 적힌 항목을 0 으로
    더하지 않는 이유**가 그것입니다 — 합계는 그대로지만 "모른다" 는 사실이 사라져
    사업 규모를 작게 오해합니다.

    ⚠️ **문서에 적힌 합계와의 대조는 하지 않습니다.** 그 값이 DB 에 없습니다 —
    `amount_items` 는 항목만 담고 문서 합계를 저장하지 않습니다. 대조는 추출
    시점에만 가능하고, 계약서도 `amount_check` 를 분석 응답 안에 두고 있습니다.

    **부가세는 `item_total` 에서 빠집니다.** 부가세는 공급가액에서 파생된 값이라
    항목들과 같은 층이 아니고, 함께 더하면 세금이 두 번 계산됩니다. 필요하면
    `total_with_vat` 를 씁니다.

    금액 항목이 없어도 오류가 아닙니다 — 0원과 빈 집계를 돌려줍니다.

    오류
      `403 PROJECT_FORBIDDEN`   VIEWER 다. 금액 열람 정책이 미결이라 지금은 막는다
      `409 CURRENCY_MISMATCH`   통화가 섞여 있다. 환율을 적용하지 않으므로 합칠 수 없다
      `404`                     내가 멤버가 아닌 프로젝트
    """
    return service.summarize(access.project.id)



@router.get("/amount-items", response_model=AmountItemListResponse)
def list_amount_items(
    limit: int = Query(200, ge=1, le=500, description="돌려줄 항목 수 상한"),
    access: ProjectAccess = Depends(get_project_amount_access),
    service: AmountSummaryService = Depends(get_amount_summary_service),
) -> AmountItemListResponse:
    """금액 항목 한 줄씩 + 항목별 검산 결과 (`AMT-003-3` 계산식·산출 근거 표시).

    `amount-summary` 가 «얼마인가» 를 답하고 이 엔드포인트가 «무엇을 더했는가» 를
    답합니다. 합계만 보면 그 숫자가 맞는지 확인할 방법이 없습니다.

    **합계 응답과 같은 저장소 메서드를 씁니다** — 조회 조건이 갈라지면 "합계는
    6건인데 목록은 4줄" 이 됩니다. 승인 상태(`APPROVED`·`EDITED`)와 정렬
    (문서 id, 항목 id)이 둘 다 같습니다.

    ### 검산 결과를 서버가 붙입니다

    | 필드 | 뜻 |
    |---|---|
    | `expected` | 수량 × 단가. 둘 중 하나라도 없으면 `null` |
    | `verified` | `true` 맞음 / `false` 어긋남 / **`null` 검산 불가** |
    | `difference` | `expected - amount`. **양수면 문서 금액이 작게** 적혀 있다 |

    `verified` 의 `false` 와 `null` 을 합치지 마십시오. 제경비·기술료처럼 비율로
    산정된 항목은 수량·단가가 원래 없어서 `null` 인데, `false` 로 묶으면 정상
    항목이 "틀린 항목" 으로 보입니다.

    화면에서 수량 × 단가를 다시 곱하지 마십시오. 서버는 `ROUND_HALF_UP` 으로 원
    단위에 맞추는데 자바스크립트 부동소수 곱셈은 큰 금액에서 1원씩 어긋납니다.

    ### 금액이 안 적힌 항목도 담습니다

    합계에서는 빠지지만(`excluded_no_amount`) 목록에서는 **어느 항목이 그랬는지
    보여야** 합니다. 확인하려는 것이 바로 그것입니다. 대신 `excluded_reason` 에
    이유를 적습니다.

    ### 상한

    기본 200, 최대 500 입니다. 산출내역서는 수백 줄이 흔해서 전부 내려주면 화면을
    펼치는 순간 느려집니다. 잘렸으면 `truncated` 가 `true` 이고 `total` 에 전체
    건수가 옵니다 — **자르고 말하지 않으면 사용자가 목록 줄 수를 전체로 읽습니다.**

    오류
      `403 PROJECT_FORBIDDEN`   VIEWER 다. 금액 열람 정책이 미결이라 지금은 막는다
      `404`                     내가 멤버가 아닌 프로젝트
    """
    return service.list_items(access.project.id, limit)
