# =============================================================================
# 이 파일의 책임: 금액 계산을 전담한다. 항목 합계, 부가세 분리, 문서에 적힌
#   합계와의 대조(AMT-03), 수량x단가 검산, 원가 구분별·프로젝트 단위 집계
#   (AMT-06)를 수행한다.
# 다른 파일과의 관계: schemas/amount.py의 AmountExtractionOut을 입력으로 받는다.
#   services/amount_normalizer.py가 정규화하고 스키마가 검증한 값만 들어온다.
#   여기 결과를 amount_items 테이블과 화면(AMT-17 계산식 표시)이 쓴다.
# Spring 비교: 순수 도메인 서비스다. @Service 이지만 Repository를 주입받지 않는
#   계산 전용 클래스에 해당한다. 스프링에서도 이런 계층은 @SpringBootTest 없이
#   순수 JUnit으로 테스트한다. 여기서도 DB·컨테이너 없이 pytest로 검증된다.
#
# 이 모듈의 원칙 세 개
#   1. 순수 함수만 담는다. DB·네트워크·AI를 부르지 않는다. 같은 입력에 항상
#      같은 결과를 낸다(AMT-06 완료 판정 기준).
#   2. 부가세(VAT)를 항목 합계에서 제외한다. 포함하면 이중으로 더해진다.
#      합계 대조가 틀리는 가장 흔한 원인이다.
#   3. 문서에 적힌 금액이 틀려 보여도 고치지 않는다. 문서가 3 x 9,500,000 =
#      28,000,000 이라고 적어놨으면 그대로 읽고 불일치로 보고한다. 코드가
#      고쳐버리면 오류가 숨어서 AMT-03이 무의미해진다.
#
# float를 쓰지 않는다. 금액은 int, 수량은 Decimal이다. 부동소수점으로 더하면
#   합계에 오차가 생기고, 그 오차가 문서와의 차액과 섞여 구분되지 않는다.
# =============================================================================

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Iterable

from app.models.enums import AmountCategory
from app.schemas.amount import AmountExtractionOut, AmountItemOut

@dataclass(frozen=True)
class TotalCheck:
    """합계 대조 결과 (AMT-03).

    difference와 matches를 나눠 둔 이유가 있다. stated_total이 없는 문서는
    "대조 불가"이고, 값이 다른 문서는 "불일치"다. 둘은 사용자에게 다르게
    보여야 한다. 앞은 문서에 합계가 없는 정상 상황이고, 뒤는 확인이 필요한
    문제다. 하나로 묶으면 합계가 없는 문서를 오류로 표시하게 된다.
    """

    item_total: int           # 부가세를 제외한 항목 합계
    vat_total: int            # 부가세 항목 합계
    stated_total: int | None  # 문서에 적힌 합계
    difference: int | None    # item_total - stated_total. 대조 불가면 None
    matches: bool             # 차이가 0인가. 대조 불가면 False

    @property
    def comparable(self) -> bool:
        """대조가 가능한 상태인가. False면 문서에 합계가 없다는 뜻이다."""
        return self.stated_total is not None

    @property
    def total_with_vat(self) -> int:
        return self.item_total + self.vat_total

@dataclass(frozen=True)
class LineCheck:
    """행 단위 검산 결과. 수량x단가와 금액이 맞는지."""

    item_name: str
    expected: int | None   # 수량 x 단가. 계산할 수 없으면 None
    actual: int            # 문서에 적힌 금액
    difference: int | None
    matches: bool | None   # None = 검사 불가 (수량이나 단가가 없다)

def _is_vat(item: AmountItemOut) -> bool:
    return item.category == AmountCategory.VAT

def sum_items(items: Iterable[AmountItemOut]) -> int:
    """부가세를 제외한 항목 합계.

    VAT를 빼는 것이 이 함수의 존재 이유다. 부가세는 공급가액에서 파생된
    값이라 항목들과 같은 층이 아니다. 함께 더하면 세금이 두 번 계산된다.
    """
    return sum(item.amount for item in items if not _is_vat(item))

def sum_vat(items: Iterable[AmountItemOut]) -> int:
    """부가세 항목 합계."""
    return sum(item.amount for item in items if _is_vat(item))

def check_total(extraction: AmountExtractionOut) -> TotalCheck:
    """항목 합계와 문서에 적힌 합계를 대조한다 (AMT-03).

    이 프로젝트에서 정확도를 수치로 증명할 수 있는 유일한 기능이다.
    요약이나 결정사항은 AI가 맞게 뽑았는지 확인할 방법이 없지만, 금액은
    재계산해서 대조된다.
    """
    item_total = sum_items(extraction.items)
    vat_total = sum_vat(extraction.items)
    stated = extraction.stated_total

    if stated is None:
        return TotalCheck(item_total, vat_total, None, None, False)

    difference = item_total - stated
    return TotalCheck(item_total, vat_total, stated, difference, difference == 0)

def verify_line(item: AmountItemOut) -> LineCheck:
    """수량 x 단가가 금액과 맞는지 검산한다.

    둘 중 하나라도 없으면 검사할 수 없다(matches=None). 제경비처럼 비율로
    산정된 항목은 수량·단가가 원래 없다.

    불일치해도 amount를 고치지 않는다. 문서가 틀렸다는 사실을 그대로 보고한다.
    """
    if item.quantity is None or item.unit_price is None:
        return LineCheck(item.item_name, None, item.amount, None, None)

    expected_exact = item.quantity * Decimal(item.unit_price)
    expected = int(expected_exact.quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    difference = expected - item.amount
    return LineCheck(item.item_name, expected, item.amount, difference,
                     difference == 0)

def verify_lines(items: Iterable[AmountItemOut]) -> list[LineCheck]:
    return [verify_line(item) for item in items]

def aggregate_by_category(items: Iterable[AmountItemOut]) -> dict[str, int]:
    """원가 구분별 합계. VAT도 별도 키로 포함한다.

    구분이 없는 항목(category=None)은 OTHER로 모은다. 버리지 않는 이유는
    합계에서 빠지면 대조가 틀리기 때문이다.
    """
    result: dict[str, int] = {}
    for item in items:
        key = item.category.value if item.category else AmountCategory.OTHER.value
        result[key] = result.get(key, 0) + item.amount
    return result

def aggregate_project(
    extractions: Iterable[AmountExtractionOut],
) -> dict[str, object]:
    """여러 문서의 금액을 프로젝트 단위로 합친다 (AMT-06).

    통화가 섞여 있으면 ValueError를 던진다. 호출부가
    ErrorCode.CURRENCY_MISMATCH(409)로 바꿔서 응답한다. 환율을 여기서
    적용하지 않는 이유는 어느 시점 환율인지에 따라 결과가 달라져서
    "같은 입력에 같은 결과"가 깨지기 때문이다.

    문서가 하나도 없으면 빈 집계를 돌려준다. 오류가 아니다. 호출부가
    NO_APPROVED_AMOUNTS로 판단할지는 별개다.
    """
    extractions = list(extractions)

    currencies = {e.currency for e in extractions if e.items}
    if len(currencies) > 1:
        raise ValueError(f"통화가 섞여 있어 집계할 수 없다: {sorted(currencies)}")

    currency = currencies.pop() if currencies else "KRW"

    by_category: dict[str, int] = {}
    item_total = 0
    vat_total = 0

    for extraction in extractions:
        item_total += sum_items(extraction.items)
        vat_total += sum_vat(extraction.items)
        for key, value in aggregate_by_category(extraction.items).items():
            by_category[key] = by_category.get(key, 0) + value

    return {
        "currency": currency,
        "item_total": item_total,
        "vat_total": vat_total,
        "total_with_vat": item_total + vat_total,
        "by_category": by_category,
        "document_count": len(extractions),
    }
