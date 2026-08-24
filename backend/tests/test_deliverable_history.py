# =============================================================================
# 이 파일의 책임: 산출물 이력 조회와 삭제(DLV-003-3)를 DB 없이 검증한다.
#
#   검사하는 것
#     ① 최근에 만든 것이 먼저 오는가 (정렬을 리포지토리에 맡기는가)
#     ② 목록이 디스크를 보지 않는가 (파일 수만큼 접근이 생기면 안 된다)
#     ③ 삭제가 **이력 먼저, 파일 나중** 인가 (순서가 뒤집히면 못 받는 행이 남는다)
#     ④ 파일 삭제 실패가 요청을 실패시키지 않는가
#     ⑤ 없는 산출물을 지울 때 404 인가
#
# 다른 파일과의 관계: services/deliverable_service.py. 리포지토리는 MagicMock 이다.
#
# Spring 비교: Mockito 로 Repository 를 스텁하고 Service 만 단위 검증.
# =============================================================================

import os
from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.core.error_codes import ErrorCode
from app.core.exceptions import BusinessError
from app.services.deliverable_service import HISTORY_LIMIT, DeliverableService


def _row(deliverable_id=9, path="/tmp/없어도-된다.md", title="주간 보고서"):
    return SimpleNamespace(
        id=deliverable_id,
        kind="WEEKLY_REPORT",
        format="MD",
        title=title,
        period_from=date(2026, 8, 14),
        period_to=date(2026, 8, 20),
        file_path=path,
        file_size=1234,
        source_counts_json={"documents": 3},
        generated_at=datetime(2026, 8, 24, 6, 0, tzinfo=timezone.utc),
    )


def _service(rows=None):
    repo = MagicMock()
    repo.list_by_project.return_value = rows if rows is not None else []
    return DeliverableService(repo, MagicMock()), repo


# --- ① ② 목록 ---------------------------------------------------------------


def test_history_asks_repository_with_limit():
    """정렬과 상한을 서비스가 다시 구현하지 않는다 — 인덱스가 받쳐 주는 쪽에 맡긴다."""
    service, repo = _service([_row(1), _row(2)])
    result = service.list_history(7)
    assert len(result) == 2
    repo.list_by_project.assert_called_once_with(7, limit=HISTORY_LIMIT)


def test_history_does_not_touch_disk():
    """건마다 파일 존재를 확인하면 파일 수만큼 디스크 접근이 생긴다."""
    service, _ = _service([_row(1, path="/없는/경로1.md"), _row(2, path="/없는/경로2.md")])
    # 파일이 하나도 없어도 목록은 그대로 나온다.
    assert len(service.list_history(7)) == 2


def test_empty_history_is_empty_list_not_error():
    service, _ = _service([])
    assert service.list_history(7) == []


# --- ③ ④ ⑤ 삭제 -------------------------------------------------------------


def test_delete_removes_history_then_file(tmp_path):
    """순서가 중요하다 — 이력을 먼저 지우고 파일을 나중에 지운다."""
    target = tmp_path / "산출물.md"
    target.write_text("내용", encoding="utf-8")

    service, repo = _service()
    repo.get.return_value = _row(path=str(target))

    service.delete(7, 9)

    repo.get.assert_called_once_with(7, 9)
    repo.remove.assert_called_once()
    assert not target.exists(), "파일이 지워지지 않았다"


def test_delete_keeps_file_when_history_removal_fails(tmp_path):
    """이력 삭제가 실패하면 파일은 그대로 둔다. 받을 수 있는 상태가 유지된다."""
    target = tmp_path / "산출물.md"
    target.write_text("내용", encoding="utf-8")

    service, repo = _service()
    repo.get.return_value = _row(path=str(target))
    repo.remove.side_effect = RuntimeError("이력 삭제 실패")

    with pytest.raises(RuntimeError):
        service.delete(7, 9)

    assert target.exists(), "이력이 남았는데 파일을 지웠다"


def test_delete_succeeds_even_if_file_already_gone():
    """사용자가 요청한 것은 이력에서 지우기다. 파일이 이미 없어도 성공이다."""
    service, repo = _service()
    repo.get.return_value = _row(path="/없는/경로.md")

    service.delete(7, 9)  # 예외가 나지 않아야 한다

    repo.remove.assert_called_once()


def test_delete_missing_deliverable_is_not_found():
    service, repo = _service()
    repo.get.return_value = None
    with pytest.raises(BusinessError) as err:
        service.delete(7, 9)
    assert err.value.error_code is ErrorCode.DELIVERABLE_NOT_FOUND
    repo.remove.assert_not_called()


def test_delete_scopes_by_project():
    """id 만으로 찾으면 남의 프로젝트 산출물을 지울 수 있다."""
    service, repo = _service()
    repo.get.return_value = _row()
    service.delete(7, 9)
    assert repo.get.call_args.args == (7, 9)


# --- 다운로드는 목록과 달리 파일을 확인한다 ---------------------------------


def test_open_file_checks_disk(tmp_path):
    target = tmp_path / "산출물.md"
    target.write_text("내용", encoding="utf-8")

    service, repo = _service()
    repo.get.return_value = _row(path=str(target))

    row = service.open_file(7, 9)
    assert os.path.exists(row.file_path)
