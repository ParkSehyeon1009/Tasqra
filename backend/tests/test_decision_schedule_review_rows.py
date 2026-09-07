from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from app.services.decision_schedule_review_service import DecisionScheduleReviewService


def _common(**values):
    defaults = dict(
        id=1, document_id=2, title="항목", evidence_text="원문", confidence=Decimal("0.9"),
        reason="근거", decision="PENDING", decided_by=None, decided_at=None,
        source_text_revision=1,
    )
    defaults.update(values)
    return SimpleNamespace(**defaults)


def test_schedule_row_includes_semantic_metadata():
    item = _common(
        kind="DEADLINE", starts_on=None, ends_on=date(2026, 9, 30),
        starts_time=None, ends_time=None, relative_expression="계약 후 10일 이내",
        temporal_type="RELATIVE", precision="DAY", anchor_event="계약일",
        calendar_rule=None, condition="계약 체결 시", tentative=False,
    )

    row = DecisionScheduleReviewService._schedule_row(item, "과업지시서.hwpx", 1)

    assert row.temporal_type == "RELATIVE"
    assert row.precision == "DAY"
    assert row.anchor_event == "계약일"
    assert row.condition == "계약 체결 시"
    assert row.tentative is False


def test_decision_row_includes_decision_type():
    item = _common(
        content="선정했다.", status="DECIDED", decision_type="SELECTION",
        superseded_by=None, decided_on=None,
    )

    row = DecisionScheduleReviewService._decision_row(item, "결과보고서.pdf", 1)

    assert row.decision_type == "SELECTION"
