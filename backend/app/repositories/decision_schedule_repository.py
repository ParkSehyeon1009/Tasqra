# =============================================================================
# 이 파일의 책임: 결정사항·일정 추출 결과 저장과 프로젝트 범위 검토 조회를 맡는다.
# 다른 파일과의 관계: writer는 add_*로 flush만 하고, review service는 get/list로
#   문서 파일명·현재 OCR revision까지 받아 승인 상태를 바꾼다.
# Spring 비교: JpaRepository의 saveAll과 프로젝트 한정 projection query를 함께
#   둔 저장소다. 트랜잭션 경계는 상위 @Service가 연다.
# =============================================================================

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from app.models.decision import Decision
from app.models.document import Document
from app.models.schedule import ScheduleItem


class DecisionScheduleRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def add_decisions(self, rows: list[Decision]) -> list[Decision]:
        if rows:
            self._db.add_all(rows)
            self._db.flush()
        return rows

    def delete_pending_decisions(self, project_id: int, document_id: int) -> int:
        """재분석 전 아직 검토하지 않은 이전 결정 제안만 대체한다."""
        return self._db.query(Decision).filter(
            Decision.project_id == project_id,
            Decision.document_id == document_id,
            Decision.decision == "PENDING",
        ).delete(synchronize_session=False)

    def add_schedule_items(
        self, rows: list[ScheduleItem]
    ) -> list[ScheduleItem]:
        if rows:
            self._db.add_all(rows)
            self._db.flush()
        return rows

    def delete_pending_schedule_items(
        self, project_id: int, document_id: int
    ) -> int:
        """재분석 전 아직 검토하지 않은 이전 일정 제안만 대체한다."""
        return self._db.query(ScheduleItem).filter(
            ScheduleItem.project_id == project_id,
            ScheduleItem.document_id == document_id,
            ScheduleItem.decision == "PENDING",
        ).delete(synchronize_session=False)

    def lock_document(
        self, project_id: int, document_id: int
    ) -> tuple[str, int] | None:
        """OCR 수정과 승인 사이 경쟁을 막도록 출처 문서 행을 먼저 잠근다."""
        document = (
            self._db.query(Document)
            .filter(Document.project_id == project_id, Document.id == document_id)
            .with_for_update()
            .one_or_none()
        )
        if document is None:
            return None
        return document.filename, document.ocr_revision

    def get_decision(
        self, project_id: int, item_id: int
    ) -> tuple[Decision, str | None, int | None] | None:
        stmt = (
            select(Decision, Document.filename, Document.ocr_revision)
            .outerjoin(
                Document,
                and_(
                    Document.id == Decision.document_id,
                    Document.project_id == project_id,
                ),
            )
            .where(Decision.project_id == project_id, Decision.id == item_id)
        )
        row = self._db.execute(stmt).one_or_none()
        return (row[0], row[1], row[2]) if row else None

    def get_decision_for_update(
        self, project_id: int, item_id: int
    ) -> Decision | None:
        return self._db.query(Decision).filter(
            Decision.project_id == project_id,
            Decision.id == item_id,
        ).with_for_update().one_or_none()

    def get_schedule_item(
        self, project_id: int, item_id: int
    ) -> tuple[ScheduleItem, str | None, int | None] | None:
        stmt = (
            select(ScheduleItem, Document.filename, Document.ocr_revision)
            .outerjoin(
                Document,
                and_(
                    Document.id == ScheduleItem.document_id,
                    Document.project_id == project_id,
                ),
            )
            .where(ScheduleItem.project_id == project_id, ScheduleItem.id == item_id)
        )
        row = self._db.execute(stmt).one_or_none()
        return (row[0], row[1], row[2]) if row else None

    def get_schedule_item_for_update(
        self, project_id: int, item_id: int
    ) -> ScheduleItem | None:
        return self._db.query(ScheduleItem).filter(
            ScheduleItem.project_id == project_id,
            ScheduleItem.id == item_id,
        ).with_for_update().one_or_none()

    def list_decisions(
        self,
        project_id: int,
        decisions: tuple[str, ...],
        limit: int,
        document_id: int | None = None,
    ) -> tuple[list[tuple[Decision, str | None, int | None]], int]:
        filters = [
            Decision.project_id == project_id,
            Decision.decision.in_(decisions),
        ]
        if document_id is not None:
            filters.append(Decision.document_id == document_id)
        total = int(
            self._db.scalar(select(func.count(Decision.id)).where(*filters)) or 0
        )
        stmt = (
            select(Decision, Document.filename, Document.ocr_revision)
            .outerjoin(
                Document,
                and_(
                    Document.id == Decision.document_id,
                    Document.project_id == project_id,
                ),
            )
            .where(*filters)
            .order_by(Decision.created_at, Decision.id)
            .limit(limit)
        )
        return (
            [(row[0], row[1], row[2]) for row in self._db.execute(stmt).all()],
            total,
        )

    def list_schedule_items(
        self,
        project_id: int,
        decisions: tuple[str, ...],
        limit: int,
        document_id: int | None = None,
    ) -> tuple[list[tuple[ScheduleItem, str | None, int | None]], int]:
        filters = [
            ScheduleItem.project_id == project_id,
            ScheduleItem.decision.in_(decisions),
        ]
        if document_id is not None:
            filters.append(ScheduleItem.document_id == document_id)
        total = int(
            self._db.scalar(select(func.count(ScheduleItem.id)).where(*filters)) or 0
        )
        stmt = (
            select(ScheduleItem, Document.filename, Document.ocr_revision)
            .outerjoin(
                Document,
                and_(
                    Document.id == ScheduleItem.document_id,
                    Document.project_id == project_id,
                ),
            )
            .where(*filters)
            .order_by(ScheduleItem.created_at, ScheduleItem.id)
            .limit(limit)
        )
        return (
            [(row[0], row[1], row[2]) for row in self._db.execute(stmt).all()],
            total,
        )
