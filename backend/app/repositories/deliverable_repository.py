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
# ⚠ 완료 태스크를 이제 센다 (전에는 셀 수 없었다)
#   `tasks` 테이블이 리비전 0019 로 생겼다(TSK-001-1·TSK-001-2 구현). 그래서
#   count_completed_tasks 를 두고, 서비스의 UNCOUNTABLE 이 빈 목록이 됐다.
#   **`decisions` · `schedule_items` 와 혼동하지 말 것** — 그 둘은 리비전 0007 로
#   있고 뜻도 "결정사항" 과 "일정" 이라 태스크가 아니다.
#
# ⚠ 기간 필터를 어느 컬럼에 걸지가 종류마다 다르다
#   문서는 created_at, 결정은 decided_on, 일정은 due_on(kind 마다 다른 컬럼),
#   태스크는 completed_at, 금액은 문서를 거쳐야 한다. 한 컬럼으로 통일할 수
#   없어서 메서드를 나눴다.
# =============================================================================

from __future__ import annotations

from datetime import date

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, joinedload

from app.models.amount import AmountItem
from app.models.decision import Decision
from app.models.deliverable import Deliverable
from app.models.document import Document
from app.models.schedule import ScheduleItem
from app.models.task import Task

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

    # --- 태스크 -------------------------------------------------------------

    def count_completed_tasks(
        self, project_id: int, *, since: date | None = None, until: date | None = None
    ) -> int:
        """완료한 태스크 수. 기간은 `completed_at` 으로 본다.

        `status == 'DONE'` 을 함께 거는 이유
          `completed_at` 만 보면 완료를 되돌린 태스크가 남는다. 반대로 상태만
          보면 "이번 주에 완료" 가 아니라 "지금 완료 상태" 를 세게 된다. 둘을
          함께 걸어야 주간 보고서의 "이 기간에 끝낸 일" 이 된다.
          task_service 가 DONE 으로 옮길 때 `completed_at` 을 찍고 DONE 에서
          빼낼 때 NULL 로 지우므로 두 조건이 어긋나지 않는다.

        기간을 주면 `completed_at` 이 NULL 인 행은 빠진다 — `count_decisions` 의
        `decided_on` 과 같은 판단이다. 완료 시각을 모르는 태스크를 "이번 주에
        끝낸 일" 로 넣으면 보고서가 틀린다.

        `completed_at` 은 timestamptz 이고 인자는 date 다. `count_documents` 와
        같은 이유로 `func.date()` 로 날짜만 비교한다 — 그러지 않으면 종료일 당일에
        끝낸 태스크가 빠진다.
        """
        stmt = select(func.count()).select_from(Task).where(
            Task.project_id == project_id, Task.status == "DONE"
        )
        if since is not None:
            stmt = stmt.where(func.date(Task.completed_at) >= since)
        if until is not None:
            stmt = stmt.where(func.date(Task.completed_at) <= until)
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


    # --- 산출물에 담을 실제 행 (DLV-002-x) ----------------------------------
    #
    # ⚠ 세는 메서드와 **같은 조건**을 써야 한다. 조건이 갈리면 미리보기가 12건이라
    #   했는데 보고서에 9건이 담기는 일이 생긴다. 그래서 아래 목록 메서드는 위
    #   count_* 와 나란히 두고 필터를 그대로 옮겼다.
    #
    # ⚠ 상한을 둔다
    #   보고서 한 장에 수천 행을 넣으면 파일도 크고 사람이 읽지도 못한다. 서비스가
    #   limit 을 넘겨 자르고, 잘렸다는 사실은 건수(source_counts)와 표의 행 수가
    #   다른 것으로 드러난다.

    def list_documents(
        self,
        project_id: int,
        *,
        since: date | None = None,
        until: date | None = None,
        limit: int = 200,
    ) -> list[Document]:
        stmt = select(Document).where(Document.project_id == project_id)
        if since is not None:
            stmt = stmt.where(func.date(Document.created_at) >= since)
        if until is not None:
            stmt = stmt.where(func.date(Document.created_at) <= until)
        stmt = stmt.order_by(Document.created_at, Document.id).limit(limit)
        return list(self._db.execute(stmt).scalars())

    def list_completed_tasks(
        self,
        project_id: int,
        *,
        since: date | None = None,
        until: date | None = None,
        limit: int = 200,
    ) -> list[Task]:
        stmt = (
            select(Task)
            .options(joinedload(Task.assignee))
            .where(Task.project_id == project_id, Task.status == "DONE")
        )
        if since is not None:
            stmt = stmt.where(func.date(Task.completed_at) >= since)
        if until is not None:
            stmt = stmt.where(func.date(Task.completed_at) <= until)
        stmt = stmt.order_by(Task.completed_at, Task.id).limit(limit)
        return list(self._db.execute(stmt).unique().scalars())

    def list_decisions(
        self,
        project_id: int,
        *,
        since: date | None = None,
        until: date | None = None,
        status: str | None = None,
        limit: int = 200,
    ) -> list[Decision]:
        stmt = select(Decision).where(Decision.project_id == project_id)
        if status is not None:
            stmt = stmt.where(Decision.status == status)
        if since is not None:
            stmt = stmt.where(Decision.decided_on >= since)
        if until is not None:
            stmt = stmt.where(Decision.decided_on <= until)
        # 결정일이 NULL 인 행은 기간을 줄 때만 빠진다(count_decisions 와 같다).
        # 정렬에서도 NULL 을 뒤로 보내 표 앞쪽에 날짜 없는 행이 몰리지 않게 한다.
        stmt = stmt.order_by(Decision.decided_on.is_(None), Decision.decided_on, Decision.id)
        return list(self._db.execute(stmt.limit(limit)).scalars())

    def list_schedule_items(
        self,
        project_id: int,
        *,
        since: date | None = None,
        until: date | None = None,
        limit: int = 200,
    ) -> list[ScheduleItem]:
        stmt = select(ScheduleItem).where(ScheduleItem.project_id == project_id)
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
        stmt = stmt.order_by(ScheduleItem.starts_on, ScheduleItem.ends_on, ScheduleItem.id)
        return list(self._db.execute(stmt.limit(limit)).scalars())

    def list_amount_items(
        self,
        project_id: int,
        *,
        since: date | None = None,
        until: date | None = None,
        limit: int = 200,
    ) -> list[AmountItem]:
        stmt = (
            select(AmountItem)
            .join(Document, Document.id == AmountItem.document_id)
            .where(Document.project_id == project_id)
        )
        if since is not None:
            stmt = stmt.where(func.date(Document.created_at) >= since)
        if until is not None:
            stmt = stmt.where(func.date(Document.created_at) <= until)
        stmt = stmt.order_by(AmountItem.document_id, AmountItem.id).limit(limit)
        return list(self._db.execute(stmt).scalars())

    # --- 산출물 이력 --------------------------------------------------------

    def add(self, deliverable: Deliverable) -> Deliverable:
        """이력 한 건을 넣는다. 커밋은 서비스가 transactional 로 한다.

        flush 까지만 하는 이유: 응답에 id 가 필요하고, 커밋 시점은 서비스가
        정해야 한다(파일 저장과 함께 묶인다).
        """
        self._db.add(deliverable)
        self._db.flush()
        return deliverable

    def get(self, project_id: int, deliverable_id: int) -> Deliverable | None:
        """프로젝트를 함께 조건에 넣는다.

        id 만으로 찾으면 남의 프로젝트 산출물을 내 프로젝트 경로로 받을 수 있다.
        권한은 라우터가 프로젝트 단위로만 보므로 그 안에 있는지는 여기서 본다.
        """
        stmt = select(Deliverable).where(
            Deliverable.id == deliverable_id, Deliverable.project_id == project_id
        )
        return self._db.execute(stmt).scalar_one_or_none()


    def list_by_project(self, project_id: int, *, limit: int = 100) -> list[Deliverable]:
        """만든 순서의 역순으로 이력을 돌려준다 (DLV-003-3).

        정렬 기준이 `generated_at` 내림차순인 이유는 리비전 0007 의 인덱스
        `ix_deliverable_recent(project_id, generated_at)` 가 그 순서를 받쳐 주기
        때문이다. 같은 시각이면 id 로 고정한다 — 순서가 흔들리면 목록이 새로고침
        때마다 달라 보인다.

        페이지를 나누지 않는다. 산출물은 프로젝트당 수십 건 규모이고 화면이
        목록으로 한 번에 보여준다. 늘어나면 그때 문서 목록처럼 페이징을 붙인다 —
        지금 넣으면 쓰지 않는 파라미터가 계약에 남는다.
        """
        stmt = (
            select(Deliverable)
            .where(Deliverable.project_id == project_id)
            .order_by(Deliverable.generated_at.desc(), Deliverable.id.desc())
            .limit(limit)
        )
        return list(self._db.execute(stmt).scalars())

    def remove(self, deliverable: Deliverable) -> None:
        """이력 한 건을 지운다. 커밋은 서비스가 한다.

        파일은 여기서 지우지 않는다 — 리포지토리는 DB 만 다룬다. 파일과 DB 를
        지우는 순서는 서비스가 정해야 한다(deliverable_service.delete 주석 참고).
        """
        self._db.delete(deliverable)
