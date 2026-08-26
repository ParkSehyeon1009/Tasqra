# =============================================================================
# 이 파일의 책임: 산출물 생성 대상 미리보기(DLV-001-2)를 DB 없이 검증한다.
#   완료 판정이 "LLM 호출 전에 건수가 보이고 **대상이 없으면 생성이 방지된다**"
#   이므로, **막는 판정**이 가장 중요한 검사다.
#
#   검사하는 것
#     ① 종류마다 세는 대상이 다른가 (이 기능의 핵심 규칙)
#     ② 대상이 없으면 생성이 막히는가 (완료 판정)
#     ③ 주간 보고서만 기간을 요구하는가
#     ④ 완료한 태스크를 기간·종류에 맞게 세는가 (리비전 0019 로 열린 재료)
#     ⑤ 승인 대기가 생성 가능 판정에 섞이지 않는가
#
# 다른 파일과의 관계: services/deliverable_service.py · schemas/deliverable.py
#   리포지토리는 MagicMock 이다 — test_document_list_queries.py 와 같은 방식.
#
# Spring 비교: Mockito 로 Repository 를 스텁하고 Service 만 단위 검증.
# =============================================================================

import asyncio
from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.core.error_codes import ErrorCode
from app.core.exceptions import BusinessError
from app.schemas.deliverable import PreviewCounts
from app.services.deliverable_service import DeliverableService

WEEK = {"period_from": date(2026, 8, 14), "period_to": date(2026, 8, 20)}


def _service(*, documents=0, decisions=0, schedules=0, amounts=0, tasks=0, pending=0,
             open_decisions=0):
    repo = MagicMock()
    repo.count_documents.return_value = documents
    repo.count_schedule_items.return_value = schedules
    repo.count_amount_items.return_value = amounts
    repo.count_completed_tasks.return_value = tasks
    repo.count_pending_suggestions.return_value = pending

    # status 인자에 따라 다른 값을 준다 — 회의 안건은 미결만 센다.
    def decisions_side_effect(project_id, *, since=None, until=None, status=None):
        return open_decisions if status == "PENDING" else decisions

    repo.count_decisions.side_effect = decisions_side_effect
    return DeliverableService(repo), repo


# --- ① 종류마다 세는 대상이 다르다 ------------------------------------------


def test_weekly_report_counts_all_five_kinds():
    service, repo = _service(documents=12, decisions=5, schedules=3, amounts=2, tasks=7)
    out = service.preview(1, kind="WEEKLY_REPORT", **WEEK)
    assert (out.counts.documents, out.counts.decisions, out.counts.schedule_items,
            out.counts.amount_items, out.counts.completed_tasks) == (12, 5, 3, 2, 7)
    # 기간이 리포지토리까지 전달돼야 한다.
    assert repo.count_documents.call_args.kwargs["since"] == WEEK["period_from"]
    assert repo.count_documents.call_args.kwargs["until"] == WEEK["period_to"]
    assert repo.count_completed_tasks.call_args.kwargs["since"] == WEEK["period_from"]
    assert repo.count_completed_tasks.call_args.kwargs["until"] == WEEK["period_to"]


def test_decision_log_counts_only_decisions_without_period():
    """결정사항 대장에 기간을 걸면 '지난주에 정한 것만' 이 되어 대장이 아니게 된다."""
    service, repo = _service(documents=12, decisions=5, schedules=3, amounts=2, tasks=7)
    out = service.preview(1, kind="DECISION_LOG", **WEEK)

    assert out.counts.decisions == 5
    assert (out.counts.documents, out.counts.schedule_items,
            out.counts.amount_items, out.counts.completed_tasks) == (0, 0, 0, 0)
    # 기간을 무시한다 — 날짜를 줬어도 응답에 담기지 않는다.
    assert out.period_from is None and out.period_to is None
    # status 없이(=전부) 센다.
    assert repo.count_decisions.call_args.kwargs.get("status") is None


def test_meeting_agenda_counts_only_open_decisions():
    """리비전 0007 주석: status='PENDING' 인 항목이 그대로 다음 회의 안건이 된다."""
    service, repo = _service(decisions=5, open_decisions=2, tasks=7)
    out = service.preview(1, kind="MEETING_AGENDA")

    # 전체 5건 중 미결 2건만 담긴다.
    assert out.counts.decisions == 2
    assert repo.count_decisions.call_args.kwargs["status"] == "PENDING"
    assert (out.counts.documents, out.counts.schedule_items,
            out.counts.amount_items, out.counts.completed_tasks) == (0, 0, 0, 0)


def test_project_status_counts_all_without_period():
    """현황 한 장은 '현재 상태' 라 기간이 없다."""
    service, repo = _service(documents=12, decisions=5, schedules=3, amounts=2, tasks=7)
    out = service.preview(1, kind="PROJECT_STATUS", **WEEK)
    assert out.counts.countable_total == 29
    assert out.period_from is None
    assert repo.count_documents.call_args.kwargs["since"] is None
    assert repo.count_completed_tasks.call_args.kwargs["since"] is None


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


# --- ④ 완료한 태스크를 센다 (리비전 0019 로 열린 재료) ----------------------


def test_completed_tasks_is_counted_not_null():
    """tasks 테이블이 생겼다. 더 이상 '셀 수 없다' 가 아니다."""
    service, _ = _service(documents=5, tasks=4)
    out = service.preview(1, kind="WEEKLY_REPORT", **WEEK)
    assert out.counts.completed_tasks == 4
    assert out.uncountable == []


def test_zero_completed_tasks_means_really_zero():
    """0 은 '집계 전' 이 아니라 그 기간에 끝낸 일이 없다는 뜻이다."""
    service, _ = _service(documents=5, tasks=0)
    out = service.preview(1, kind="WEEKLY_REPORT", **WEEK)
    assert out.counts.completed_tasks == 0
    assert out.uncountable == []


def test_completed_tasks_alone_allows_generation():
    """명세가 주간 보고서 내용에 태스크를 넣으므로 태스크만 있어도 만들 수 있다."""
    service, _ = _service(tasks=2)
    out = service.preview(1, kind="WEEKLY_REPORT", **WEEK)
    assert out.counts.countable_total == 2
    assert out.can_generate is True
    assert out.blocked_reason is None


def test_blocked_reason_mentions_tasks_for_weekly_report():
    """막힌 이유가 세는 대상과 같아야 한다 — 태스크도 셌으므로 문장에 있어야 한다."""
    service, _ = _service()
    out = service.preview(1, kind="WEEKLY_REPORT", **WEEK)
    assert "태스크" in out.blocked_reason


def test_decision_kinds_do_not_count_tasks():
    """결정사항 대장·회의 안건에는 태스크가 담기지 않는다."""
    for kind in ("DECISION_LOG", "MEETING_AGENDA"):
        service, repo = _service(decisions=3, open_decisions=1, tasks=9)
        out = service.preview(1, kind=kind)
        assert out.counts.completed_tasks == 0, kind
        repo.count_completed_tasks.assert_not_called()


# --- ⑤ 승인 대기는 생성 가능 판정에 섞이지 않는다 ---------------------------


def test_pending_does_not_count_toward_total():
    """승인 대기만 있으면 보고서는 비어 있다. 담길 내용이 아니다."""
    counts = PreviewCounts(
        documents=0, decisions=0, schedule_items=0, amount_items=0,
        completed_tasks=0, pending_suggestions=7,
    )
    assert counts.countable_total == 0


def test_pending_is_shown_regardless_of_period():
    """기간과 무관하다 — 지난주 제안이 아직 대기 중이면 지금 처리해야 한다."""
    service, repo = _service(documents=5, pending=3)
    out = service.preview(1, kind="WEEKLY_REPORT", **WEEK)
    assert out.counts.pending_suggestions == 3
    # 기간 인자를 받지 않는 메서드다.
    repo.count_pending_suggestions.assert_called_once_with(1)


def test_countable_total_sums_five_kinds():
    """완료한 태스크까지 다섯을 더한다. 승인 대기는 아무리 많아도 더하지 않는다."""
    counts = PreviewCounts(
        documents=12, decisions=5, schedule_items=3, amount_items=2,
        completed_tasks=7, pending_suggestions=99,
    )
    assert counts.countable_total == 29



# --- ⑥ 본문 미리보기(preview_content)의 개요 (DLV-002-1·DLV-002-2) -----------
#
# 만들기(generate)의 개요는 test_deliverable_generate.py 가 검증한다. 여기서는
# **본문 미리보기가 같은 개요를 만드는가** 를 잠근다 — 이 엔드포인트의 존재 이유가
# "미리 본 것과 만든 것이 어긋나지 않게" 이므로, 개요만 갈라지면 그 약속이 깨진다.
# preview_content 는 파일을 쓰지 않으므로 db 없이 검증한다.


class _FakeAI:
    """개요 LLM 경로 검증용 최소 클라이언트. 계약(generate_with_meta)만 만족시킨다."""

    provider = "fake"

    def __init__(self, *, text='{"summary": "미리보기 개요입니다."}'):
        self._text = text
        self.calls = 0

    async def generate(self, prompt: str) -> str:
        return (await self.generate_with_meta(prompt)).text

    async def generate_with_meta(self, prompt: str):
        from app.ai.client_protocol import AIResult

        self.calls += 1
        return AIResult(text=self._text, model_name="fake-model")


def _document(name="과업지시서.pdf"):
    return SimpleNamespace(
        filename=name,
        document_type="CONTRACT",
        created_at=datetime(2026, 8, 17, 9, 30, tzinfo=timezone.utc),
    )


def _content_service(*, documents=1, rows=None, ai_client=None):
    """preview_content 용 서비스. count_* 로 생성 가능 판정을 통과시키고 list_* 로
    본문 재료를 준다(preview 전용 _service 는 count_* 만 세우므로 따로 둔다)."""
    repo = MagicMock()
    repo.count_documents.return_value = documents
    repo.count_schedule_items.return_value = 0
    repo.count_amount_items.return_value = 0
    repo.count_completed_tasks.return_value = 0
    repo.count_pending_suggestions.return_value = 0
    repo.count_decisions.return_value = 0

    rows = rows or {"documents": [_document()]}
    repo.list_documents.return_value = rows.get("documents", [])
    repo.list_completed_tasks.return_value = rows.get("completed_tasks", [])
    repo.list_decisions.return_value = rows.get("decisions", [])
    repo.list_schedule_items.return_value = rows.get("schedule_items", [])
    repo.list_amount_items.return_value = rows.get("amount_items", [])
    return DeliverableService(repo, None, ai_client), repo


def _content(service, **kwargs):
    """preview_content 는 async(개요 LLM)라 asyncio.run 으로 부른다."""
    return asyncio.run(
        service.preview_content(1, kind="PROJECT_STATUS", deliverable_format="MD", **kwargs)
    )


def test_preview_content_fills_overview_with_one_llm_call():
    ai = _FakeAI(text='{"summary": "문서 1건이 반영된 현황입니다."}')
    service, _ = _content_service(ai_client=ai)
    out = _content(service)

    assert ai.calls == 1  # 만들기와 같은 "개요 1회"
    assert "## 개요" in out.body
    assert "문서 1건이 반영된 현황입니다." in out.body
    assert "아직" not in out.body  # 미연결 안내 문구가 아니다
    assert "과업지시서.pdf" in out.body  # 표는 실제 자료


def test_preview_content_uses_placeholder_without_llm():
    """LLM 이 없으면 미리보기도 개요를 지어내지 않는다(만들기와 같은 판단)."""
    service, _ = _content_service(ai_client=None)
    out = _content(service)
    assert "## 개요" in out.body
    assert "아직" in out.body


def test_preview_content_blocks_when_nothing_to_include():
    """담을 것이 없으면 미리보기도 막는다 — 개요 LLM 을 부르기 전에 막힌다."""
    ai = _FakeAI()
    service, _ = _content_service(documents=0, rows={"documents": []}, ai_client=ai)
    with pytest.raises(BusinessError) as err:
        _content(service)
    assert err.value.error_code is ErrorCode.DELIVERABLE_EMPTY
    assert ai.calls == 0  # 막힌 뒤엔 헛 호출을 하지 않는다
