# =============================================================================
# 이 파일의 책임: 산출물 만들기(DLV-002-x)를 DB 없이 검증한다.
#
#   검사하는 것
#     ① 담을 것이 없으면 만들지 않는가 (미리보기와 같은 판단인가)
#     ② 아직 못 만드는 형식을 400 이 아니라 501 로 구분하는가
#     ③ 유형마다 담는 자료가 다른가 (_materials 가 _count 의 표와 같은가)
#     ④ 본문에 실제 자료가 들어가고 표가 깨지지 않는가
#     ⑤ 스냅샷이 미리보기 건수와 같은 키인가 (갱신 판정의 근거)
#     ⑥ 이력 저장이 실패하면 쓴 파일을 남기지 않는가
#
# 다른 파일과의 관계: services/deliverable_service.py ·
#   services/deliverable_markdown.py. 리포지토리는 MagicMock 이고 파일 저장만
#   실제로 한다(tmp_path 로 UPLOAD_DIR 을 바꾼다).
#
# Spring 비교: Mockito 로 Repository 를 스텁하고 Service 만 단위 검증.
#   파일 쓰기는 @TempDir 로 실제 디스크를 쓰는 것과 같다.
# =============================================================================

import asyncio
from datetime import date, datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.core.error_codes import ErrorCode
from app.core.exceptions import BusinessError
from app.services.deliverable_markdown import (
    DeliverableMaterials,
    clean,
    render_markdown,
)
from app.services.deliverable_service import SNAPSHOT_KEYS, DeliverableService

WEEK = {"period_from": date(2026, 8, 14), "period_to": date(2026, 8, 20)}


@pytest.fixture(autouse=True)
def upload_dir(tmp_path, monkeypatch):
    """산출물 파일을 임시 폴더에 쓴다. 실제 uploads 를 더럽히지 않는다."""
    from app.core.config import settings

    monkeypatch.setattr(settings, "UPLOAD_DIR", str(tmp_path), raising=False)
    return tmp_path


def _document(name="계약서.pdf", document_type="CONTRACT"):
    return SimpleNamespace(
        filename=name,
        document_type=document_type,
        created_at=datetime(2026, 8, 17, 9, 30, tzinfo=timezone.utc),
    )


def _task(title="API 연동", assignee="김보현"):
    return SimpleNamespace(
        title=title,
        assignee=SimpleNamespace(name=assignee),
        completed_at=datetime(2026, 8, 18, 5, 0, tzinfo=timezone.utc),
    )


def _decision(title="이관 대상 확정", status="DECIDED", decided_on=date(2026, 8, 19)):
    return SimpleNamespace(title=title, status=status, decided_on=decided_on)


def _schedule(title="중간 보고", kind="MEETING"):
    return SimpleNamespace(
        title=title, kind=kind, starts_on=date(2026, 8, 20), ends_on=None
    )


def _amount(name="직접인건비", quantity=Decimal("6.0000"), unit_price=1_000_000, amount=6_000_000):
    return SimpleNamespace(
        item_name=name,
        quantity=quantity,
        unit_price=unit_price,
        amount=amount,
    )


def _service(*, documents=0, decisions=0, schedules=0, amounts=0, tasks=0, pending=0,
             open_decisions=0, rows=None, ai_client=None):
    repo = MagicMock()
    repo.count_documents.return_value = documents
    repo.count_schedule_items.return_value = schedules
    repo.count_amount_items.return_value = amounts
    repo.count_completed_tasks.return_value = tasks
    repo.count_pending_suggestions.return_value = pending

    def decisions_side_effect(project_id, *, since=None, until=None, status=None):
        return open_decisions if status == "PENDING" else decisions

    repo.count_decisions.side_effect = decisions_side_effect

    rows = rows or {}
    repo.list_documents.return_value = rows.get("documents", [])
    repo.list_completed_tasks.return_value = rows.get("completed_tasks", [])
    repo.list_decisions.return_value = rows.get("decisions", [])
    repo.list_schedule_items.return_value = rows.get("schedule_items", [])
    repo.list_amount_items.return_value = rows.get("amount_items", [])
    repo.add.side_effect = lambda row: _with_id(row)
    return DeliverableService(repo, MagicMock(), ai_client), repo


def _with_id(row, value=9):
    """DB 가 매길 id 를 흉내낸다. flush 뒤에 채워지는 값이다."""
    row.id = value
    return row


def _read(row) -> str:
    with open(row.file_path, encoding="utf-8") as file:
        return file.read()


def _gen(service, **kwargs):
    """`generate` 는 async 다(개요 LLM 호출 때문). 이 파일은 DB 없이 도는 단위
    테스트라 asyncio.run 으로 직접 부른다 — test_error_response_format.py 가 async
    핸들러를 부르는 방식과 같다. project_id 는 이 파일에서 늘 1 이다.

    `_service()` 는 ai_client 를 주지 않으므로 개요는 SUMMARY_PLACEHOLDER 로 남는다
    (LLM 을 부르지 않는다). 개요 LLM 경로는 test_overview_* 에서 따로 검증한다.
    """
    return asyncio.run(service.generate(1, **kwargs))


# --- ① 담을 것이 없으면 만들지 않는다 ---------------------------------------


def test_blocked_when_nothing_to_include():
    """미리보기가 막은 것과 같은 판단이어야 한다."""
    service, repo = _service()
    with pytest.raises(BusinessError) as err:
        _gen(service, kind="WEEKLY_REPORT", deliverable_format="MD", **WEEK)
    # 이미 있던 코드를 쓴다. 뜻이 같은 코드를 하나 더 만들지 않는다.
    assert err.value.error_code is ErrorCode.DELIVERABLE_EMPTY
    # 파일도 이력도 만들지 않는다.
    repo.add.assert_not_called()


def test_blocked_reason_comes_from_preview():
    """이유 문장을 만들기가 따로 쓰지 않는다 — 두 곳이 갈리면 안 된다."""
    service, _ = _service(pending=4)
    with pytest.raises(BusinessError) as err:
        _gen(service, kind="WEEKLY_REPORT", deliverable_format="MD", **WEEK)
    assert "승인" in str(err.value)
    assert "4건" in str(err.value)


def test_period_required_is_checked_before_writing():
    service, repo = _service(documents=3)
    with pytest.raises(BusinessError) as err:
        _gen(service, kind="WEEKLY_REPORT", deliverable_format="MD")
    assert err.value.error_code is ErrorCode.PERIOD_REQUIRED
    repo.add.assert_not_called()


# --- ② 형식 ------------------------------------------------------------------


def test_unsupported_format_is_not_ready_not_invalid():
    """DB 가 허용하는 값이다. 값이 틀린 것과 서버가 아직 못 하는 것을 구분한다.

    XLSX 는 2026-08-26 부터 만들 수 있어 여기서 뺐다 — 501 은 이제 PDF 만.
    """
    for unsupported in ("PDF",):
        service, repo = _service(documents=3)
        with pytest.raises(BusinessError) as err:
            _gen(service, kind="WEEKLY_REPORT", deliverable_format=unsupported, **WEEK)
        assert err.value.error_code is ErrorCode.DELIVERABLE_FORMAT_NOT_READY, unsupported
        # 형식을 먼저 보므로 DB 조회도 하지 않는다.
        repo.count_documents.assert_not_called()
        repo.add.assert_not_called()


def test_unknown_format_is_invalid():
    service, _ = _service(documents=3)
    with pytest.raises(BusinessError) as err:
        _gen(service, kind="WEEKLY_REPORT", deliverable_format="DOCX", **WEEK)
    assert err.value.error_code is ErrorCode.INVALID_DOCUMENT_TYPE


# --- ③ 유형마다 담는 자료가 다르다 ------------------------------------------


def test_meeting_agenda_takes_only_open_decisions():
    service, repo = _service(
        open_decisions=2, rows={"decisions": [_decision(status="PENDING")]}
    )
    _gen(service, kind="MEETING_AGENDA", deliverable_format="MD")
    assert repo.list_decisions.call_args.kwargs["status"] == "PENDING"
    repo.list_documents.assert_not_called()
    repo.list_amount_items.assert_not_called()


def test_decision_log_takes_all_decisions_without_period():
    service, repo = _service(decisions=3, rows={"decisions": [_decision()]})
    _gen(service, kind="DECISION_LOG", deliverable_format="MD", **WEEK)
    assert repo.list_decisions.call_args.kwargs.get("status") is None
    assert "since" not in repo.list_decisions.call_args.kwargs


def test_weekly_report_takes_five_materials_with_period():
    service, repo = _service(documents=1, rows={"documents": [_document()]})
    _gen(service, kind="WEEKLY_REPORT", deliverable_format="MD", **WEEK)
    for name in ("list_documents", "list_completed_tasks", "list_decisions",
                 "list_schedule_items", "list_amount_items"):
        call = getattr(repo, name).call_args
        assert call.kwargs["since"] == WEEK["period_from"], name
        assert call.kwargs["until"] == WEEK["period_to"], name


# --- ④ 본문 ------------------------------------------------------------------


def test_body_contains_real_rows():
    service, _ = _service(
        documents=1, tasks=1, decisions=1, schedules=1, amounts=1,
        rows={
            "documents": [_document("과업지시서.pdf")],
            "completed_tasks": [_task("검색 API 연동")],
            "decisions": [_decision("이관 범위 확정")],
            "schedule_items": [_schedule("착수 보고")],
            "amount_items": [_amount("직접인건비")],
        },
    )
    row = _gen(service, kind="WEEKLY_REPORT", deliverable_format="MD", **WEEK)
    body = _read(row)

    assert "과업지시서.pdf" in body
    assert "검색 API 연동" in body
    assert "이관 범위 확정" in body
    assert "착수 보고" in body
    assert "직접인건비" in body
    # 금액은 천 단위 구분을 넣는다.
    assert "6,000,000" in body
    # 수량의 뒤 0 을 지운다. Numeric(18,4) 라 6.0000 으로 온다.
    assert "| 6 |" in body
    # 제목과 기간이 머리에 있다.
    assert body.startswith("# 주간 보고서 2026-08-14 ~ 2026-08-20")
    assert "2026-08-14 ~ 2026-08-20" in body


def test_body_marks_summary_as_not_written_without_llm():
    """LLM 이 없으면 개요를 지어내지 않고 비었다고 적는다(SUMMARY_PLACEHOLDER)."""
    service, _ = _service(documents=1, rows={"documents": [_document()]})
    body = _read(_gen(service, kind="WEEKLY_REPORT", deliverable_format="MD", **WEEK))
    assert "## 개요" in body
    assert "아직" in body


# --- 개요(LLM 1회) DLV-002-1·DLV-002-2 --------------------------------------


class _FakeAI:
    """개요 LLM 경로를 검증하기 위한 최소 클라이언트.

    실제 어댑터(fake_client·local_client)와 같은 계약(generate_with_meta)만
    만족시킨다. 호출 횟수를 세어 "LLM 호출은 개요 1회" 를 검사한다.
    """

    provider = "fake"

    def __init__(self, *, text='{"summary": "이번 주 핵심 개요입니다."}', fail=False):
        self._text = text
        self._fail = fail
        self.calls = 0
        self.prompts: list[str] = []

    async def generate(self, prompt: str) -> str:  # 계약상 존재해야 한다
        result = await self.generate_with_meta(prompt)
        return result.text

    async def generate_with_meta(self, prompt: str):
        from app.ai.client_protocol import AIResult

        self.calls += 1
        self.prompts.append(prompt)
        if self._fail:
            raise RuntimeError("provider down")
        return AIResult(text=self._text, model_name="fake-model")


def test_overview_is_filled_by_one_llm_call():
    """개요를 LLM 1회 호출로 채운다 — 완료 판정 "LLM 호출은 개요 1회"."""
    ai = _FakeAI(text='{"summary": "문서 1건과 결정 1건이 반영됐습니다."}')
    service, _ = _service(
        documents=1, decisions=1,
        rows={"documents": [_document("과업지시서.pdf")], "decisions": [_decision()]},
        ai_client=ai,
    )
    body = _read(_gen(service, kind="WEEKLY_REPORT", deliverable_format="MD", **WEEK))

    assert ai.calls == 1  # 정확히 한 번
    assert "문서 1건과 결정 1건이 반영됐습니다." in body
    # 개요가 채워졌으므로 미연결 안내 문구(SUMMARY_PLACEHOLDER)는 없다.
    assert "아직" not in body
    # 표는 여전히 실제 자료다.
    assert "과업지시서.pdf" in body


def test_overview_llm_not_called_for_kinds_without_overview():
    """결정 대장·회의 안건에는 개요 절이 없다. 헛 호출을 하지 않는다."""
    ai = _FakeAI()
    service, _ = _service(decisions=2, rows={"decisions": [_decision()]}, ai_client=ai)
    _gen(service, kind="DECISION_LOG", deliverable_format="MD", **WEEK)
    assert ai.calls == 0


def test_overview_falls_back_to_placeholder_when_llm_fails():
    """개요 하나 때문에 보고서 전체를 막지 않는다. 실패하면 안내 문구로 되돌아간다."""
    ai = _FakeAI(fail=True)
    service, _ = _service(documents=1, rows={"documents": [_document()]}, ai_client=ai)
    body = _read(_gen(service, kind="WEEKLY_REPORT", deliverable_format="MD", **WEEK))

    assert ai.calls == 1
    assert "## 개요" in body
    assert "아직" in body  # SUMMARY_PLACEHOLDER 로 되돌아간다
    # 표는 정상적으로 만들어진다(제목이 머리에 있다).
    assert body.startswith("# 주간 보고서")


def test_overview_uses_raw_text_when_json_broken():
    """JSON 이 깨져 와도 서버가 죽지 않고 본문 텍스트를 그대로 개요로 쓴다."""
    ai = _FakeAI(text="그냥 평문 개요입니다")
    service, _ = _service(documents=1, rows={"documents": [_document()]}, ai_client=ai)
    body = _read(_gen(service, kind="WEEKLY_REPORT", deliverable_format="MD", **WEEK))
    assert "그냥 평문 개요입니다" in body


def test_empty_section_says_so_instead_of_empty_table():
    """머리글만 있는 표는 '자료를 못 가져온 것' 처럼 보인다."""
    service, _ = _service(documents=1, rows={"documents": [_document()]})
    body = _read(_gen(service, kind="WEEKLY_REPORT", deliverable_format="MD", **WEEK))
    assert "이 기간에 완료한 태스크가 없습니다." in body


def test_clean_keeps_value_and_removes_newlines():
    """구조 단계에서는 형식별 escape 를 하지 않는다. 줄바꿈만 없앤다."""
    assert clean("두\n줄") == "두 줄"
    assert clean(None) == "—"
    # `|` 는 여기서 바꾸지 않는다 — Markdown 포매터의 몫이다.
    assert clean("A|B") == "A|B"


def test_pipe_in_value_does_not_break_markdown_table():
    """문서 이름에 | 가 있으면 표가 깨진다. 지우지 않고 전각으로 바꾼다."""
    body = render_markdown(
        kind="PROJECT_STATUS",
        title="t",
        period_from=None,
        period_to=None,
        materials=DeliverableMaterials(documents=[_document("A|B.pdf")]),
        generated_at_text="2026-08-24 15:00",
    )
    assert "A｜B.pdf" in body
    assert "A|B.pdf" not in body


def test_amount_none_is_dash_not_zero():
    """금액이 없는 것과 0 원은 다르다."""
    body = "\n".join(
        render_markdown(
            kind="PROJECT_STATUS",
            title="t",
            period_from=None,
            period_to=None,
            materials=DeliverableMaterials(amount_items=[_amount(amount=None, unit_price=None)]),
            generated_at_text="2026-08-24 15:00",
        ).splitlines()
    )
    assert "| — | — |" in body


# --- ⑤ 스냅샷 ----------------------------------------------------------------


def test_snapshot_uses_preview_count_keys():
    """갱신 판정(DLV-003-4)이 다시 세어 비교할 수 있어야 한다."""
    service, repo = _service(
        documents=7, tasks=8, decisions=3, schedules=2, amounts=1,
        rows={"documents": [_document()]},
    )
    _gen(service, kind="WEEKLY_REPORT", deliverable_format="MD", **WEEK)
    saved = repo.add.call_args.args[0]
    assert saved.source_counts_json == {
        "documents": 7, "completed_tasks": 8, "decisions": 3,
        "schedule_items": 2, "amount_items": 1,
    }
    assert set(saved.source_counts_json) == set(SNAPSHOT_KEYS)
    # 승인 대기는 담기는 재료가 아니라 스냅샷에 넣지 않는다.
    assert "pending_suggestions" not in saved.source_counts_json


def test_saved_row_keeps_kind_format_and_period():
    service, repo = _service(documents=1, rows={"documents": [_document()]})
    _gen(service, kind="WEEKLY_REPORT", deliverable_format="MD", **WEEK)
    saved = repo.add.call_args.args[0]
    assert (saved.kind, saved.format) == ("WEEKLY_REPORT", "MD")
    assert (saved.period_from, saved.period_to) == (WEEK["period_from"], WEEK["period_to"])
    assert saved.file_size and saved.file_size > 0
    assert saved.title == "주간 보고서 2026-08-14 ~ 2026-08-20"


def test_period_is_ignored_for_kinds_without_period():
    """결정사항 대장에 기간을 걸면 대장이 아니게 된다."""
    service, repo = _service(decisions=2, rows={"decisions": [_decision()]})
    _gen(service, kind="DECISION_LOG", deliverable_format="MD", **WEEK)
    saved = repo.add.call_args.args[0]
    assert saved.period_from is None and saved.period_to is None


# --- ⑥ 실패하면 파일을 남기지 않는다 ----------------------------------------


def test_file_is_removed_when_history_fails():
    """목록에 없는데 디스크에만 남는 파일을 만들지 않는다."""
    service, repo = _service(documents=1, rows={"documents": [_document()]})
    repo.add.side_effect = RuntimeError("이력 저장 실패")
    with pytest.raises(RuntimeError):
        _gen(service, kind="WEEKLY_REPORT", deliverable_format="MD", **WEEK)

    from app.core.config import settings

    directory = f"{settings.UPLOAD_DIR}/deliverables/1"
    import os

    left = os.listdir(directory) if os.path.isdir(directory) else []
    assert left == [], f"파일이 남았다: {left}"


# --- 다운로드 ----------------------------------------------------------------


def test_download_missing_file_is_distinguished_from_not_found():
    service, repo = _service()
    repo.get.return_value = SimpleNamespace(file_path="/없는/경로.md")
    with pytest.raises(BusinessError) as err:
        service.open_file(1, 9)
    assert err.value.error_code is ErrorCode.DELIVERABLE_FILE_MISSING

    repo.get.return_value = None
    with pytest.raises(BusinessError) as err:
        service.open_file(1, 9)
    assert err.value.error_code is ErrorCode.DELIVERABLE_NOT_FOUND



# --- 요청 검증 (빈 값과 잘못된 값을 구분한다) --------------------------------


def test_empty_format_is_rejected_by_schema():
    """빈 문자열은 "고르지 않았다" 다. 값이 틀린 것(400)이 아니라 422 여야 한다.

    min_length=1 이 없으면 "" 가 문자열로 통과해 서비스까지 내려가고, 거기서
    INVALID_DOCUMENT_TYPE(400)이 난다. 실제로 그렇게 나와서 고쳤다.
    """
    from pydantic import ValidationError

    from app.schemas.deliverable import DeliverableCreateRequest

    for payload in (
        {"kind": "PROJECT_STATUS", "format": ""},
        {"kind": "", "format": "MD"},
        {"kind": "PROJECT_STATUS"},
    ):
        with pytest.raises(ValidationError):
            DeliverableCreateRequest(**payload)


def test_valid_request_passes_schema():
    from app.schemas.deliverable import DeliverableCreateRequest

    request = DeliverableCreateRequest(kind="PROJECT_STATUS", format="MD")
    assert (request.kind, request.format) == ("PROJECT_STATUS", "MD")
    # 기간은 없어도 된다. 주간 보고서만 서비스에서 필수로 본다.
    assert request.period_from is None and request.period_to is None
