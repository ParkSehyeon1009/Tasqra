# =============================================================================
# 이 파일의 책임: 프로젝트 금액 현황(AMT-002-2 집계 · AMT-002-1 검산)을 DB 없이
#   검증한다. 계산 자체는 test_amount_calculator.py 가 이미 22개로 덮고 있으므로,
#   여기서는 **DB 행을 계산기에 넘기는 경계**를 본다. 조용히 틀리는 곳이 거기다.
#
#   검사하는 것
#     ① 승인된 항목만 세는가 (AMT-001-2: 승인 전에는 어디에도 반영하지 않는다)
#     ② 금액이 NULL 인 항목을 0 으로 만들지 않고 건수로 알리는가
#     ③ DB 의 문자열 category 를 Enum 으로 바꾸는가 (안 하면 AttributeError)
#     ④ Decimal 을 int 로 바꾸며 잘라내지 않는가
#     ⑤ 부가세를 항목 합계에서 빼는가
#     ⑥ 검산 불일치를 고치지 않고 보고하는가
#     ⑦ 통화가 섞이면 막는가 (한 문서 안에서 섞인 경우까지)
#     ⑧ 같은 입력이면 같은 결과가 나오는가 (AMT-002-2 완료 판정)
#
# 다른 파일과의 관계: services/amount_summary_service.py 를 검증한다.
#   리포지토리는 MagicMock 이다 — test_deliverable_preview.py 와 같은 방식.
#
# Spring 비교: Mockito 로 Repository 를 스텁하고 Service 만 단위 검증.
# =============================================================================

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.core.error_codes import ErrorCode
from app.core.exceptions import BusinessError
from app.repositories.amount_repository import APPROVED_DECISIONS
from app.services.amount_summary_service import AmountSummaryService


def item(
    item_id,
    *,
    name="특급기술자",
    category="DIRECT_LABOR",
    quantity=None,
    unit_price=None,
    amount="1000000",
    currency="KRW",
):
    """amount_items 한 행을 흉내낸다.

    금액을 문자열로 받아 Decimal 로 바꾸는 이유: 컬럼이 Numeric(18,2) 라
    SQLAlchemy 가 Decimal 을 준다. float 로 쓰면 테스트가 실제와 달라진다.
    """
    return SimpleNamespace(
        id=item_id,
        item_name=name,
        category=category,
        quantity=None if quantity is None else Decimal(quantity),
        unit_price=None if unit_price is None else Decimal(unit_price),
        amount=None if amount is None else Decimal(amount),
        currency=currency,
    )


def service(rows):
    """rows: [(항목, 문서id, 파일명)] — 리포지토리가 돌려주는 모양 그대로."""
    repo = MagicMock()
    repo.list_project_items.return_value = rows
    return AmountSummaryService(repo), repo


def one(*items, document_id=1, filename="제안요청서.pdf"):
    return [(each, document_id, filename) for each in items]


# --- ① 승인된 항목만 --------------------------------------------------------

def test_only_approved_decisions_are_counted():
    """승인 상태 필터는 리포지토리가 건다. 서비스는 그 상수를 응답에 알린다."""
    svc, _ = service(one(item(1)))
    assert svc.summarize(7).included_decisions == ["APPROVED", "EDITED"]


def test_approved_decisions_constant_excludes_pending_and_rejected():
    """PENDING·REJECTED 가 섞이면 승인 전 값이 합계에 반영된다."""
    assert "PENDING" not in APPROVED_DECISIONS
    assert "REJECTED" not in APPROVED_DECISIONS
    assert set(APPROVED_DECISIONS) == {"APPROVED", "EDITED"}


def test_repository_is_asked_for_the_requested_project():
    svc, repo = service([])
    svc.summarize(42)
    repo.list_project_items.assert_called_once_with(42)


# --- ② 금액이 NULL 인 항목 --------------------------------------------------

def test_null_amount_is_excluded_and_reported():
    """문서에 금액이 안 적힌 항목. 건수로 알린다."""
    svc, _ = service(one(item(1, amount="500"), item(2, amount=None)))
    summary = svc.summarize(7)
    assert summary.item_total == 500
    assert summary.excluded_no_amount == 1
    assert summary.included_item_count == 1


def test_null_amount_is_not_treated_as_zero():
    """0 으로 더하면 합계는 같지만 '모른다' 가 사라진다. 건수로 드러나야 한다."""
    svc, _ = service(one(item(1, amount="500"), item(2, amount=None)))
    only_one = svc.summarize(7)
    svc2, _ = service(one(item(1, amount="500"), item(2, amount="0")))
    with_zero = svc2.summarize(7)

    assert only_one.item_total == with_zero.item_total == 500
    # 합계가 같아도 이 둘은 구별돼야 한다.
    assert only_one.excluded_no_amount == 1
    assert with_zero.excluded_no_amount == 0
    assert only_one.included_item_count != with_zero.included_item_count


def test_all_amounts_null_gives_zero_total_not_error():
    svc, _ = service(one(item(1, amount=None), item(2, amount=None)))
    summary = svc.summarize(7)
    assert summary.item_total == 0
    assert summary.excluded_no_amount == 2
    # 금액 항목이 하나도 집계되지 않았으므로 문서도 세지 않는다.
    assert summary.document_count == 0


# --- ③ 문자열 category 를 Enum 으로 -----------------------------------------

def test_string_category_from_db_does_not_crash():
    """aggregate_by_category 가 category.value 를 부른다. str 이면 AttributeError."""
    svc, _ = service(one(item(1, category="DIRECT_LABOR", amount="100")))
    summary = svc.summarize(7)
    assert [(row.category, row.amount) for row in summary.by_category] == [
        ("DIRECT_LABOR", 100)
    ]


def test_null_category_goes_to_other():
    """구분이 없는 항목을 버리면 합계가 대조와 어긋난다."""
    svc, _ = service(one(item(1, category=None, amount="300")))
    summary = svc.summarize(7)
    assert [(row.category, row.amount) for row in summary.by_category] == [
        ("OTHER", 300)
    ]


def test_unknown_category_raises_instead_of_silently_becoming_other():
    """DB CHECK 와 Enum 이 어긋난 상황이다. OTHER 로 섞으면 합계가 틀린 채 그럴듯해진다."""
    svc, _ = service(one(item(1, category="NOT_A_REAL_CATEGORY", amount="100")))
    with pytest.raises(ValueError):
        svc.summarize(7)


# --- ④ Decimal → int -------------------------------------------------------

def test_decimal_amount_is_converted_without_truncation():
    svc, _ = service(one(item(1, amount="9500000.00")))
    assert svc.summarize(7).item_total == 9_500_000


def test_fractional_amount_is_rounded_not_floored():
    """잘라내면 항목마다 최대 1원이 사라져 합계가 항목 수만큼 어긋난다."""
    svc, _ = service(one(item(1, amount="100.50"), item(2, amount="200.50")))
    # ROUND_HALF_UP: 101 + 201
    assert svc.summarize(7).item_total == 302


# --- ⑤ 부가세 --------------------------------------------------------------

def test_vat_is_excluded_from_item_total():
    """부가세를 항목과 함께 더하면 세금이 두 번 계산된다."""
    svc, _ = service(one(
        item(1, category="DIRECT_LABOR", amount="1000"),
        item(2, category="VAT", amount="100"),
    ))
    summary = svc.summarize(7)
    assert summary.item_total == 1000
    assert summary.vat_total == 100
    assert summary.total_with_vat == 1100


def test_vat_still_appears_in_category_breakdown():
    """합계에서는 빠지지만 구분별 내역에는 남는다 — 사라지면 대조가 안 된다."""
    svc, _ = service(one(
        item(1, category="DIRECT_LABOR", amount="1000"),
        item(2, category="VAT", amount="100"),
    ))
    categories = dict(
        (row.category, row.amount) for row in svc.summarize(7).by_category
    )
    assert categories == {"DIRECT_LABOR": 1000, "VAT": 100}


# --- ⑥ 검산 ---------------------------------------------------------------

def test_line_mismatch_is_reported_not_fixed():
    """문서가 3 x 100 = 400 이라고 적어놨으면 그대로 읽고 불일치로 보고한다."""
    svc, _ = service(one(
        item(1, name="중급기술자", quantity="3", unit_price="100", amount="400")
    ))
    summary = svc.summarize(7)

    assert len(summary.line_mismatches) == 1
    mismatch = summary.line_mismatches[0]
    assert (mismatch.expected, mismatch.actual, mismatch.difference) == (300, 400, -100)
    assert mismatch.item_name == "중급기술자"
    # 금액을 고치지 않는다 — 합계는 문서에 적힌 값 그대로다.
    assert summary.item_total == 400


def test_matching_line_produces_no_mismatch():
    svc, _ = service(one(item(1, quantity="3", unit_price="100", amount="300")))
    assert svc.summarize(7).line_mismatches == []


def test_missing_quantity_or_price_is_unverifiable_not_mismatch():
    """제경비·기술료는 비율로 산정돼 수량·단가가 원래 없다. 오류가 아니다."""
    svc, _ = service(one(
        item(1, category="OVERHEAD", amount="500"),
        item(2, category="TECH_FEE", quantity="1", unit_price=None, amount="200"),
    ))
    summary = svc.summarize(7)
    assert summary.unverifiable_line_count == 2
    assert summary.line_mismatches == []


def test_mismatch_points_at_the_document():
    """어느 문서의 어느 항목인지 가리켜야 사용자가 확인할 수 있다."""
    svc, _ = service(
        one(item(9, quantity="2", unit_price="50", amount="120"),
            document_id=31, filename="원가계산서.xlsx")
    )
    mismatch = svc.summarize(7).line_mismatches[0]
    assert (mismatch.item_id, mismatch.document_id, mismatch.filename) == (
        9, 31, "원가계산서.xlsx"
    )


# --- ⑦ 통화 ---------------------------------------------------------------

def test_mixed_currency_across_documents_is_rejected():
    svc, _ = service(
        one(item(1, amount="100", currency="KRW"), document_id=1)
        + one(item(2, amount="100", currency="USD"), document_id=2)
    )
    with pytest.raises(BusinessError) as raised:
        svc.summarize(7)
    assert raised.value.error_code is ErrorCode.CURRENCY_MISMATCH


def test_mixed_currency_inside_one_document_is_also_rejected():
    """계산기의 통화 검사는 문서 단위다. DB 는 통화를 항목마다 들고 있어서
    한 문서 안에서 섞이면 그 검사를 빠져나간다."""
    svc, _ = service(one(
        item(1, amount="100", currency="KRW"),
        item(2, amount="100", currency="USD"),
    ))
    with pytest.raises(BusinessError) as raised:
        svc.summarize(7)
    assert raised.value.error_code is ErrorCode.CURRENCY_MISMATCH


def test_currency_of_items_is_reported():
    svc, _ = service(one(item(1, amount="100", currency="USD")))
    assert svc.summarize(7).currency == "USD"


def test_empty_project_defaults_to_krw_without_error():
    """빈 프로젝트에서 오류 화면이 뜨면 고장으로 읽힌다."""
    svc, _ = service([])
    summary = svc.summarize(7)
    assert summary.currency == "KRW"
    assert (summary.item_total, summary.vat_total, summary.total_with_vat) == (0, 0, 0)
    assert summary.by_category == []
    assert summary.document_count == 0


# --- ⑧ 같은 입력이면 같은 결과 ---------------------------------------------

def test_category_order_is_fixed_by_amount_desc():
    """dict 순서는 삽입 순서다. 항목이 오는 순서가 바뀌면 화면 줄 순서가 바뀐다."""
    svc, _ = service(one(
        item(1, category="EXPENSE", amount="100"),
        item(2, category="DIRECT_LABOR", amount="900"),
        item(3, category="OVERHEAD", amount="500"),
    ))
    assert [row.category for row in svc.summarize(7).by_category] == [
        "DIRECT_LABOR", "OVERHEAD", "EXPENSE"
    ]


def test_same_amount_breaks_tie_by_category_name():
    svc, _ = service(one(
        item(1, category="OVERHEAD", amount="100"),
        item(2, category="EXPENSE", amount="100"),
    ))
    assert [row.category for row in svc.summarize(7).by_category] == [
        "EXPENSE", "OVERHEAD"
    ]


def test_document_count_counts_documents_with_amounts():
    svc, _ = service(
        one(item(1, amount="100"), document_id=1)
        + one(item(2, amount="200"), item(3, amount="300"), document_id=2)
    )
    summary = svc.summarize(7)
    assert summary.document_count == 2
    assert summary.included_item_count == 3
    assert summary.item_total == 600
