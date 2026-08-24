# =============================================================================
# 이 파일의 책임: 금액 계산기가 요구하는 **최소 모양**을 계약으로 정의한다.
#   계산기는 이 다섯(또는 셋) 속성만 읽고, 그 값이 LLM 응답에서 왔는지 DB 행에서
#   왔는지 알지 않는다.
#
# 다른 파일과의 관계: services/amount_calculator.py 가 이 타입에만 의존한다.
#   schemas/amount.py 의 AmountItemOut·AmountExtractionOut 이 이 모양을 만족한다
#   (LLM 추출 경로). services/amount_summary_service.py 의 내부 dataclass 도
#   만족한다 (DB 조회 경로). embedding/protocol.py · rerank/protocol.py 와 같은
#   방식이다.
#
# Spring 비교: Java interface 다. 구현 클래스가 implements 를 선언하지 않아도
#   모양이 맞으면 통과하는 점만 다르다(구조적 타이핑).
#
# 왜 이것이 필요한가 — DB 행으로는 AmountItemOut 을 만들 수 없다
#   AmountItemOut 은 **LLM 응답 검증용** 스키마다. 그래서 source_quote 와
#   confidence 를 필수로 요구한다(추출기는 근거와 확신도를 반드시 낸다).
#   그런데 amount_items 테이블은 그 둘을 NULL 로 허용한다. 사람이 손으로 넣은
#   항목에는 원문 근거가 없을 수 있어서다.
#
#   그래서 DB 행을 AmountItemOut 으로 바꾸려 하면 **ValidationError 가 난다.**
#   억지로 맞추려면 없는 근거 문장을 지어내야 하는데, 그것은 "문서에 없는 값은
#   비운다"(AMT-001-1 완료 판정)를 정면으로 어긴다.
#
#   계산기는 그 둘을 아예 쓰지 않는다. 그러니 계산기의 요구를 실제로 쓰는
#   것만큼으로 좁히는 것이 맞다. 타입 힌트를 좁히는 것이므로 **실행 동작은 전혀
#   바뀌지 않는다** — 기존 테스트 22개가 그대로 통과한다.
# =============================================================================

from __future__ import annotations

from decimal import Decimal
from typing import Protocol, Sequence

from app.models.enums import AmountCategory


class AmountLine(Protocol):
    """금액 항목 한 줄. 계산기가 읽는 것은 이 다섯뿐이다."""

    # 검산 결과에 무엇이 틀렸는지 적기 위해 필요하다.
    item_name: str
    # ⚠️ **문자열이 아니라 Enum 이다.** aggregate_by_category 가 `.value` 를
    #   부르므로 str 을 넣으면 AttributeError 가 난다. DB 는 str 로 저장하므로
    #   조회 경로에서 AmountCategory(...) 로 바꿔서 넘겨야 한다.
    category: AmountCategory | None
    # 비율로 산정된 항목(제경비·기술료)은 수량·단가가 원래 없다.
    quantity: Decimal | None
    unit_price: int | None
    # ⚠️ **None 이 아니다.** 문서에 금액이 안 적힌 항목은 DB 에서 NULL 일 수
    #   있는데, sum() 이 None 을 만나면 TypeError 로 죽는다. 부르는 쪽이 먼저
    #   걸러서 넘긴다 — 0 으로 바꾸면 합계가 조용히 틀린다.
    amount: int


class AmountDocument(Protocol):
    """문서 하나에서 뽑힌 금액. 통화와 문서에 적힌 합계가 여기 붙는다."""

    # 통화가 섞이면 aggregate_project 가 ValueError 를 던진다. 환율을 적용하지
    # 않는 이유는 그 함수 주석에 있다.
    currency: str
    # 문서에 적힌 합계. **DB 에는 이 값이 없다** — amount_items 는 항목만 담고
    # 문서 합계를 저장하지 않는다. 그래서 조회 경로에서는 항상 None 이고
    # check_total 의 대조가 성립하지 않는다. 대조는 추출 시점에만 가능하다.
    stated_total: int | None
    items: Sequence[AmountLine]
