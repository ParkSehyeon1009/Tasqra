# =============================================================================
# 이 파일의 책임: 결정사항·일정 제안을 승인·수정·거절·취소한다.
# 다른 파일과의 관계: DecisionScheduleRepository로 프로젝트 범위를 확인하고,
#   transaction.py로 상태와 판단자·판단시각을 한 트랜잭션에 저장한다.
# Spring 비교: @Service + @Transactional 계층이다. Repository가 조회하고 이
#   서비스가 상태 전이와 오래된 제안 검사를 맡는다.
# =============================================================================

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.error_codes import ErrorCode
from app.core.exceptions import BusinessError
from app.core.transaction import transactional
from app.models.decision import Decision
from app.models.schedule import ScheduleItem
from app.repositories.decision_schedule_repository import DecisionScheduleRepository
from app.schemas.decision_schedule import (
    DecisionListResponse,
    DecisionRow,
    ScheduleItemListResponse,
    ScheduleItemRow,
)

APPROVED_DECISIONS = ("APPROVED", "EDITED")


class DecisionScheduleReviewService:
    def __init__(self, db: Session, repository: DecisionScheduleRepository) -> None:
        self._db = db
        self._repository = repository

    def list_decisions(
        self,
        project_id: int,
        decisions: tuple[str, ...],
        limit: int,
        document_id: int | None = None,
    ) -> DecisionListResponse:
        rows, total = self._repository.list_decisions(
            project_id, decisions, limit, document_id
        )
        items = [self._decision_row(*row) for row in rows]
        return DecisionListResponse(
            items=items,
            total=total,
            returned=len(items),
            truncated=total > len(items),
            limit=limit,
            included_decisions=list(decisions),
        )

    def list_schedule_items(
        self,
        project_id: int,
        decisions: tuple[str, ...],
        limit: int,
        document_id: int | None = None,
    ) -> ScheduleItemListResponse:
        rows, total = self._repository.list_schedule_items(
            project_id, decisions, limit, document_id
        )
        items = [self._schedule_row(*row) for row in rows]
        return ScheduleItemListResponse(
            items=items,
            total=total,
            returned=len(items),
            truncated=total > len(items),
            limit=limit,
            included_decisions=list(decisions),
        )

    def update_decision(
        self, project_id: int, item_id: int, user_id: int, values: dict
    ) -> DecisionRow:
        found = self._get_decision(project_id, item_id)
        item, filename, current_revision = found
        with transactional(self._db):
            filename, current_revision = self._lock_current_source(
                project_id, item, filename, current_revision
            )
            for field in ("title", "content", "status", "decided_on"):
                if field in values:
                    setattr(item, field, values[field])
            self._mark(item, "EDITED", user_id)
        return self._decision_row(item, filename, current_revision)

    def update_schedule_item(
        self, project_id: int, item_id: int, user_id: int, values: dict
    ) -> ScheduleItemRow:
        found = self._get_schedule_item(project_id, item_id)
        item, filename, current_revision = found
        starts_on = values.get("starts_on", item.starts_on)
        ends_on = values.get("ends_on", item.ends_on)
        if starts_on and ends_on and starts_on > ends_on:
            raise BusinessError(ErrorCode.INVALID_SCHEDULE_DATES)
        with transactional(self._db):
            filename, current_revision = self._lock_current_source(
                project_id, item, filename, current_revision
            )
            for field in ("title", "kind", "starts_on", "ends_on"):
                if field in values:
                    setattr(item, field, values[field])
            self._mark(item, "EDITED", user_id)
        return self._schedule_row(item, filename, current_revision)

    def approve_decision(self, project_id: int, item_id: int, user_id: int) -> DecisionRow:
        return self._decide_decision(project_id, item_id, user_id, "APPROVED")

    def reject_decision(self, project_id: int, item_id: int, user_id: int) -> DecisionRow:
        return self._decide_decision(project_id, item_id, user_id, "REJECTED")

    def cancel_decision(self, project_id: int, item_id: int) -> DecisionRow:
        item, filename, current_revision = self._get_decision(project_id, item_id)
        with transactional(self._db):
            if item.decision == "REJECTED":
                filename, current_revision = self._lock_current_source(
                    project_id, item, filename, current_revision
                )
            self._cancel(item)
        return self._decision_row(item, filename, current_revision)

    def approve_schedule_item(
        self, project_id: int, item_id: int, user_id: int
    ) -> ScheduleItemRow:
        return self._decide_schedule_item(project_id, item_id, user_id, "APPROVED")

    def reject_schedule_item(
        self, project_id: int, item_id: int, user_id: int
    ) -> ScheduleItemRow:
        return self._decide_schedule_item(project_id, item_id, user_id, "REJECTED")

    def cancel_schedule_item(self, project_id: int, item_id: int) -> ScheduleItemRow:
        item, filename, current_revision = self._get_schedule_item(project_id, item_id)
        with transactional(self._db):
            if item.decision == "REJECTED":
                filename, current_revision = self._lock_current_source(
                    project_id, item, filename, current_revision
                )
            self._cancel(item)
        return self._schedule_row(item, filename, current_revision)

    def _decide_decision(
        self, project_id: int, item_id: int, user_id: int, decision: str
    ) -> DecisionRow:
        item, filename, current_revision = self._get_decision(project_id, item_id)
        with transactional(self._db):
            if decision == "APPROVED":
                filename, current_revision = self._lock_current_source(
                    project_id, item, filename, current_revision
                )
            self._mark(item, decision, user_id)
        return self._decision_row(item, filename, current_revision)

    def _decide_schedule_item(
        self, project_id: int, item_id: int, user_id: int, decision: str
    ) -> ScheduleItemRow:
        item, filename, current_revision = self._get_schedule_item(project_id, item_id)
        with transactional(self._db):
            if decision == "APPROVED":
                filename, current_revision = self._lock_current_source(
                    project_id, item, filename, current_revision
                )
            self._mark(item, decision, user_id)
        return self._schedule_row(item, filename, current_revision)

    def _get_decision(self, project_id: int, item_id: int):
        found = self._repository.get_decision(project_id, item_id)
        if found is None:
            raise BusinessError(ErrorCode.DECISION_NOT_FOUND)
        return found

    def _get_schedule_item(self, project_id: int, item_id: int):
        found = self._repository.get_schedule_item(project_id, item_id)
        if found is None:
            raise BusinessError(ErrorCode.SCHEDULE_ITEM_NOT_FOUND)
        return found

    @staticmethod
    def _mark(item: Decision | ScheduleItem, decision: str, user_id: int) -> None:
        # 금액 승인 흐름과 같이 현재 상태를 제한하지 않는다. 잘못 승인·거절한
        # 판단을 다른 판단으로 바로 정정할 수 있고 마지막 판단자를 남긴다.
        item.decision = decision
        item.decided_by = user_id
        item.decided_at = datetime.now(timezone.utc)

    @staticmethod
    def _cancel(item: Decision | ScheduleItem) -> None:
        # 금액 취소와 같이 수정된 업무 값은 되돌리지 않고 판단 메타데이터만 지운다.
        item.decision = "PENDING"
        item.decided_by = None
        item.decided_at = None

    def _lock_current_source(
        self,
        project_id: int,
        item: Decision | ScheduleItem,
        filename: str | None,
        current_revision: int | None,
    ) -> tuple[str | None, int | None]:
        """출처 문서를 잠근 뒤 revision을 다시 읽어 승인 판정을 원자화한다."""
        if item.document_id is None:
            return filename, current_revision
        source = self._repository.lock_document(project_id, item.document_id)
        if source is None:
            # 문서 삭제 시 제안 행은 남기는 스키마다. 현재 revision을 알 수 없으므로
            # 삭제된 출처 행의 검토를 막지 않는다.
            return None, None
        locked_filename, locked_revision = source
        self._ensure_current(item.source_text_revision, locked_revision)
        return locked_filename, locked_revision

    @staticmethod
    def _ensure_current(source_revision: int, current_revision: int | None) -> None:
        # 문서가 삭제돼 현재 revision을 알 수 없으면 행 보존 설계에 맞게 막지 않는다.
        if current_revision is not None and source_revision < current_revision:
            raise BusinessError(ErrorCode.STALE_SUGGESTION)

    @staticmethod
    def _decision_row(
        item: Decision, filename: str | None, current_revision: int | None
    ) -> DecisionRow:
        return DecisionRow(
            id=item.id,
            document_id=item.document_id,
            filename=filename,
            title=item.title,
            content=item.content,
            status=item.status,
            superseded_by=item.superseded_by,
            decided_on=item.decided_on,
            confidence=item.confidence,
            reason=item.reason,
            decision=item.decision,
            decided_by=item.decided_by,
            decided_at=item.decided_at,
            source_text_revision=item.source_text_revision,
            current_text_revision=current_revision,
            stale=current_revision is not None
            and item.source_text_revision < current_revision,
        )

    @staticmethod
    def _schedule_row(
        item: ScheduleItem, filename: str | None, current_revision: int | None
    ) -> ScheduleItemRow:
        return ScheduleItemRow(
            id=item.id,
            document_id=item.document_id,
            filename=filename,
            title=item.title,
            kind=item.kind,
            starts_on=item.starts_on,
            ends_on=item.ends_on,
            confidence=item.confidence,
            reason=item.reason,
            decision=item.decision,
            decided_by=item.decided_by,
            decided_at=item.decided_at,
            source_text_revision=item.source_text_revision,
            current_text_revision=current_revision,
            stale=current_revision is not None
            and item.source_text_revision < current_revision,
        )
