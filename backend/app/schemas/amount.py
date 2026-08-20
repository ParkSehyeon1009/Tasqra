# =============================================================================
# 이 파일의 책임: 금액 분석기(AMT-001-1)가 반환한 JSON을 받는 Pydantic 모델을
#   정의한다. 모델 응답이 규격에 맞는지 여기서 걸러내고, 어긋나면 호출부가
#   ErrorCode.AI_INVALID_RESPONSE(502)로 BusinessError를 던져 재시도한다.

# 다른 파일과의 관계: services/amount_normalizer.py가 문자열 숫자를 정수로
#   바꾼 뒤 이 모델로 검증한다. 검증을 통과한 값은
#   services/amount_calculator.py가 계산에 쓰고 amount_items 테이블에 저장된다.
#   값 목록은 models/enums.py의 DocumentType · AmountCategory를 따른다.
# Spring 비교: @RequestBody DTO + Bean Validation(@NotNull·@Min·@Size)과 같다.
#   Spring은 어노테이션으로 제약을 붙이지만 Pydantic은 필드 타입과 Field()로
#   선언하고, 위반 시 ValidationError를 던진다.
#
# 이 모듈의 원칙 — 모델은 뽑기만 하고 계산하지 않는다.
#   stated_total은 "문서에 적힌 합계"이고 items의 합과 별개로 받는다. 둘을
#   대조하는 것이 AMT-03이고, 이 프로젝트에서 정확도를 수치로 증명할 수 있는
#   유일한 기능이다. 모델이 미리 더해서 주면 대조할 대상이 사라진다.
# =============================================================================

from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field, model_validator

from app.models.enums import AmountCategory, DocumentType

class AmountItemOut(BaseModel):
    """금액 항목 하나. 문서에 적힌 값만 담고, 없는 값은 None으로 둔다.

    amount만 필수다. 수량·단위·단가는 비율로 산정된 항목(제경비 등)에서
    문서에 아예 없는 경우가 많다. 빈 문자열이나 0을 쓰지 않는 이유는 0이
    "금액이 0원"이라는 다른 뜻이기 때문이다.
    """

    item_name: str = Field(min_length=1, max_length=300,
                           description="문서에 적힌 항목명 그대로")
    category: AmountCategory | None = Field(
        default=None, description="원가 구분. VAT 구분이 합계 정확도에 직결된다")

    quantity: Decimal | None = Field(default=None, ge=0,
                                     description="1.5인월 같은 소수 허용")
    unit: str | None = Field(default=None, max_length=20)

    # 금액은 원 단위 정수다. float를 쓰면 합계에 오차가 생긴다.
    # quantity만 Decimal인 이유는 인월 같은 소수 수량이 실제로 나오기 때문이다.
    unit_price: int | None = Field(default=None, ge=0)
    amount: int = Field(ge=0, description="문서에 적힌 금액. 계산해서 만들지 않는다")

    period_from: date | None = None
    period_to: date | None = None

    source_quote: str = Field(min_length=1, max_length=1000,
                              description="원문을 그대로 인용. 검증의 근거")
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str = Field(min_length=1, max_length=1000,
                        description="왜 이렇게 판단했는지")

    @model_validator(mode="after")
    def check_period_order(self) -> "AmountItemOut":
        if self.period_from and self.period_to and self.period_from > self.period_to:
            raise ValueError(
                f"기간이 거꾸로다: {self.period_from} > {self.period_to}")
        return self

class AmountExtractionOut(BaseModel):
    """문서 한 건의 금액 추출 결과.

    금액이 없는 문서(회의록 등)는 오류가 아니다. items를 빈 배열로 두고
    notes에 사유를 적는다.
    """

    document_type: DocumentType
    currency: str = Field(default="KRW", pattern=r"^[A-Z]{3}$",
                          description="ISO 통화 코드")

    # 문서에 적힌 합계. 항목 합계와 대조할 상대편이다(AMT-002-1).
    # 없으면 None이고, 그때는 "대조 불가"이지 "불일치"가 아니다.
    stated_total: int | None = Field(default=None, ge=0)

    items: list[AmountItemOut] = Field(default_factory=list)
    notes: str | None = Field(default=None,
                              description="판단이 어려웠던 점. 금액이 없으면 사유")


    # 통화 일치 검사는 여기서 하지 않는다. 문서 한 건에는 통화가 하나이므로
    # 검사할 것이 없고, 여러 문서를 합칠 때만 문제가 된다. 그 검사는
    # services/amount_calculator.aggregate_project() 가 담당한다.


    def has_amounts(self) -> bool:
        return bool(self.items)
