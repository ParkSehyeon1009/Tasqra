# =============================================================================
# 이 파일의 책임: 갱신 필요 판정(DLV-003-4)을 DB 없이 검증한다.
#
#   완료 판정: "생성 후 **대상이 추가되면** 갱신 필요 표시가 뜬다."
#
#   검사하는 것
#     ① 늘어나면 뜨는가
#     ② 그대로면 안 뜨는가
#     ③ **줄어든 것으로는 뜨지 않는가** (문서를 지웠다고 다시 만들 이유가 없다)
#     ④ 무엇이 몇 건 늘었는지 알려주는가
#     ⑤ 같은 (유형, 기간)을 여러 번 세지 않는가
#     ⑥ 유형마다 세는 대상이 다른 규칙을 그대로 쓰는가
#
# 다른 파일과의 관계
#   services/deliverable_service.py  stale_changes 가 검사 대상이다
#   models/deliverable.py            판정 규칙(stale_against)은 모델에 있다.
#     그 규칙 자체는 test_suggestion_models.py 가 이미 검증한다 — 여기서는
#     **서비스가 그것을 올바른 현재값과 함께 부르는지**를 본다
#
# Spring 비교: Mockito 로 Repository 를 스텁하고 Service 만 단위 검증.
# =============================================================================

from datetime import date, datetime, timezone
from unittest.mock import MagicMock

from app.models.deliverable import Deliverable
from app.services.deliverable_service import DeliverableService

WEEK_FROM = date(2026, 8, 14)
WEEK_TO = date(2026, 8, 20)

# 만든 시점에 문서 5 · 태스크 3 · 결정 2 · 일정 1 · 금액 0 이었다.
MADE_WITH = {
    "documents": 5,
    "completed_tasks": 3,
    "decisions": 2,
    "schedule_items": 1,
    "amount_items": 0,
}


def _deliverable(deliverable_id=1, kind="WEEKLY_REPORT", snapshot=None,
                 period_from=WEEK_FROM, period_to=WEEK_TO):
    """실제 모델을 쓴다 — 판정 규칙(stale_against)을 흉내내지 않기 위해서다."""
    row = Deliverable(
        project_id=7,
        kind=kind,
        format="MD",
        period_from=period_from,
        period_to=period_to,
        title="주간 보고서",
        file_path="/tmp/x.md",
        file_size=10,
        source_counts_json=dict(MADE_WITH if snapshot is None else snapshot),
        generated_at=datetime(2026, 8, 20, 9, 0, tzinfo=timezone.utc),
    )
    row.id = deliverable_id
    return row


def _service(*, documents=5, tasks=3, decisions=2, schedules=1, amounts=0,
             open_decisions=0):
    repo = MagicMock()
    repo.count_documents.return_value = documents
    repo.count_completed_tasks.return_value = tasks
    repo.count_schedule_items.return_value = schedules
    repo.count_amount_items.return_value = amounts
    repo.count_pending_suggestions.return_value = 0

    def decisions_side_effect(project_id, *, since=None, until=None, status=None):
        return open_decisions if status == "PENDING" else decisions

    repo.count_decisions.side_effect = decisions_side_effect
    return DeliverableService(repo, MagicMock()), repo


# --- ① ② ③ ④ 판정 -----------------------------------------------------------


def test_stale_when_material_grew():
    """문서가 2건 늘었다 — 갱신이 필요하다."""
    service, _ = _service(documents=7)
    changes = service.stale_changes(7, [_deliverable()])
    assert changes[1] == {"documents": 2}


def test_not_stale_when_nothing_changed():
    service, _ = _service()
    changes = service.stale_changes(7, [_deliverable()])
    assert changes[1] == {}


def test_not_stale_when_material_shrank():
    """문서를 지웠다고 보고서를 다시 만들 이유가 없다."""
    service, _ = _service(documents=2, decisions=0)
    changes = service.stale_changes(7, [_deliverable()])
    assert changes[1] == {}


def test_reports_every_grown_kind():
    """무엇이 몇 건 늘었는지 화면이 문장을 만들 수 있어야 한다."""
    service, _ = _service(documents=6, tasks=5, amounts=4)
    changes = service.stale_changes(7, [_deliverable()])
    assert changes[1] == {"documents": 1, "completed_tasks": 2, "amount_items": 4}


def test_key_missing_from_snapshot_counts_as_growth():
    """재료 종류가 나중에 추가된 경우 — 그 값 전부가 늘어난 것이다."""
    service, _ = _service()
    row = _deliverable(snapshot={"documents": 5})
    changes = service.stale_changes(7, [row])
    assert changes[1] == {"completed_tasks": 3, "decisions": 2, "schedule_items": 1}


# --- ⑤ 같은 조건을 여러 번 세지 않는다 --------------------------------------


def test_same_kind_and_period_is_counted_once():
    """같은 조건으로 여러 번 만든 경우가 흔하다(다시 만들기)."""
    service, repo = _service(documents=9)
    rows = [_deliverable(1), _deliverable(2), _deliverable(3)]
    changes = service.stale_changes(7, rows)

    assert repo.count_documents.call_count == 1
    # 세 건 모두 같은 판정을 받는다 — 스냅샷이 같으므로.
    assert changes == {1: {"documents": 4}, 2: {"documents": 4}, 3: {"documents": 4}}


def test_different_period_is_counted_separately():
    service, repo = _service(documents=9)
    rows = [
        _deliverable(1, period_from=WEEK_FROM, period_to=WEEK_TO),
        _deliverable(2, period_from=date(2026, 8, 7), period_to=date(2026, 8, 13)),
    ]
    service.stale_changes(7, rows)
    assert repo.count_documents.call_count == 2


# --- ⑥ 유형별 규칙을 그대로 쓴다 --------------------------------------------


def test_meeting_agenda_compares_only_open_decisions():
    """안건은 미결 결정만 담는다. 확정된 결정이 늘어도 갱신 대상이 아니다."""
    service, repo = _service(decisions=99, open_decisions=5)
    row = _deliverable(
        1, kind="MEETING_AGENDA", period_from=None, period_to=None,
        snapshot={"documents": 0, "completed_tasks": 0, "decisions": 3,
                  "schedule_items": 0, "amount_items": 0},
    )
    changes = service.stale_changes(7, [row])
    # 미결이 3 -> 5 로 늘었다. 전체 결정 99 는 쓰지 않는다.
    assert changes[1] == {"decisions": 2}
    assert repo.count_decisions.call_args.kwargs["status"] == "PENDING"
    # 문서는 담기지 않는 유형이라 세지 않는다.
    repo.count_documents.assert_not_called()


def test_decision_log_ignores_period():
    """대장은 전체 누적이다. 기간이 없으니 결정 전부와 비교한다."""
    service, repo = _service(decisions=10)
    row = _deliverable(
        1, kind="DECISION_LOG", period_from=None, period_to=None,
        snapshot={"documents": 0, "completed_tasks": 0, "decisions": 4,
                  "schedule_items": 0, "amount_items": 0},
    )
    changes = service.stale_changes(7, [row])
    assert changes[1] == {"decisions": 6}
    assert repo.count_decisions.call_args.kwargs.get("status") is None


def test_empty_history_needs_no_counting():
    service, repo = _service()
    assert service.stale_changes(7, []) == {}
    repo.count_documents.assert_not_called()
