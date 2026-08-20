# =============================================================================
# 이 파일의 책임: 산출물 생성 대상 미리보기(DLV-001-2)를 DB 없이 검증한다.
#   완료 판정이 "LLM 호출 전에 건수가 보이고 **대상이 없으면 생성이 방지된다**"
#   이므로, **막는 판정**이 가장 중요한 검사다.
#
#   검사하는 것
#     ① 종류마다 세는 대상이 다른가 (이 기능의 핵심 규칙)
#     ② 대상이 없으면 생성이 막히는가 (완료 판정)
#     ③ 주간 보고서만 기간을 요구하는가
#     ④ 셀 수 없는 것(completed_tasks)을 0 으로 만들지 않는가
#     ⑤ 승인 대기가 생성 가능 판정에 섞이지 않는가
#
# 다른 파일과의 관계: services/deliverable_service.py · schemas/deliverable.py
#   리포지토리는 MagicMock 이다 — test_document_list_queries.py 와 같은 방식.
#
# Spring 비교: Mockito 로 Repository 를 스텁하고 Service 만 단위 검증.
# =============================================================================

from datetime import date
from unittest.mock import MagicMock

import pytest

from app.core.error_codes import ErrorCode
from app.core.exceptions import BusinessError
from app.schemas.deliverable import PreviewCounts
from app.services.deliverable_service import DeliverableService

WEEK = {"period_from": date(2026, 8, 14), "period_to": date(2026, 8, 20)}


def _service(*, documents=0, decisions=0, schedules=0, amounts=0, pending=0,
             open_decisions=0):
    repo = MagicMock()
    repo.count_documents.return_value = documents
    repo.count_schedule_items.return_value = schedules
    repo.count_amount_items.return_value = amounts
    repo.count_pending_suggestions.return_value = pending

    # status 인자에 따라 다른 값을 준다 — 회의 안건은 미결만 센다.
    def decisions_side_effect(project_id, *, since=None, until=None, status=None):
        return open_decisions if status == "PENDING" else decisions

    repo.count_decisions.side_effect = decisions_side_effect
    return DeliverableService(repo), repo


# --- ① 종류마다 세는 대상이 다르다 ------------------------------------------


def test_weekly_report_counts_all_four_kinds():
    service, repo = _service(documents=12, decisions=5, schedules=3, amounts=2)
    out = service.preview(1, kind="WEEKLY_REPORT", **WEEK)
    assert (out.counts.documents, out.counts.decisions,
            out.counts.schedule_items, out.counts.amount_items) == (12, 5, 3, 2)
    # 기간이 리포지토리까지 전달돼야 한다.
    assert repo.count_documents.call_args.kwargs["since"] == WEEK["period_from"]
    assert repo.count_documents.call_args.kwargs["until"] == WEEK["period_to"]


def test_decision_log_counts_only_decisions_without_period():
    """결정사항 대장에 기간을 걸면 '지난주에 정한 것만' 이 되어 대장이 아니게 된다."""
    service, repo = _service(documents=12, decisions=5, schedules=3, amounts=2)
    out = service.preview(1, kind="DECISION_LOG", **WEEK)

    assert out.counts.decisions == 5
    assert (out.counts.documents, out.counts.schedule_items,
            out.counts.amount_items) == (0, 0, 0)
    # 기간을 무시한다 — 날짜를 줬어도 응답에 담기지 않는다.
    assert out.period_from is None and out.period_to is None
    # status 없이(=전부) 센다.
    assert repo.count_decisions.call_args.kwargs.get("status") is None


def test_meeting_agenda_counts_only_open_decisions():
    """리비전 0007 주석: status='PENDING' 인 항목이 그대로 다음 회의 안건이 된다."""
    service, repo = _service(decisions=5, open_decisions=2)
    out = service.preview(1, kind="MEETING_AGENDA")

    # 전체 5건 중 미결 2건만 담긴다.
    assert out.counts.decisions == 2
    assert repo.count_decisions.call_args.kwargs["status"] == "PENDING"
    assert (out.counts.documents, out.counts.schedule_items,
            out.counts.amount_items) == (0, 0, 0)


def test_project_status_counts_all_without_period():
    """현황 한 장은 '현재 상태' 라 기간이 없다."""
    service, repo = _service(documents=12, decisions=5, schedules=3, amounts=2)
    out = service.preview(1, kind="PROJECT_STATUS", **WEEK)
    assert out.counts.countable_total == 22
    assert out.period_from is None
    assert repo.count_documents.call_args.kwargs["since"] is None


# --- ② 대상이 없으면 생성이 막힌다 (완료 판정) ------------------------------


def test_blocked_when_nothing_to_include():
    service, _ = _service()
    out = service.preview(1, kind="WEEKLY_REPORT", **WEEK)
    assert out.can_generate is False
    assert out.blocked_reason
    assert "없습니다" in out.blocked_reason


def test_allowed_when_one_item_exists():
    """하나라도 있으면 만들 수 있다."""
    service, _ = _service(documents=1)
    out = service.preview(1, kind="WEEKLY_REPORT", **WEEK)
    assert out.can_generate is True
    assert out.blocked_reason is None


def test_blocked_reason_mentions_pending_when_present():
    """승인만 하면 담길 내용이 생긴다는 것을 알려준다."""
    service, _ = _service(pending=4)
    out = service.preview(1, kind="WEEKLY_REPORT", **WEEK)
    assert out.can_generate is False
    assert "4건" in out.blocked_reason
    assert "승인" in out.blocked_reason


def test_blocked_reason_differs_by_kind():
    for kind, word in (("MEETING_AGENDA", "미결"), ("DECISION_LOG", "결정사항")):
        service, _ = _service()
        out = service.preview(1, kind=kind)
        assert word in out.blocked_reason, (kind, out.blocked_reason)


# --- ③ 주간 보고서만 기간을 요구한다 ----------------------------------------


def test_weekly_report_requires_period():
    service, repo = _service(documents=5)
    with pytest.raises(BusinessError) as err:
        service.preview(1, kind="WEEKLY_REPORT")
    assert err.value.error_code is ErrorCode.PERIOD_REQUIRED
    # 세지도 않아야 한다.
    repo.count_documents.assert_not_called()


def test_other_kinds_do_not_require_period():
    for kind in ("DECISION_LOG", "MEETING_AGENDA", "PROJECT_STATUS"):
        service, _ = _service(decisions=1, open_decisions=1)
        out = service.preview(1, kind=kind)
        assert out.needs_period is False


def test_needs_period_flag_is_true_only_for_weekly():
    service, _ = _service(documents=1)
    assert service.preview(1, kind="WEEKLY_REPORT", **WEEK).needs_period is True


def test_reversed_period_is_rejected():
    service, _ = _service(documents=5)
    with pytest.raises(BusinessError) as err:
        service.preview(
            1, kind="WEEKLY_REPORT",
            period_from=date(2026, 8, 20), period_to=date(2026, 8, 14),
        )
    assert err.value.error_code is ErrorCode.INVALID_PROJECT_DATES


def test_unknown_kind_is_rejected():
    service, _ = _service()
    with pytest.raises(BusinessError):
        service.preview(1, kind="SOMETHING_ELSE")


# --- ④ 셀 수 없는 것을 0 으로 만들지 않는다 ---------------------------------


def test_completed_tasks_is_none_not_zero():
    """tasks 테이블이 없다. 0 으로 두면 '완료한 일이 없다' 로 잘못 읽힌다."""
    service, _ = _service(documents=5)
    out = service.preview(1, kind="WEEKLY_REPORT", **WEEK)
    assert out.counts.completed_tasks is None
    assert "completed_tasks" in out.uncountable


def test_uncountable_is_reported_even_when_generatable():
    service, _ = _service(documents=5)
    out = service.preview(1, kind="WEEKLY_REPORT", **WEEK)
    assert out.can_generate is True
    assert out.uncountable == ["completed_tasks"]


# --- ⑤ 승인 대기는 생성 가능 판정에 섞이지 않는다 ---------------------------


def test_pending_does_not_count_toward_total():
    """승인 대기만 있으면 보고서는 비어 있다. 담길 내용이 아니다."""
    counts = PreviewCounts(
        documents=0, decisions=0, schedule_items=0, amount_items=0,
        pending_suggestions=7,
    )
    assert counts.countable_total == 0


def test_pending_is_shown_regardless_of_period():
    """기간과 무관하다 — 지난주 제안이 아직 대기 중이면 지금 처리해야 한다."""
    service, repo = _service(documents=5, pending=3)
    out = service.preview(1, kind="WEEKLY_REPORT", **WEEK)
    assert out.counts.pending_suggestions == 3
    # 기간 인자를 받지 않는 메서드다.
    repo.count_pending_suggestions.assert_called_once_with(1)


def test_countable_total_sums_four_kinds():
    counts = PreviewCounts(
        documents=12, decisions=5, schedule_items=3, amount_items=2,
        pending_suggestions=99,
    )
    assert counts.countable_total == 22
