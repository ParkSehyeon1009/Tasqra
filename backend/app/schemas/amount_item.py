# =============================================================================
# 이 파일의 책임: 금액 항목 목록 응답 모양을 정한다 (AMT-003-3 계산식·산출 근거
#   표시). 항목 한 줄마다 **검산 결과를 서버가 붙여서** 내려준다.
# 다른 파일과의 관계: services/amount_summary_service.py 가 채우고
#   api/routes/amount_router.py 가 돌려준다. 값의 출처는 models/amount.py 다.
# Spring 비교: 조회 전용 DTO 다. 엔티티를 그대로 내보내지 않는 이유가 여기서는
#   하나 더 있다 — 검산 결과는 DB 컬럼이 아니라 계산해서 붙이는 값이다.
#
# 왜 합계 응답(amount-summary)에 목록을 넣지 않고 따로 두는가
#   현황 화면은 열 때마다 부른다. 항목이 수백 줄인 프로젝트에서 합계만 보려는데
#   목록까지 매번 실어 보내면 느려진다. 목록은 **펼칠 때** 부른다.
#
# 검산을 화면에서 하지 않는 이유
#   수량 x 단가를 화면에서 곱하면 반올림 규칙이 두 곳에 생긴다. 서버는
#   ROUND_HALF_UP 으로 원 단위에 맞추는데(amount_calculator.verify_line),
#   자바스크립트는 부동소수 곱셈이라 큰 금액에서 1원씩 어긋날 수 있다.
#   에러가 나지 않고 숫자만 틀리는 종류다.
#
# difference 부호를 화면이 그대로 쓰면 안 된다
#   `difference = expected - amount` 다. 그래서 **문서 금액이 더 크면 음수**다.
#   화면에 -50,000 만 띄우면 "5만원 부족" 으로 읽힌다. 문장으로 풀어야 한다.
#   이 규칙을 LineMismatch(schemas/amount_summary.py)와 **같게** 맞춰 뒀다 —
#   두 응답이 같은 값을 다른 부호로 주면 화면이 어느 쪽인지 외워야 한다.
# =============================================================================

from decimal import Decimal

from pydantic import BaseModel, Field, model_validator

from app.models.enums import AmountCategory


class AmountItemRow(BaseModel):
    """금액 항목 한 줄 + 그 줄의 검산 결과.

    금액을 `int` 로, 수량을 `Decimal` 로 두는 이유가 다르다.

    | 필드 | 형 | 왜 |
    |---|---|---|
    | `amount`·`unit_price`·`expected` | `int` | 원 단위다. 합계 응답도 `int` 라 화면이 같은 방식으로 다룬다 |
    | `quantity` | `Decimal` | `Numeric(18,4)` 다. 0.5 인월처럼 소수가 실제로 쓰인다 |
    """

    id: int
    document_id: int
    # 어느 문서에서 나온 값인지. 근거를 되짚는 출발점이다.
    filename: str

    item_name: str
    # 판별하지 못하면 None 이다. 화면에서 '기타' 로 바꾸지 않는다 —
    # "판별 못 했다" 와 "기타로 판별했다" 는 다르다(리비전 0015).
    category: str | None
    quantity: Decimal | None
    unit: str | None
    unit_price: int | None
    # 문서에 적힌 금액. 안 적혀 있으면 None 이고 합계에서 빠진다.
    amount: int | None
    currency: str
    # 원문 근거. 표에서는 줄여 보여주고 마우스를 올리면 전체가 보이게 한다.
    source_quote: str | None
    decision: str
    # 이 항목으로 만든 태스크의 id. 없으면 None (AMT-004-3).
    #
    # 화면이 「태스크로 만들기」와 「태스크 있음」을 구별하는 데 쓴다. 이 값을
    # 서버가 주는 이유는, 화면이 태스크 목록을 따로 받아 맞춰보게 하면 그 규칙
    # (origin='AI_APPROVED' 이고 source_suggestion_id 가 이 항목인 것)이 화면에도
    # 생기기 때문이다.
    task_id: int | None = None

    # --- 서버가 계산해 붙이는 값 (DB 컬럼이 아니다) --------------------------
    # 수량 x 단가. 둘 중 하나라도 없으면 None 이다.
    expected: int | None = None
    # 검산 결과. True 맞음 / False 어긋남 / **None 검산 불가**.
    # 세 값이 뜻이 다르므로 False 와 None 을 합치지 않는다 — 합치면 제경비처럼
    # 비율로 산정된 항목이 "틀린 항목" 으로 보인다.
    verified: bool | None = None
    # expected - amount. 양수면 문서 금액이 작게 적혀 있다.
    difference: int | None = None
    # 합계에 들어가지 않은 이유. 들어갔으면 None 이다.
    excluded_reason: str | None = None


class AmountItemListResponse(BaseModel):
    """금액 항목 목록.

    `total` 과 `returned` 를 **함께** 준다. 상한 때문에 잘렸을 때 화면이 개수를
    잘못 세지 않게 하려는 것이다. 자르고 말하지 않으면 사용자는 목록의 줄 수를
    전체 건수로 읽는다.
    """

    items: list[AmountItemRow] = Field(default_factory=list)
    # 승인된 항목 전체 수. 상한과 무관하다.
    total: int
    # 이 응답에 실제로 담긴 수.
    returned: int
    # total > returned 인가. 화면이 직접 비교하지 않게 서버가 판단해 준다.
    truncated: bool
    limit: int
    # 목록에 담은 승인 상태. 합계 응답과 같은 값이다 — 두 응답이 다른 범위를
    # 보면 "6건인데 목록은 4줄" 같은 일이 생긴다.
    included_decisions: list[str] = Field(default_factory=list)



class AmountItemUpdateRequest(BaseModel):
    """금액 항목 수정 (`AMT-001-2` 금액 항목 승인·수정).

    ### 왜 이 기능이 필요한가

    검산이 어긋났을 때(`AMT-002-1`) 사람이 할 수 있는 일이 있어야 한다. 그전에는
    불일치를 **보여주기만** 하고 고칠 곳이 없었다. `decision='EDITED'` 는 설계에만
    있고 그 상태로 바꾸는 코드가 없었다.

    ### 보낸 것만 고친다

    필드를 `model_fields_set` 으로 판단한다. **「안 보냈다」와 「null 로 보냈다」가
    다르다** — 앞은 그대로 두라는 뜻이고 뒤는 비우라는 뜻이다. 제경비처럼 수량이
    원래 없는 항목에서 잘못 채운 값을 지울 수 있어야 한다.
    `TaskUpdateRequest` 도 같은 방식이다.

    ### 수정하면 승인된 것으로 본다

    저장하면 `decision` 이 `EDITED` 가 된다. `PENDING` 이던 항목이 합계에 들어오게
    되는데 그것이 `AMT-001-2` 가 말하는 «승인하거나 수정한다» 다 — 사람이 값을
    확인해 고쳤으면 그 자체가 승인이다.

    ### 음수를 막는 이유

    문서에 적힌 금액과 단가는 음수가 아니다. 감액은 별도 문서(변경계약서)의 항목으로
    들어오고, 이 컬럼에 음수를 넣으면 합계가 조용히 줄어든다. `unit_price` 는 DB
    CHECK(`ck_amount_unit_price`)도 같은 조건이라 여기서 막는 것이 그 CHECK 과
    같은 방향이다.
    """

    quantity: Decimal | None = Field(default=None, ge=0)
    unit: str | None = Field(default=None, max_length=30)
    unit_price: int | None = Field(default=None, ge=0)
    # 문서에 적힌 금액. 이것을 고치면 문서의 오류가 감춰지므로 화면에서 마지막
    # 선택임을 알린다. 그래도 막지는 않는다 — 어느 쪽이 맞는지는 사람이 정한다.
    amount: int | None = Field(default=None, ge=0)
    category: AmountCategory | None = None

    @model_validator(mode="after")
    def require_change(self):
        if not self.model_fields_set:
            raise ValueError("고칠 값을 하나 이상 보내야 합니다.")
        return self
