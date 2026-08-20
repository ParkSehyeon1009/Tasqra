# =============================================================================
# 이 파일의 책임: 산출물 생성 대상 미리보기(DLV-001-2)를 만든다.
#   리포지토리가 세어 준 건수를 받아 **"만들 수 있는가" 를 판단**하고 응답으로
#   바꾼다. 세는 것은 리포지토리, 판단은 여기다 — dashboard_service 와 같은 구조다.
#
#   완료 판정: "LLM 호출 전에 건수가 보이고 대상이 없으면 생성이 방지된다."
#
# 다른 파일과의 관계
#   repositories/deliverable_repository.py  건수를 세어 준다
#   schemas/deliverable.py                  응답 계약
#   api/routes/deliverable_router.py        이 서비스를 부른다
#   models/deliverable.py                   PERIOD_REQUIRED_KINDS 와 같은 판단
#
# Spring 비교: @Service 다. 읽기만 하므로 @Transactional(readOnly = true) 다.
#
# ⚠ 종류마다 세는 대상이 다르다 — 이것이 이 파일의 핵심이다
#
#   | kind           | 기간   | 무엇을 담나                          |
#   |----------------|--------|--------------------------------------|
#   | WEEKLY_REPORT  | 필수   | 기간 안의 문서·결정·일정·금액 변동   |
#   | DECISION_LOG   | 없음   | 결정 **전부**(확정·미결·뒤집힘)      |
#   | MEETING_AGENDA | 없음   | **미결 결정만**(status='PENDING')    |
#   | PROJECT_STATUS | 없음   | 현재 상태 전부                        |
#
#   결정사항 대장에 기간을 걸면 "지난주에 정한 것만" 이 되어 대장이 아니게 된다.
#   회의 안건에 확정된 결정을 넣으면 이미 끝난 것을 또 논의하게 된다.
#   **DB CHECK(ck_deliverable_period_required)가 WEEKLY_REPORT 만 기간을
#   강제하는 것과 같은 판단이다.**
#
# ⚠ 승인 대기는 "담길 내용" 이 아니다
#   기간과 무관하게 세지만 생성 가능 판정에는 넣지 않는다. 승인 대기만 있고
#   확정된 내용이 없으면 보고서는 비어 있다. 화면에는 보여준다 — 사용자가
#   "먼저 승인하고 만들까" 를 판단할 재료다.
# =============================================================================

from __future__ import annotations

import logging
from datetime import date

from app.core.error_codes import ErrorCode
from app.core.exceptions import BusinessError
from app.repositories.deliverable_repository import DeliverableRepository
from app.schemas.deliverable import (
    DELIVERABLE_KINDS,
    PERIOD_REQUIRED_KINDS,
    DeliverablePreviewResponse,
    PreviewCounts,
)

logger = logging.getLogger(__name__)

# tasks 테이블이 없어 셀 수 없는 재료. 생기면 이 목록이 빈다.
UNCOUNTABLE = ["completed_tasks"]

__all__ = ["DeliverableService", "UNCOUNTABLE"]


class DeliverableService:
    def __init__(self, repository: DeliverableRepository) -> None:
        self._repo = repository

    def preview(
        self,
        project_id: int,
        *,
        kind: str,
        period_from: date | None = None,
        period_to: date | None = None,
    ) -> DeliverablePreviewResponse:
        """산출물에 담길 건수를 세어 돌려준다 (DLV-001-2).

        권한은 라우터의 `get_project_access` 가 이미 판정했다. 여기서 다시 보지
        않는다 — dashboard_service 와 같은 이유로 판단 지점을 늘리지 않는다.
        """
        if kind not in DELIVERABLE_KINDS:
            raise BusinessError(ErrorCode.INVALID_DOCUMENT_TYPE)

        needs_period = kind in PERIOD_REQUIRED_KINDS
        if needs_period and (period_from is None or period_to is None):
            raise BusinessError(ErrorCode.PERIOD_REQUIRED)
        if period_from and period_to and period_from > period_to:
            raise BusinessError(ErrorCode.INVALID_PROJECT_DATES)

        # 기간을 쓰지 않는 유형은 날짜가 와도 무시한다. 그래야 화면이 날짜를
        # 남겨둔 채 유형만 바꿔도 결과가 유형의 뜻대로 나온다.
        since, until = (period_from, period_to) if needs_period else (None, None)
        counts = self._count(project_id, kind=kind, since=since, until=until)

        can_generate = counts.countable_total > 0
        reason = None
        if not can_generate:
            reason = self._blocked_reason(kind, counts)

        logger.info(
            "산출물 미리보기 project_id=%s kind=%s 기간=%s~%s 합=%d 생성가능=%s",
            project_id, kind, since, until, counts.countable_total, can_generate,
        )
        return DeliverablePreviewResponse(
            kind=kind,
            period_from=since,
            period_to=until,
            counts=counts,
            can_generate=can_generate,
            blocked_reason=reason,
            needs_period=needs_period,
            uncountable=list(UNCOUNTABLE),
        )

    # --- 내부 ---------------------------------------------------------------

    def _count(
        self, project_id: int, *, kind: str, since: date | None, until: date | None
    ) -> PreviewCounts:
        """종류에 맞는 재료만 센다. 머리말의 표가 이 함수의 규칙이다."""
        pending = self._repo.count_pending_suggestions(project_id)

        if kind == "MEETING_AGENDA":
            # 미결 결정만 안건이 된다. 리비전 0007 주석:
            # "status='PENDING' 인 항목이 그대로 다음 회의 안건이 된다."
            # 문서·일정·금액은 안건의 재료가 아니다.
            return PreviewCounts(
                documents=0,
                decisions=self._repo.count_decisions(project_id, status="PENDING"),
                schedule_items=0,
                amount_items=0,
                pending_suggestions=pending,
            )

        if kind == "DECISION_LOG":
            # 결정 전부. 기간을 걸지 않는다 — 걸면 대장이 아니게 된다.
            return PreviewCounts(
                documents=0,
                decisions=self._repo.count_decisions(project_id),
                schedule_items=0,
                amount_items=0,
                pending_suggestions=pending,
            )

        # WEEKLY_REPORT · PROJECT_STATUS — 네 종류를 모두 담는다.
        # 주간 보고서는 기간이 있고 현황 한 장은 없다(since·until 이 None).
        return PreviewCounts(
            documents=self._repo.count_documents(project_id, since=since, until=until),
            decisions=self._repo.count_decisions(project_id, since=since, until=until),
            schedule_items=self._repo.count_schedule_items(
                project_id, since=since, until=until
            ),
            amount_items=self._repo.count_amount_items(
                project_id, since=since, until=until
            ),
            pending_suggestions=pending,
        )

    @staticmethod
    def _blocked_reason(kind: str, counts: PreviewCounts) -> str:
        """왜 만들 수 없는지 사람이 읽는 문장으로.

        화면이 그대로 보여줄 수 있어야 한다. 코드를 보고 문장을 만들게 하면
        같은 판단이 두 곳에 생긴다.

        승인 대기가 남아 있으면 그것을 알린다 — 승인하면 담길 내용이 생긴다는
        뜻이므로 사용자가 다음에 할 일을 안다.
        """
        if counts.pending_suggestions > 0:
            return (
                f"담을 내용이 없습니다. 승인 대기 중인 제안이 "
                f"{counts.pending_suggestions}건 있습니다 — 승인하면 담깁니다."
            )
        if kind == "MEETING_AGENDA":
            return "미결 상태인 결정사항이 없습니다. 안건으로 낼 것이 없습니다."
        if kind == "DECISION_LOG":
            return "기록된 결정사항이 없습니다."
        if kind == "WEEKLY_REPORT":
            return "선택한 기간에 문서·결정·일정·금액 변동이 없습니다."
        return "프로젝트에 담을 내용이 아직 없습니다."
