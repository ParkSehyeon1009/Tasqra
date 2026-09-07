# ① 책임: 금액 원시 JSON parser와 PENDING 저장 writer의 경계·멱등성을 검증한다.
# ② 관계: amount_parser, AmountWriter를 순수 입력과 메모리 fake repository로 검사한다.
# ③ Spring 비교: ObjectMapper DTO 테스트와 mock JpaRepository 기반 @Service 단위테스트에 해당한다.

import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.ai.client_protocol import AIResult
from app.analyzers.amount_parser import parse_amount_extraction
from app.analyzers.protocol import AnalyzeResult
from app.core.error_codes import ErrorCode
from app.core.exceptions import BusinessError
from app.models.amount import AmountItem
from app.repositories.amount_repository import AmountRepository
from app.services.amount_writer import AmountWriter


def _item(**overrides):
    value = {
        "item_name": "특급기술자",
        "category": "DIRECT_LABOR",
        "quantity": "3인월",
        "unit": "인월",
        "unit_price": "9,500,000원",
        "amount": "28,500,000원",
        "period_from": None,
        "period_to": None,
        "source_quote": "특급기술자 3인월 28,500,000원",
        "confidence": 0.9,
        "reason": "문서 표의 같은 행",
    }
    value.update(overrides)
    return value


def _payload(**overrides):
    value = {
        "document_type": "COST_SHEET",
        "currency": "KRW",
        "stated_total": "28,500,000원",
        "items": [_item()],
        "notes": None,
    }
    value.update(overrides)
    return value


def _parse(payload):
    return parse_amount_extraction(json.dumps(payload, ensure_ascii=False))


def _assert_invalid(raw: str) -> None:
    with pytest.raises(BusinessError) as exc:
        parse_amount_extraction(raw)
    assert exc.value.error_code is ErrorCode.AI_INVALID_RESPONSE


def test_parser_normalizes_valid_json_and_accepts_ai_result():
    raw = json.dumps(_payload(), ensure_ascii=False)

    parsed = parse_amount_extraction(
        AIResult(text=raw, model_name="amount-model", tokens_in=10)
    )

    assert parsed.stated_total == 28_500_000
    assert parsed.items[0].quantity == 3
    assert parsed.items[0].unit_price == 9_500_000
    assert parsed.items[0].amount == 28_500_000


def test_parser_preserves_explicit_nulls_without_inventing_values():
    parsed = _parse(_payload(
        stated_total=None,
        notes=None,
        items=[_item(
            category=None,
            quantity=None,
            unit=None,
            unit_price=None,
            period_from=None,
            period_to=None,
        )],
    ))

    assert parsed.stated_total is None
    assert parsed.notes is None
    item = parsed.items[0]
    assert item.category is None
    assert item.quantity is None
    assert item.unit is None
    assert item.unit_price is None
    assert item.period_from is None
    assert item.period_to is None
    assert item.amount == 28_500_000


@pytest.mark.parametrize("raw", [
    "```json\n{}\n```",
    '{"document_type": "COST_SHEET",',
    '[{"document_type": "COST_SHEET"}]',
    '{"document_type": "COST_SHEET", "items": [], "stated_total": NaN}',
])
def test_parser_rejects_code_fence_malformed_root_and_nonstandard_json(raw):
    _assert_invalid(raw)


@pytest.mark.parametrize("payload", [
    _payload(unexpected="value"),
    _payload(items=[_item(unexpected="value")]),
])
def test_parser_rejects_unknown_fields(payload):
    _assert_invalid(json.dumps(payload, ensure_ascii=False))


@pytest.mark.parametrize("payload", [
    _payload(stated_total="약 1억원"),
    _payload(items=[_item(amount="28,500,000.5")]),
    _payload(items=[_item(amount=-1)]),
    _payload(items=[_item(unit_price=-1)]),
    _payload(items=[_item(quantity="-1인월")]),
    _payload(items=[_item(quantity="수량 3")]),
    _payload(items=[_item(amount="1원2")]),
    _payload(items=[_item(amount="1,2,3")]),
    _payload(items=[_item(quantity="1e3")]),
    _payload(items=[_item(quantity="1.5.2")]),
])
def test_parser_rejects_invalid_or_negative_numbers(payload):
    _assert_invalid(json.dumps(payload, ensure_ascii=False))


class _AnalysisRepository:
    def __init__(self):
        self.rows = []

    def create(self, row):
        row.id = len(self.rows) + 1
        self.rows.append(row)
        return row


class _AmountRepository:
    def __init__(self, rows=None):
        self.rows = list(rows or [])
        self.next_id = 100

    def delete_pending_items(self, document_id):
        before = len(self.rows)
        self.rows = [
            row for row in self.rows
            if not (row.document_id == document_id and row.decision == "PENDING")
        ]
        return before - len(self.rows)

    def add_items(self, rows):
        for row in rows:
            row.id = self.next_id
            self.next_id += 1
        self.rows.extend(rows)
        return rows


def _result():
    return AnalyzeResult(
        result={"ignored": "writer stores the validated DTO"},
        provider="local",
        model_name="amount-model",
        prompt_version="amount-v1",
        tokens_in=10,
        tokens_out=20,
        latency_ms=30,
    )


def test_writer_maps_validated_values_to_pending_rows_and_revisions():
    analyses = _AnalysisRepository()
    amounts = _AmountRepository()
    writer = AmountWriter(analyses, amounts)
    extraction = _parse(_payload())

    analysis, rows = writer.write(
        document_id=7,
        source_text_revision=12,
        source_ocr_revision=4,
        analyzer_type="amount",
        result=_result(),
        extraction=extraction,
    )

    assert analysis.source_text_revision == 12
    assert analysis.result_json == extraction.model_dump(mode="json")
    assert len(rows) == 1
    row = rows[0]
    assert row.document_id == 7
    assert row.analysis_id == analysis.id
    assert row.source_text_revision == 4
    assert row.decision == "PENDING"
    assert row.decided_by is None
    assert row.decided_at is None
    assert row.quantity == 3
    assert row.unit_price == 9_500_000
    assert row.amount == 28_500_000


def test_duplicate_write_replaces_only_pending_and_preserves_review_history():
    reviewed = [
        SimpleNamespace(id=1, document_id=7, decision="APPROVED"),
        SimpleNamespace(id=2, document_id=7, decision="EDITED"),
        SimpleNamespace(id=3, document_id=7, decision="REJECTED"),
    ]
    old_pending = SimpleNamespace(id=4, document_id=7, decision="PENDING")
    other_pending = SimpleNamespace(id=5, document_id=8, decision="PENDING")
    analyses = _AnalysisRepository()
    amounts = _AmountRepository([*reviewed, old_pending, other_pending])
    writer = AmountWriter(analyses, amounts)
    extraction = _parse(_payload())

    for _ in range(2):
        writer.write(
            document_id=7,
            source_text_revision=12,
            source_ocr_revision=4,
            analyzer_type="amount",
            result=_result(),
            extraction=extraction,
        )

    assert len(analyses.rows) == 2
    assert all(row in amounts.rows for row in reviewed)
    assert other_pending in amounts.rows
    current = [
        row for row in amounts.rows
        if row.document_id == 7 and row.decision == "PENDING"
    ]
    assert len(current) == 1
    assert current[0].analysis_id == analyses.rows[-1].id


def test_writer_keeps_null_fields_and_does_not_calculate_missing_values():
    analyses = _AnalysisRepository()
    amounts = _AmountRepository()
    writer = AmountWriter(analyses, amounts)
    extraction = _parse(_payload(
        stated_total=None,
        items=[_item(quantity=None, unit_price=None)],
    ))

    analysis, rows = writer.write(
        document_id=7,
        source_text_revision=12,
        source_ocr_revision=4,
        analyzer_type="amount",
        result=_result(),
        extraction=extraction,
    )

    assert analysis.result_json["stated_total"] is None
    assert rows[0].quantity is None
    assert rows[0].unit_price is None
    assert rows[0].amount == 28_500_000


def test_real_repository_delete_scope_is_document_pending_only():
    db = MagicMock()
    delete_query = db.query.return_value.filter.return_value
    delete_query.delete.return_value = 2
    repository = AmountRepository(db)

    assert repository.delete_pending_items(7) == 2

    db.query.assert_called_once_with(AmountItem)
    document_condition, decision_condition = db.query.return_value.filter.call_args.args
    assert document_condition.left.key == "document_id"
    assert document_condition.right.value == 7
    assert decision_condition.left.key == "decision"
    assert decision_condition.right.value == "PENDING"
    delete_query.delete.assert_called_once_with(synchronize_session=False)
