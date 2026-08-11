# =============================================================================
# 이 파일의 책임: 금액 정규화(amount_normalizer)와 비용 산출 엔진
#   (amount_calculator)을 검증한다. DB·AI·네트워크를 쓰지 않으므로 컨테이너
#   기동 없이도 돌아간다.
# 다른 파일과의 관계: services/amount_normalizer.py 와
#   services/amount_calculator.py 를 대상으로 한다. 입력은
#   schemas/amount.py 의 AmountExtractionOut 이다.
# Spring 비교: 순수 JUnit 테스트다. @SpringBootTest 없이 도메인 로직만 검증하는
#   계층에 해당한다. 컨텍스트를 띄우지 않아 빠르다.
#
# 여기서 가장 중요한 테스트는 test_total_mismatch_is_reported_not_fixed 다.
#   문서에 적힌 합계가 틀렸을 때 코드가 고치지 않고 차액을 보고하는지 확인한다.
#   고쳐버리면 AMT-03(합계 대조)이 무의미해진다.
# =============================================================================

from decimal import Decimal

import pytest

from app.models.enums import AmountCategory, DocumentType
from app.schemas.amount import AmountExtractionOut
from app.services.amount_calculator import (
    aggregate_by_category,
    aggregate_project,
    check_total,
    sum_items,
    sum_vat,
    verify_line,
    verify_lines,
)
from app.services.amount_normalizer import (
    normalize_number,
    normalize_payload,
    normalize_quantity,
)

# ── 테스트 데이터 만들기 ──────────────────────────────────────────────────────

def item(name, amount, category=None, quantity=None, unit_price=None):
    return {
        "item_name": name,
        "amount": amount,
        "category": category,
        "quantity": quantity,
        "unit_price": unit_price,
        "source_quote": f"{name} 관련 원문",
        "confidence": 0.9,
        "reason": "테스트 데이터",
    }

def extraction(items, stated_total=None, currency="KRW",
               document_type="COST_SHEET"):
    return AmountExtractionOut.model_validate({
        "document_type": document_type,
        "currency": currency,
        "stated_total": stated_total,
        "items": items,
    })

@pytest.fixture
def cost_sheet():
    """합계가 맞는 산출내역서. 공급가액 97,500,000 + 부가세 9,750,000."""
    return extraction(
        stated_total=97_500_000,
        items=[
            item("특급기술자", 28_500_000, "DIRECT_LABOR", 3, 9_500_000),
            item("고급기술자", 43_200_000, "DIRECT_LABOR", 6, 7_200_000),
            item("제경비", 25_800_000, "OVERHEAD"),
            item("부가세", 9_750_000, "VAT"),
        ],
    )

# ── 정규화 ───────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("raw, expected", [
    ("9,500,000원", 9_500_000),
    ("  9500000  ", 9_500_000),
    ("1,234,567 KRW", 1_234_567),
    (9_500_000, 9_500_000),
    (9_500_000.0, 9_500_000),
    ("", None),
    (None, None),
    ("-", None),
    ("미정", None),
    ("없음", None),
    ("약 1억", None),      # 해석하지 않는다. 추측이 되기 때문이다
    (-500, None),          # 금액에 음수를 허용하지 않는다
    ("9,500,000.5", None), # 원 단위가 아니면 버린다
    (True, None),          # bool 이 1 로 들어가지 않게
])
def test_normalize_number(raw, expected):
    assert normalize_number(raw) == expected

@pytest.mark.parametrize("raw, expected", [
    ("3", Decimal("3")),
    ("1.5", Decimal("1.5")),
    ("3인월", Decimal("3")),
    ("1.5 M/M", Decimal("1.5")),
    ("1,200개", Decimal("1200")),
    (3, Decimal("3")),
    ("", None),
    (None, None),
    (-2, None),
])
def test_normalize_quantity(raw, expected):
    assert normalize_quantity(raw) == expected

def test_normalize_payload_does_not_mutate_source():
    source = {
        "stated_total": "97,500,000원",
        "items": [item("특급", "28,500,000", "DIRECT_LABOR", "3인월", "9,500,000")],
    }
    source["items"][0]["unit"] = ""

    result = normalize_payload(source)

    assert result["stated_total"] == 97_500_000
    assert result["items"][0]["amount"] == 28_500_000
    assert result["items"][0]["quantity"] == Decimal("3")
    assert result["items"][0]["unit"] is None   # 빈 문자열은 None 으로
    # 원본이 그대로여야 한다
    assert source["stated_total"] == "97,500,000원"
    assert source["items"][0]["amount"] == "28,500,000"

def test_normalized_payload_passes_schema(cost_sheet):
    raw = {
        "document_type": "COST_SHEET",
        "stated_total": "97,500,000원",
        "items": [item("특급", "28,500,000", "DIRECT_LABOR", "3인월", "9,500,000")],
    }
    parsed = AmountExtractionOut.model_validate(normalize_payload(raw))
    assert parsed.items[0].amount == 28_500_000
    assert parsed.document_type is DocumentType.COST_SHEET

# ── 부가세 분리 ──────────────────────────────────────────────────────────────

def test_vat_is_excluded_from_item_total(cost_sheet):
    """부가세를 항목 합계에 넣으면 이중으로 더해진다."""
    assert sum_items(cost_sheet.items) == 97_500_000
    assert sum_vat(cost_sheet.items) == 9_750_000
    # VAT 를 포함했다면 107,250,000 이 나온다
    assert sum_items(cost_sheet.items) != 107_250_000

def test_sum_items_ignores_only_vat_category():
    items = extraction([
        item("A", 1000, "DIRECT_LABOR"),
        item("B", 2000, "OTHER"),
        item("세금", 300, "VAT"),
        item("구분없음", 500),           # category=None
    ]).items
    assert sum_items(items) == 3500
    assert sum_vat(items) == 300

# ── 합계 대조 (AMT-03) ───────────────────────────────────────────────────────

def test_total_matches(cost_sheet):
    result = check_total(cost_sheet)
    assert result.item_total == 97_500_000
    assert result.vat_total == 9_750_000
    assert result.difference == 0
    assert result.matches is True
    assert result.comparable is True
    assert result.total_with_vat == 107_250_000

def test_total_mismatch_is_reported_not_fixed():
    """이 파일에서 가장 중요한 테스트.

    문서가 10,000,000 + 5,000,000 = 14,000,000 이라고 잘못 적어놨다.
    코드는 문서 값을 고치지 않고 차액 1,000,000 을 보고해야 한다.
    고쳐버리면 AMT-03 이 무의미해진다.
    """
    doc = extraction(
        stated_total=14_000_000,
        items=[item("A", 10_000_000), item("B", 5_000_000)],
    )
    result = check_total(doc)

    assert result.item_total == 15_000_000
    assert result.stated_total == 14_000_000   # 문서 값을 고치지 않았다
    assert result.difference == 1_000_000
    assert result.matches is False
    assert result.comparable is True

def test_total_not_comparable_when_no_stated_total():
    """대조 불가와 불일치는 다른 상태다.

    회의록처럼 합계가 없는 문서를 오류로 표시하면 안 된다.
    """
    doc = extraction([item("X", 500_000)], document_type="MEETING_NOTES")
    result = check_total(doc)

    assert result.difference is None
    assert result.matches is False
    assert result.comparable is False

def test_empty_document_has_zero_total():
    doc = extraction([], document_type="MEETING_NOTES")
    result = check_total(doc)
    assert result.item_total == 0
    assert result.vat_total == 0
    assert result.comparable is False

# ── 행 검산 ──────────────────────────────────────────────────────────────────

def test_verify_line_matches(cost_sheet):
    result = verify_line(cost_sheet.items[0])
    assert result.expected == 28_500_000
    assert result.difference == 0
    assert result.matches is True

def test_verify_line_detects_document_error():
    """문서에 3 x 9,500,000 = 28,000,000 이라고 적혀 있으면 그대로 읽는다."""
    doc = extraction([item("X", 28_000_000, None, 3, 9_500_000)])
    result = verify_line(doc.items[0])

    assert result.expected == 28_500_000
    assert result.actual == 28_000_000     # 문서 값 그대로
    assert result.difference == 500_000
    assert result.matches is False

def test_verify_line_skips_when_quantity_or_price_missing(cost_sheet):
    """제경비처럼 비율로 산정된 항목은 수량·단가가 없어 검사할 수 없다."""
    overhead = cost_sheet.items[2]
    result = verify_line(overhead)
    assert result.matches is None
    assert result.expected is None

def test_verify_line_handles_decimal_quantity():
    """1.5인월 x 8,000,000 = 12,000,000. float 면 오차가 생긴다."""
    doc = extraction([item("반월", 12_000_000, "DIRECT_LABOR",
                           Decimal("1.5"), 8_000_000)])
    assert verify_line(doc.items[0]).matches is True

def test_verify_lines_returns_all(cost_sheet):
    results = verify_lines(cost_sheet.items)
    assert len(results) == 4
    assert [r.matches for r in results] == [True, True, None, None]

# ── 원가 구분별 집계 ─────────────────────────────────────────────────────────

def test_aggregate_by_category(cost_sheet):
    result = aggregate_by_category(cost_sheet.items)
    assert result == {
        "DIRECT_LABOR": 71_700_000,
        "OVERHEAD": 25_800_000,
        "VAT": 9_750_000,
    }

def test_category_none_goes_to_other():
    items = extraction([item("구분없음", 1000)]).items
    assert aggregate_by_category(items) == {AmountCategory.OTHER.value: 1000}

# ── 프로젝트 집계 (AMT-06) ───────────────────────────────────────────────────

def test_aggregate_project(cost_sheet):
    other = extraction([item("추가", 500_000)], document_type="CONTRACT")
    result = aggregate_project([cost_sheet, other])

    assert result["currency"] == "KRW"
    assert result["item_total"] == 98_000_000
    assert result["vat_total"] == 9_750_000
    assert result["total_with_vat"] == 107_750_000
    assert result["document_count"] == 2
    assert result["by_category"]["DIRECT_LABOR"] == 71_700_000
    assert result["by_category"]["OTHER"] == 500_000

def test_aggregate_project_rejects_mixed_currency(cost_sheet):
    usd = extraction([item("Y", 100)], currency="USD", document_type="ETC")
    with pytest.raises(ValueError, match="통화"):
        aggregate_project([cost_sheet, usd])

def test_aggregate_project_ignores_currency_of_empty_documents(cost_sheet):
    """항목이 없는 문서의 통화는 집계에 영향을 주지 않는다."""
    empty_usd = extraction([], currency="USD", document_type="MEETING_NOTES")
    result = aggregate_project([cost_sheet, empty_usd])
    assert result["currency"] == "KRW"

def test_aggregate_project_with_no_documents():
    result = aggregate_project([])
    assert result["item_total"] == 0
    assert result["document_count"] == 0
    assert result["currency"] == "KRW"

def test_aggregate_is_deterministic(cost_sheet):
    """AMT-06 완료 판정 기준 — 같은 입력이면 항상 같은 결과."""
    other = extraction([item("추가", 500_000)], document_type="CONTRACT")
    first = aggregate_project([cost_sheet, other])
    second = aggregate_project([cost_sheet, other])
    assert first == second
