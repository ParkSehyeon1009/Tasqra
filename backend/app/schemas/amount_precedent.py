# =============================================================================
# 이 파일의 책임: 과거 유사 사업 단가 선례 조회(SRH-002-3)의 응답 계약이다.
# 다른 파일과의 관계: services/amount_precedent_service.py 가 채우고
#   api/routes/amount_router.py 가 돌려준다. 값의 출처는 models/amount.py 다.
# Spring 비교: 응답 DTO + Bean Validation 이다. Pydantic 은 검증과 직렬화를
#   한 클래스에서 하므로 @Valid 와 Jackson 설정이 하나로 합쳐진 셈이다.
#
# 금액을 int 가 아니라 Decimal 로 두는 이유
#   amount_items 가 Numeric(18,2) 다. float 로 바꾸면 큰 금액에서 오차가 생기고,
#   조달 금액은 억 단위라 그 오차가 눈에 보인다. JSON 으로는 문자열이 아니라
#   숫자로 나가지만 파이썬 안에서는 Decimal 로 다룬다.
# =============================================================================

from __future__ import annotations

from datetime import date
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class AmountPrecedentItem(BaseModel):
    """선례 한 건. 어느 사업의 어느 문서에서 나온 단가인지까지 담는다."""

    model_config = ConfigDict(from_attributes=True)

    # 출처. 프로젝트·문서를 다시 조회하지 않게 조인으로 함께 담는다.
    project_id: int
    project_name: str
    document_id: int
    document_filename: str

    item_name: str
    category: str | None
    quantity: Decimal | None
    unit: str | None
    # 이 조회의 핵심 값. NULL 인 항목은 애초에 결과에 넣지 않는다.
    unit_price: Decimal
    amount: Decimal | None
    period_from: date | None
    period_to: date | None
    # 원문 인용. "이 숫자가 어디서 나왔나" 를 사람이 확인하는 근거다.
    source_quote: str | None
    # APPROVED 인지 EDITED 인지 보여준다. EDITED 면 사람이 값을 고친 것이라
    # 신뢰도가 다르다.
    decision: str


class AmountPrecedentSummary(BaseModel):
    """선례들의 요약. 추계(estimate)의 출발점이다.

    중앙값을 쓰고 평균을 쓰지 않는다. 선례가 적을 때 한 건의 이상치가 평균을
    끌고 가는데, 조달 단가는 사업 규모에 따라 크게 벌어져서 그 일이 잦다.
    """

    count: int
    min_unit_price: Decimal
    median_unit_price: Decimal
    max_unit_price: Decimal


class AmountPrecedentResponse(BaseModel):
    item_name: str
    # 실제로 찾아본 프로젝트. 현재 프로젝트가 빠져 있는 것을 화면에서 확인할 수
    # 있게 돌려준다. 비어 있으면 "다른 사업이 없다" 는 뜻이다.
    searched_project_ids: list[int]
    # 선례가 없으면 None 이다. 0 을 넣으면 "단가가 0원" 과 구별되지 않는다.
    summary: AmountPrecedentSummary | None = None
    precedents: list[AmountPrecedentItem] = Field(default_factory=list)
