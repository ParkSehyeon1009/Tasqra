# =============================================================================
# 이 파일의 책임: 대시보드 집계와 프로젝트 캘린더 조회를 담는다. 집계는 세기만
#   하고 판단은 services/dashboard_service.py에 두며, 캘린더는 날짜 범위만 거른다.
# 다른 파일과의 관계: Document·AmountItem·Task·ScheduleItem을 읽는다.
#   dependencies.py가 세션을 넣어 만들고 dashboard_service.py가 쓴다.
# Spring 비교: @Repository 다. group by 로 상태별 건수를 한 번에 받아오는 것은
#   JPQL 의 프로젝션 집계 쿼리에 해당한다.
#
# document_repository.py 에 넣지 않고 파일을 새로 만든 이유 두 개
#   1. 대시보드 집계는 한 테이블에 머물지 않는다. documents 를 세고 amount_items
#      를 조인해 세고, 앞으로 decisions · schedule_items 가 연결되면 그것도
#      센다. "이 숫자가 어디서 나왔나" 를 한 파일에서 전부 확인할 수 있는 편이
#      낫다. 지표가 여러 리포지토리에 흩어지면 합이 안 맞을 때 추적이 어렵다.
#   2. document_repository.py 는 문서 도메인(재정님 영역) 파일이다. 집계만
#      더하려고 그 파일을 건드리면 충돌 지점이 생긴다. 얻는 것 없이 남의 작업과
#      부딪히는 변경은 피한다.
#
# 조회를 다섯 번 내보내는 것에 대해
#   지표마다 한 번씩이라 항상 다섯 번이다. 결과 수에 비례하지 않으므로 N+1 이
#   아니다. 하나로 합칠 수도 있지만(FILTER 절이나 CTE) 그러면 지표를 더할 때마다
#   쿼리 하나를 다시 손봐야 하고, 어느 숫자가 틀렸는지 따로 확인하기도 어려워진다.
#   documents 는 ix_doc_list · ix_doc_type 이, amount_items 는 ix_amount_pending
#   이 이미 각 조회에 맞는 인덱스라 다섯 번이 싼 쪽이다.
# =============================================================================

from __future__ import annotations

from datetime import date

from sqlalchemy import Select, and_, func, or_, select
from sqlalchemy.orm import Session, joinedload

from app.models.amount import AmountItem
from app.models.document import Document
from app.models.schedule import ScheduleItem
from app.models.task import Task, TaskActivityLog

# 승인 대기로 셀 상태. amount_items.decision 의 값이다.
# APPROVED · EDITED 는 사람이 이미 판단한 것이고 REJECTED 는 거절한 것이라
# "대기" 가 아니다. 이 값이 ix_amount_pending 부분 인덱스의 조건과 같아야
# 인덱스를 탄다(리비전 0007 의 postgresql_where="decision = 'PENDING'").
PENDING_DECISION = "PENDING"


class DashboardRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def count_documents_by_status(self, project_id: int) -> dict[str, int]:
        """{상태: 건수}. 그 프로젝트에 없는 상태는 키가 아예 없다.

        호출한 쪽이 dict.get(상태, 0) 으로 읽어야 한다. 상태 여섯 개를 0 으로
        채워 돌려주지 않는 이유는, 그 목록을 여기에 적으면 enums.py 의
        DocumentStatus 와 두 곳에서 관리해야 하기 때문이다.
        """
        stmt: Select = (
            select(Document.status, func.count())
            .where(Document.project_id == project_id)
            .group_by(Document.status)
        )
        return {row[0]: int(row[1]) for row in self._db.execute(stmt).all()}

    def count_documents_by_review_status(self, project_id: int) -> dict[str, int]:
        """{검수 상태: 건수}. 위와 같은 방식이다."""
        stmt: Select = (
            select(Document.review_status, func.count())
            .where(Document.project_id == project_id)
            .group_by(Document.review_status)
        )
        return {row[0]: int(row[1]) for row in self._db.execute(stmt).all()}

    def count_documents_by_type(self, project_id: int) -> list[tuple[str | None, int]]:
        """[(문서 유형, 건수)]. 유형이 없는 문서는 첫 값이 None 인 칸으로 온다.

        NULL 을 걸러내지 않는다. documents.document_type 은 nullable 이고
        분류되지 않은 문서가 실제로 있다. 걸러내면 분포의 합이 문서 수보다
        작아져서 화면의 숫자가 서로 맞지 않는다.

        정렬하지 않는다 — 어떤 순서로 보여줄지는 서비스가 정한다.
        ix_doc_type (project_id, document_type) 이 이 조회 순서와 같다.
        """
        stmt: Select = (
            select(Document.document_type, func.count())
            .where(Document.project_id == project_id)
            .group_by(Document.document_type)
        )
        return [(row[0], int(row[1])) for row in self._db.execute(stmt).all()]

    def list_recent_documents(self, *, project_id: int, limit: int) -> list[Document]:
        """최근 올라온 문서. 최신이 먼저다.

        created_at 이 같을 때 id 로 한 번 더 정렬한다. server_default=func.now()
        라 같은 트랜잭션에서 여러 건을 넣으면 created_at 이 동일해지고, 그러면
        정렬이 실행마다 달라져 새로고침할 때 목록 순서가 흔들린다.

        ix_doc_list (project_id, created_at) 를 탄다.
        """
        stmt: Select = (
            select(Document)
            .where(Document.project_id == project_id)
            .order_by(Document.created_at.desc(), Document.id.desc())
            .limit(limit)
        )
        return list(self._db.execute(stmt).scalars())

    def count_pending_amount_items(self, project_id: int) -> int:
        """승인 대기 금액 항목 수.

        amount_items 에는 project_id 가 없어서 documents 를 조인해 거른다.
        금액 항목은 문서에서 읽은 값이므로 프로젝트가 아니라 문서에 매달려
        있다(models/amount.py 참고). 그래서 프로젝트 단위로 세려면 조인이
        반드시 필요하다.
        """
        stmt: Select = (
            select(func.count())
            .select_from(AmountItem)
            .join(Document, Document.id == AmountItem.document_id)
            .where(Document.project_id == project_id)
            .where(AmountItem.decision == PENDING_DECISION)
        )
        return int(self._db.execute(stmt).scalar_one())

    def count_open_tasks(self, project_id: int) -> int:
        stmt: Select = (
            select(func.count())
            .select_from(Task)
            .where(Task.project_id == project_id, Task.status != "DONE")
        )
        return int(self._db.execute(stmt).scalar_one())

    def count_document_states_by_projects(
        self, project_ids: list[int]
    ) -> tuple[dict[int, dict[str, int]], dict[int, dict[str, int]]]:
        """프로젝트별 문서 상태와 검수 상태를 한 번의 묶음 조회로 센다."""
        stmt: Select = (
            select(
                Document.project_id,
                Document.status,
                Document.review_status,
                func.count(),
            )
            .where(Document.project_id.in_(project_ids))
            .group_by(Document.project_id, Document.status, Document.review_status)
        )
        by_status: dict[int, dict[str, int]] = {}
        by_review: dict[int, dict[str, int]] = {}
        for project_id, status, review_status, count in self._db.execute(stmt).all():
            status_counts = by_status.setdefault(int(project_id), {})
            status_counts[status] = status_counts.get(status, 0) + int(count)
            review_counts = by_review.setdefault(int(project_id), {})
            review_counts[review_status] = review_counts.get(review_status, 0) + int(count)
        return by_status, by_review

    def count_document_types_by_projects(
        self, project_ids: list[int]
    ) -> dict[int, list[tuple[str | None, int]]]:
        stmt: Select = (
            select(Document.project_id, Document.document_type, func.count())
            .where(Document.project_id.in_(project_ids))
            .group_by(Document.project_id, Document.document_type)
        )
        result: dict[int, list[tuple[str | None, int]]] = {}
        for project_id, document_type, count in self._db.execute(stmt).all():
            result.setdefault(int(project_id), []).append((document_type, int(count)))
        return result

    def count_pending_amount_items_by_projects(
        self, project_ids: list[int]
    ) -> dict[int, int]:
        stmt: Select = (
            select(Document.project_id, func.count())
            .select_from(AmountItem)
            .join(Document, Document.id == AmountItem.document_id)
            .where(
                Document.project_id.in_(project_ids),
                AmountItem.decision == PENDING_DECISION,
            )
            .group_by(Document.project_id)
        )
        return {
            int(project_id): int(count)
            for project_id, count in self._db.execute(stmt).all()
        }

    def count_open_tasks_by_projects(self, project_ids: list[int]) -> dict[int, int]:
        stmt: Select = (
            select(Task.project_id, func.count())
            .where(Task.project_id.in_(project_ids), Task.status != "DONE")
            .group_by(Task.project_id)
        )
        return {
            int(project_id): int(count)
            for project_id, count in self._db.execute(stmt).all()
        }

    def list_recent_documents_by_projects(
        self, *, project_ids: list[int], limit_per_project: int
    ) -> dict[int, list[Document]]:
        """각 프로젝트의 최근 문서를 window 순위로 한 번에 가져온다."""
        ranked = (
            select(
                Document.id.label("document_id"),
                func.row_number()
                .over(
                    partition_by=Document.project_id,
                    order_by=(Document.created_at.desc(), Document.id.desc()),
                )
                .label("document_rank"),
            )
            .where(Document.project_id.in_(project_ids))
            .subquery()
        )
        stmt: Select = (
            select(Document)
            .join(ranked, ranked.c.document_id == Document.id)
            .where(ranked.c.document_rank <= limit_per_project)
            .order_by(Document.project_id, Document.created_at.desc(), Document.id.desc())
        )
        result: dict[int, list[Document]] = {}
        for document in self._db.execute(stmt).scalars():
            result.setdefault(int(document.project_id), []).append(document)
        return result

    def list_recent_task_activity_by_projects(
        self, *, project_ids: list[int], limit: int
    ) -> list[TaskActivityLog]:
        """접근 가능한 프로젝트 전체에서 가장 최근 활동만 제한해 가져온다."""
        stmt: Select = (
            select(TaskActivityLog)
            .options(joinedload(TaskActivityLog.actor))
            .where(TaskActivityLog.project_id.in_(project_ids))
            .order_by(TaskActivityLog.created_at.desc(), TaskActivityLog.id.desc())
            .limit(limit)
        )
        return list(self._db.execute(stmt).scalars())

    def list_calendar_tasks(
        self, *, project_id: int, starts_on: date, ends_on: date
    ) -> list[Task]:
        """조회 구간에 마감일이 있는 태스크. 수기·AI 출처와 상태를 가리지 않는다."""
        stmt: Select = (
            select(Task)
            .where(
                Task.project_id == project_id,
                Task.due_on >= starts_on,
                Task.due_on <= ends_on,
            )
            .order_by(Task.due_on, Task.id)
        )
        return list(self._db.execute(stmt).scalars())

    def list_calendar_schedule_items(
        self, *, project_id: int, starts_on: date, ends_on: date
    ) -> list[ScheduleItem]:
        """조회 구간과 겹치는, 사람이 승인 또는 수정 승인한 일정만 반환한다."""
        in_range = or_(
            and_(
                ScheduleItem.kind == "PERIOD",
                ScheduleItem.starts_on <= ends_on,
                ScheduleItem.ends_on >= starts_on,
            ),
            and_(
                ScheduleItem.kind.in_(("MILESTONE", "MEETING")),
                ScheduleItem.starts_on >= starts_on,
                ScheduleItem.starts_on <= ends_on,
            ),
            and_(
                ScheduleItem.kind == "DEADLINE",
                ScheduleItem.ends_on >= starts_on,
                ScheduleItem.ends_on <= ends_on,
            ),
        )
        stmt: Select = (
            select(ScheduleItem)
            .where(
                ScheduleItem.project_id == project_id,
                ScheduleItem.decision.in_(("APPROVED", "EDITED")),
                in_range,
            )
            .order_by(ScheduleItem.starts_on, ScheduleItem.ends_on, ScheduleItem.id)
        )
        return list(self._db.execute(stmt).scalars())
