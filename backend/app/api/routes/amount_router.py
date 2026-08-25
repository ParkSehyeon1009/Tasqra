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
from starlette import status

from app.dependencies import (
    ProjectAccess,
    get_amount_item_service,
    get_amount_precedent_service,
    get_amount_summary_service,
    get_amount_task_service,
    get_project_access,
    get_project_amount_access,
    get_project_editor_access,
)
from app.schemas.amount_item import (
    AmountItemListResponse,
    AmountItemRow,
    AmountItemUpdateRequest,
)
from app.schemas.amount_precedent import AmountPrecedentResponse
from app.schemas.amount_summary import AmountSummaryResponse
from app.schemas.task import TaskResponse
from app.services.amount_item_service import AmountItemService
from app.services.amount_precedent_service import AmountPrecedentService
from app.services.amount_summary_service import AmountSummaryService
from app.services.amount_task_service import AmountTaskService

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



@router.post(
    "/amount-items/{item_id}/task",
    response_model=TaskResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_task_from_amount_mismatch(
    item_id: int,
    access: ProjectAccess = Depends(get_project_editor_access),
    service: AmountTaskService = Depends(get_amount_task_service),
) -> TaskResponse:
    """검산이 어긋난 금액 항목을 태스크로 만든다 (`AMT-004-3` · `TSK-002-1`).

    **자동으로 만들지 않습니다.** 완료 판정이 *"승인형 태스크 제안 카드가 생기고
    자동 등록은 하지 않는다"* 라서, 검산할 때가 아니라 **사람이 누를 때** 만듭니다.
    그래서 이 엔드포인트가 승인 버튼 그 자체입니다.

    `TSK-002-1` 의 *"승인 전에는 보드에 나타나지 않는다"* 도 같이 만족합니다 —
    누르기 전에는 `tasks` 에 행이 없으므로 보드 조회를 건드릴 필요가 없습니다.

    ### 요청 본문이 없습니다

    금액이나 차액을 받지 않고 **항목 id 만** 받습니다. 서버가 그 항목을 다시
    검산합니다. 화면이 낡은 목록을 들고 있으면 이미 고쳐진 항목으로 태스크를 만들
    수 있고, 그러면 근거 없는 태스크가 남습니다.

    ### 제목·설명을 서버가 만듭니다

    화면마다 문구를 만들면 같은 성격의 태스크가 다르게 적힙니다. 그리고 이 태스크는
    보드에서도 읽히므로 **계산 근거가 설명 안에 함께** 있어야 무슨 일인지 알 수
    있습니다. 차액은 부호가 아니라 문장으로 적습니다 — `-50,000` 만 적으면
    "부족" 으로 읽힙니다.

    `type` 은 `DOCUMENT` 입니다. 문서에 적힌 값을 확인하는 일이고, `OTHER` 로 두면
    보드에서 성격을 알 수 없습니다.

    ### 만들어진 태스크

    `origin='AI_APPROVED'`, `source_suggestion_id=<금액 항목 id>` 입니다.

    ⚠ `source_suggestion_id` 는 원래 「제안 테이블의 id」 자리인데 그 테이블이 아직
    없어서 **빌려 쓰고 있습니다.** `task_suggestions` 를 만드는 리비전에서 컬럼을
    갈라야 합니다 — 자세한 것은 `models/task.py` 의 그 컬럼 주석에 있습니다.

    ### 오류

      `404 AMOUNT_ITEM_NOT_FOUND`        그 항목이 없다 (다른 프로젝트 것 포함)
      `409 AMOUNT_NOT_MISMATCHED`        어긋난 항목이 아니다 → 목록이 낡았다
      `409 AMOUNT_TASK_ALREADY_EXISTS`   이미 만든 태스크가 있다
      `403 PROJECT_FORBIDDEN`            VIEWER 다. 태스크를 만들 수 없다

    검산 불가(제경비처럼 수량·단가가 없는 항목)와 금액이 안 적힌 항목도
    `AMOUNT_NOT_MISMATCHED` 입니다. **어긋난 것이 아니라 정상**이라서 태스크로 만들
    이유가 없습니다.
    """
    task = service.create_from_mismatch(
        access.project.id, item_id, access.member.user_id
    )
    return TaskResponse.model_validate(task)



@router.patch("/amount-items/{item_id}", response_model=AmountItemRow)
def update_amount_item(
    item_id: int,
    body: AmountItemUpdateRequest,
    access: ProjectAccess = Depends(get_project_editor_access),
    service: AmountItemService = Depends(get_amount_item_service),
) -> AmountItemRow:
    """금액 항목을 고친다 (`AMT-001-2` 금액 항목 승인·수정).

    검산이 어긋났을 때(`AMT-002-1`) **사람이 할 수 있는 일**이 이것입니다. 그전에는
    불일치를 보여주기만 하고 고칠 곳이 없었습니다.

    ### 보낸 필드만 고칩니다

    「안 보냈다」와 「`null` 로 보냈다」가 다릅니다 — 앞은 그대로 두라는 뜻이고 뒤는
    비우라는 뜻입니다. 제경비처럼 수량이 원래 없는 항목에서 잘못 채운 값을 지울 수
    있어야 합니다.

    고칠 수 있는 것은 `quantity`·`unit`·`unit_price`·`amount`·`category` 다섯입니다.
    `item_name` 과 `source_quote` 는 **문서에서 읽은 사실**이라 고치지 않습니다 —
    이름을 바꾸면 원문과 대조할 수 없습니다.

    ### 고치면 승인된 것으로 봅니다

    `decision` 이 `EDITED` 가 되고 `decided_by`·`decided_at` 이 남습니다.
    `PENDING` 이던 항목은 이때 합계에 들어옵니다 — 그것이 `AMT-001-2` 가 말하는
    *"승인하거나 수정한다"* 입니다. 사람이 값을 확인해 고쳤으면 그 자체가 승인입니다.

    ### 응답이 목록의 한 줄과 같은 모양입니다

    **다시 검산한 결과**(`expected`·`verified`·`difference`)가 함께 옵니다. 고쳐서
    맞게 됐는지 바로 보이고, 화면은 전체를 다시 받지 않고 그 줄만 갈아끼울 수 있습니다.

    고친 뒤 여전히 어긋나 있어도 **막지 않습니다.** 그것도 정보입니다 — 수량을
    바로잡았는데 아직 맞지 않으면 다른 곳이 틀렸다는 뜻입니다.

    ### 문서에 적힌 금액(`amount`)을 고치는 것

    막지 않지만 **마지막 선택**입니다. 그 값을 고치면 문서의 오류가 감춰져서 합계
    대조가 무의미해집니다(`models/amount.py` 의 그 컬럼 주석이 근거입니다).
    우리가 잘못 읽은 것이라면 `quantity`·`unit_price` 를 고치는 것이 맞습니다.

    ### 오류

      `422 VALIDATION_ERROR`        고칠 값을 하나도 안 보냈다 · 음수 · 없는 원가구분
      `404 AMOUNT_ITEM_NOT_FOUND`   그 항목이 없다 (다른 프로젝트 것 포함)
      `403 PROJECT_FORBIDDEN`       VIEWER 다

    음수를 막는 이유: 문서에 적힌 금액과 단가는 음수가 아닙니다. 감액은 변경계약서의
    항목으로 들어오고, 여기에 음수를 넣으면 합계가 조용히 줄어듭니다.
    """
    return service.update(
        access.project.id,
        item_id,
        access.member.user_id,
        body.model_dump(exclude_unset=True),
    )
