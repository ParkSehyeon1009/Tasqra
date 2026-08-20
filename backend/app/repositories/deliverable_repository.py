# =============================================================================
# 이 파일의 책임: 산출물의 재료가 몇 건인지 DB 에서 센다 (DLV-001-2 미리보기).
#   세는 일만 한다. "만들 수 있는가" 판단은 서비스가 한다.
#
# 다른 파일과의 관계
#   services/deliverable_service.py  이 리포지토리를 부르고 판단을 한다
#   models/decision.py · schedule.py · amount.py · document.py 를 읽는다
#   repositories/dashboard_repository.py 와 같은 방식이다 — 리포지토리가 세고
#   서비스가 접는다
#
# Spring 비교: @Repository 다. 세는 것을 화면이 아니라 DB 가 하는 이유는
#   dashboard_repository 머리말과 같다 — 목록을 받아 화면에서 세면 페이지 상한
#   때문에 숫자가 조용히 틀린다.
#
# ⚠ 완료 태스크는 셀 수 없다
#   `tasks` 테이블이 아직 없다(TSK-001-1 태스크 CRUD 미구현). 마이그레이션
#   어디에도 create_table("tasks") 가 없고 모델도 없다.
#   **`decisions` · `schedule_items` 와 혼동하지 말 것** — 그 둘은 리비전 0007 로
#   있고 8/20 에 ORM 모델도 생겼다. 뜻도 "결정사항" 과 "일정" 이라 태스크가 아니다.
#   그래서 count_tasks 같은 메서드를 두지 않았다. 없는 것을 0 으로 세면 "완료한
#   태스크가 0건" 과 "아직 셀 수 없다" 를 구별할 수 없다.
#
# ⚠ 기간 필터를 어느 컬럼에 걸지가 종류마다 다르다
#   문서는 created_at, 결정은 decided_on, 일정은 due_on(kind 마다 다른 컬럼),
#   금액은 문서를 거쳐야 한다. 한 컬럼으로 통일할 수 없어서 메서드를 나눴다.
# =============================================================================

from __future__ import annotations

from datetime import date

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models.amount import AmountItem
from app.models.decision import Decision
from app.models.document import Document
from app.models.schedule import ScheduleItem

__all__ = ["DeliverableRepository"]


class DeliverableRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    # --- 문서 ---------------------------------------------------------------

    def count_documents(
        self, project_id: int, *, since: date | None = None, until: date | None = None
    ) -> int:
        """기간 안에 올라온 문서 수.

        `created_at` 은 timestamptz 이고 인자는 date 다. `func.date()` 로 날짜만
        비교한다 — 그러지 않으면 종료일 당일에 올린 문서가 빠진다(00:00 기준으로
        비교되기 때문).
        """
        stmt = select(func.count()).select_from(Document).where(
            Document.project_id == project_id
        )
        if since is not None:
            stmt = stmt.where(func.date(Document.created_at) >= since)
        if until is not None:
            stmt = stmt.where(func.date(Document.created_at) <= until)
        return int(self._db.execute(stmt).scalar() or 0)

    # --- 결정사항 -----------------------------------------------------------

    def count_decisions(
        self,
        project_id: int,
        *,
        since: date | None = None,
        until: date | None = None,
        status: str | None = None,
    ) -> int:
        """결정사항 수. `status` 를 주면 그 상태만 센다.

        기간은 `decided_on` 으로 본다. 그 값이 NULL 인 행(문서에 날짜가 없었던
        경우)은 기간을 주면 빠진다 — **일부러 그렇게 둔다.** 날짜를 모르는 결정을
        "이번 주 결정" 으로 넣으면 보고서가 틀린다.

        기간을 주지 않으면(결정사항 대장·회의 안건) 전부 센다.
        """
        stmt = select(func.count()).select_from(Decision).where(
            Decision.project_id == project_id
        )
        if status is not None:
            stmt = stmt.where(Decision.status == status)
        if since is not None:
            stmt = stmt.where(Decision.decided_on >= since)
        if until is not None:
            stmt = stmt.where(Decision.decided_on <= until)
        return int(self._db.execute(stmt).scalar() or 0)

    # --- 일정·기한 ----------------------------------------------------------

    def count_schedule_items(
        self, project_id: int, *, since: date | None = None, until: date | None = None
    ) -> int:
        """기간에 걸리는 일정·기한 수.

        `kind` 마다 기한 컬럼이 다르다(models/schedule.py 의 due_on 참고).
        SQL 에서 프로퍼티를 쓸 수 없으므로 **두 컬럼 중 하나라도 걸리면** 센다.
        `MILESTONE`·`MEETING` 은 `starts_on`, `DEADLINE`·`PERIOD` 는 `ends_on` 이
        기한이라 이 방식이 둘을 함께 담는다.

        `PERIOD` 는 구간이라 기간과 겹치기만 해도 걸린다 — 그것이 맞다.
        "이 주에 진행 중인 기간" 이 보고서에 들어가야 한다.
        """
        stmt = select(func.count()).select_from(ScheduleItem).where(
            ScheduleItem.project_id == project_id
        )
        if since is not None or until is not None:
            starts_ok = ScheduleItem.starts_on.is_not(None)
            ends_ok = ScheduleItem.ends_on.is_not(None)
            if since is not None:
                starts_ok = starts_ok & (ScheduleItem.starts_on >= since)
                ends_ok = ends_ok & (ScheduleItem.ends_on >= since)
            if until is not None:
                starts_ok = starts_ok & (ScheduleItem.starts_on <= until)
                ends_ok = ends_ok & (ScheduleItem.ends_on <= until)
            stmt = stmt.where(or_(starts_ok, ends_ok))
        return int(self._db.execute(stmt).scalar() or 0)

    # --- 금액 ---------------------------------------------------------------

    def count_amount_items(
        self, project_id: int, *, since: date | None = None, until: date | None = None
    ) -> int:
        """금액 항목 수.

        `amount_items` 에는 `project_id` 가 없다 — 문서를 거쳐야 한다. 리비전
        0007 이 그렇게 만들었고, 금액은 항상 문서에서 나오기 때문이다.
        (`document_chunks` 는 0014 로 역정규화했지만 그건 HNSW 인덱스 때문이었다.)

        기간은 **문서의 업로드 시각**으로 본다. 금액 항목 자체에는 날짜가
        `period_from`·`period_to` 뿐이고 그건 "그 금액이 적용되는 기간" 이라
        보고서의 "이번 주 변동" 과 다른 뜻이다.
        """
        stmt = (
            select(func.count())
            .select_from(AmountItem)
            .join(Document, Document.id == AmountItem.document_id)
            .where(Document.project_id == project_id)
        )
        if since is not None:
            stmt = stmt.where(func.date(Document.created_at) >= since)
        if until is not None:
            stmt = stmt.where(func.date(Document.created_at) <= until)
        return int(self._db.execute(stmt).scalar() or 0)

    def count_pending_suggestions(self, project_id: int) -> int:
        """승인 대기 중인 AI 제안 수 — 금액·결정·일정을 합친다.

        기간을 받지 않는다. **승인 대기는 "지금 남아 있는 것" 이라 기간과 무관**하다.
        지난주 제안이 아직 대기 중이면 그것도 지금 처리해야 한다.

        대시보드의 `count_pending_amount_items` 는 금액만 센다. 여기서 셋을 합치는
        것은 산출물이 세 종류를 모두 재료로 쓰기 때문이다.
        """
        amounts = (
            select(func.count())
            .select_from(AmountItem)
            .join(Document, Document.id == AmountItem.document_id)
            .where(Document.project_id == project_id, AmountItem.decision == "PENDING")
        )
        decisions = select(func.count()).select_from(Decision).where(
            Decision.project_id == project_id, Decision.decision == "PENDING"
        )
        schedules = select(func.count()).select_from(ScheduleItem).where(
            ScheduleItem.project_id == project_id, ScheduleItem.decision == "PENDING"
        )
        total = 0
        for stmt in (amounts, decisions, schedules):
            total += int(self._db.execute(stmt).scalar() or 0)
        return total
