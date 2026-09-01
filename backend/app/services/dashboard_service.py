# =============================================================================
# 이 파일의 책임: 프로젝트 단건·전역 포트폴리오 핵심 현황(DSH-001)과
#   프로젝트 캘린더 조회 결과를 만든다. 집계 상태를 화면 묶음으로 접는다.
# 다른 파일과의 관계: repositories/dashboard_repository.py 로 조회하고 응답 계약은
#   schemas/dashboard.py 다. api/routes/dashboard_router.py 가 부른다.
# Spring 비교: @Service 다. 상태 묶기 규칙이 이 계층에 있는 것은
#   amount_calculator 의 집계가 서비스에 있는 것과 같은 이유다 — 판단은 SQL 이
#   아니라 코드에 두고 테스트할 수 있게 한다.
#
# 권한 범위를 정하는 위치
#   프로젝트 단건 조회는 라우터의 get_project_access가 판정한 project_id만 받는다.
#   전역 포트폴리오는 라우터에서 인증한 user_id를 받고 ProjectRepository로 참여
#   프로젝트 범위를 한 번 계산한다. 이후 bulk 조회는 그 ID 목록 밖을 읽지 않는다.
#
# 왜 화면에서 세지 않고 서버에서 세나
#   기존 대시보드는 문서 목록을 받아 화면에서 셌다. 그런데 그 목록은
#   GET /documents 의 첫 페이지이고 기본 size 가 20 이다(document_router.py).
#   useWorkspaceData 는 응답의 items 만 쓰므로 **문서가 21건 이상인 프로젝트에서
#   숫자가 조용히 틀린다.** 에러도 안 나고 화면도 정상으로 보인다. 페이지를 전부
#   받아 세는 방법은 문서가 늘수록 요청이 늘어 답이 아니다. 세는 일은 DB 가
#   해야 한다.
# =============================================================================

from __future__ import annotations

import logging
from datetime import date

from app.models.document import Document
from app.models.enums import DocumentStatus, ReviewStatus
from app.repositories.dashboard_repository import DashboardRepository
from app.repositories.project_repository import ProjectRepository
from app.schemas.dashboard import (
    DashboardCalendarEvent,
    DashboardCalendarResponse,
    DashboardDocumentCounts,
    DashboardDocumentTypeCount,
    DashboardRecentDocument,
    DashboardResponse,
    PortfolioDashboardResponse,
    PortfolioProjectDashboard,
    PortfolioTaskActivity,
)

logger = logging.getLogger(__name__)

# "처리 중" 으로 묶을 상태. 사용자가 기다리면 저절로 끝나는 상태들이다.
#
# FAILED 를 넣지 않는다 — 기다려도 끝나지 않고 사람이 재처리를 눌러야 한다.
# EXTRACTED 도 넣지 않는다. 추출은 끝났고 다음 단계(검수·분석)를 기다리는
# 상태라서, 처리 중에 넣으면 "언제 끝나나" 를 잘못 읽게 된다.
#
# 화면의 utils/documentStatus.js 가 쓰는 셋과 같아야 한다. 다르면 같은 문서가
# 대시보드와 문서 목록에서 다르게 분류된다.
PROCESSING_STATUSES = (
    DocumentStatus.PENDING.value,
    DocumentStatus.EXTRACTING.value,
    DocumentStatus.ANALYZING.value,
)

# OCR 검수가 필요한 상태. NOT_REQUIRED(검수 대상 아님)와 COMPLETED(끝냄)는 빼고
# 사람이 아직 손대야 하는 둘만 센다.
REVIEW_PENDING_STATUSES = (
    ReviewStatus.PENDING.value,
    ReviewStatus.IN_PROGRESS.value,
)


class DashboardService:
    def __init__(
        self,
        dashboard_repository: DashboardRepository,
        project_repository: ProjectRepository,
    ) -> None:
        self._dashboard = dashboard_repository
        self._projects = project_repository

    def get_overview(
        self,
        *,
        project_id: int,
        recent_limit: int,
    ) -> DashboardResponse:
        response = self._build_overview(
            by_status=self._dashboard.count_documents_by_status(project_id),
            by_review=self._dashboard.count_documents_by_review_status(project_id),
            type_rows=self._dashboard.count_documents_by_type(project_id),
            recent=self._dashboard.list_recent_documents(
                project_id=project_id, limit=recent_limit
            ),
            pending_amounts=self._dashboard.count_pending_amount_items(project_id),
            open_tasks=self._dashboard.count_open_tasks(project_id),
        )
        logger.info(
            "대시보드 현황 project_id=%s 문서=%d건 처리중=%d 검수대기=%d 금액승인대기=%d",
            project_id,
            response.documents.total,
            response.documents.processing,
            response.review_pending,
            response.pending_amount_items,
        )
        return response

    def get_portfolio(
        self,
        *,
        user_id: int,
        recent_document_limit: int,
        activity_limit: int,
    ) -> PortfolioDashboardResponse:
        """사용자가 참여한 모든 프로젝트의 전역 현황을 고정된 수의 쿼리로 만든다."""
        memberships = self._projects.list_for_user(user_id)
        project_ids = [int(project.id) for project, _member in memberships]
        if not project_ids:
            return PortfolioDashboardResponse()

        by_status, by_review = self._dashboard.count_document_states_by_projects(
            project_ids
        )
        types = self._dashboard.count_document_types_by_projects(project_ids)
        pending_amounts = self._dashboard.count_pending_amount_items_by_projects(
            project_ids
        )
        open_tasks = self._dashboard.count_open_tasks_by_projects(project_ids)
        recent_documents = self._dashboard.list_recent_documents_by_projects(
            project_ids=project_ids,
            limit_per_project=recent_document_limit,
        )
        activity = self._dashboard.list_recent_task_activity_by_projects(
            project_ids=project_ids,
            limit=activity_limit,
        )

        return PortfolioDashboardResponse(
            projects=[
                PortfolioProjectDashboard(
                    project_id=project_id,
                    dashboard=self._build_overview(
                        by_status=by_status.get(project_id, {}),
                        by_review=by_review.get(project_id, {}),
                        type_rows=types.get(project_id, []),
                        recent=recent_documents.get(project_id, []),
                        pending_amounts=pending_amounts.get(project_id, 0),
                        open_tasks=open_tasks.get(project_id, 0),
                    ),
                )
                for project_id in project_ids
            ],
            recent_task_activity=[
                PortfolioTaskActivity.model_validate(item) for item in activity
            ],
        )

    @staticmethod
    def _build_overview(
        *,
        by_status: dict[str, int],
        by_review: dict[str, int],
        type_rows: list[tuple[str | None, int]],
        recent: list[Document],
        pending_amounts: int,
        open_tasks: int,
    ) -> DashboardResponse:
        counts = DashboardDocumentCounts(**document_counts(by_status))
        return DashboardResponse(
            documents=counts,
            review_pending=review_pending_count(by_review),
            pending_amount_items=pending_amounts,
            open_tasks=open_tasks,
            document_types=[
                DashboardDocumentTypeCount(document_type=document_type, count=count)
                for document_type, count in sort_type_rows(
                    merge_legacy_document_types(type_rows)
                )
            ],
            recent_documents=[
                DashboardRecentDocument.model_validate(document) for document in recent
            ],
        )

    def get_calendar(
        self, *, project_id: int, starts_on: date, ends_on: date
    ) -> DashboardCalendarResponse:
        """태스크 마감과 승인된 일정을 월간 달력용 공통 계약으로 합친다."""
        tasks = self._dashboard.list_calendar_tasks(
            project_id=project_id, starts_on=starts_on, ends_on=ends_on
        )
        schedules = self._dashboard.list_calendar_schedule_items(
            project_id=project_id, starts_on=starts_on, ends_on=ends_on
        )
        items = [
            DashboardCalendarEvent(
                id=f"task:{task.id}",
                item_type="TASK",
                source_id=task.id,
                title=task.title,
                kind="TASK_DUE",
                starts_on=task.due_on,
                ends_on=task.due_on,
                task_type=task.type,
                status=task.status,
            )
            for task in tasks
        ]
        items.extend(
            DashboardCalendarEvent(
                id=f"schedule:{schedule.id}",
                item_type="SCHEDULE",
                source_id=schedule.id,
                title=schedule.title,
                kind=schedule.kind,
                starts_on=schedule.starts_on,
                ends_on=schedule.ends_on,
            )
            for schedule in schedules
        )
        items.sort(
            key=lambda item: (
                item.starts_on or item.ends_on or date.max,
                item.item_type,
                item.source_id,
            )
        )
        return DashboardCalendarResponse(items=items)


# --- 집계 (순수 함수) --------------------------------------------------------
#
# 아래 셋은 DB 도 스키마도 모르는 순수 함수다. 그래서 sqlalchemy·pydantic 이
# 없는 환경에서도 그대로 실행해 검사할 수 있다 — 도구/check_dashboard.py 가
# 소스에서 이 함수들만 잘라내 돌린다. 숫자를 접는 규칙이 지표의 핵심이라
# 확인할 수 있는 자리에 두었다.


def document_counts(by_status: dict[str, int]) -> dict[str, int]:
    """상태 분포를 화면이 쓰는 묶음으로 접는다.

    total 은 **모든 상태의 합**이다. 아는 상태만 더하지 않는다 — enums.py 에
    상태가 추가되고 이 파일이 안 고쳐지면 총계가 조용히 작아진다. 합으로 두면
    모르는 상태가 와도 총계는 맞고, 묶음(processing 등)에만 안 잡힌다.

    상태가 없는 문서는 있을 수 없다(documents.status 가 not null, 기본값 PENDING).
    """
    return {
        "total": sum(by_status.values()),
        "processing": _sum_of(by_status, PROCESSING_STATUSES),
        "extracted": by_status.get(DocumentStatus.EXTRACTED.value, 0),
        "completed": by_status.get(DocumentStatus.COMPLETED.value, 0),
        "failed": by_status.get(DocumentStatus.FAILED.value, 0),
    }


def review_pending_count(by_review: dict[str, int]) -> int:
    """OCR 검수가 필요한 문서 수."""
    return _sum_of(by_review, REVIEW_PENDING_STATUSES)


def _sum_of(counts: dict[str, int], keys: tuple[str, ...]) -> int:
    """분포 dict 에서 여러 상태를 합친다. 없는 키는 0 으로 본다.

    리포지토리가 그 프로젝트에 있는 상태만 돌려주므로 키가 없는 경우가 정상이다.
    """
    return sum(counts.get(key, 0) for key in keys)


def merge_legacy_document_types(
    rows: list[tuple[str | None, int]],
) -> list[tuple[str | None, int]]:
    """레거시 BILLING 건수를 ETC에 합쳐 사용자에게 8종 분포로 보여준다.

    DB 값은 마이그레이션 없이 보존한다. 읽기 모델에서만 합치므로 기존 문서도
    사라지지 않고, ETC 필터의 Repository 호환 규칙과 같은 의미가 된다.
    """
    merged: dict[str | None, int] = {}
    for document_type, count in rows:
        canonical = "ETC" if document_type == "BILLING" else document_type
        merged[canonical] = merged.get(canonical, 0) + count
    return list(merged.items())


def sort_type_rows(rows: list[tuple[str | None, int]]) -> list[tuple[str | None, int]]:
    """많은 유형부터. 유형이 없는 칸(None)은 언제나 맨 끝이다.

    많은 순서로 두는 이유는 대시보드가 "이 프로젝트에 무슨 문서가 쌓였나" 를
    보여주는 자리이기 때문이다. 정의 순서로 두면 0건인 유형이 앞에 오고 실제로
    쌓인 유형을 아래에서 찾아야 한다.

    건수가 같으면 유형 이름으로 정렬한다. 그러지 않으면 DB 가 돌려주는 순서에
    따라 새로고침할 때마다 칸 순서가 바뀐다.

    None 을 맨 끝에 두는 것은 "미분류" 가 유형이 아니라 유형이 없는 상태라서다.
    개수가 많다고 맨 앞에 오면 분포를 읽는 데 방해가 된다.
    """
    return sorted(rows, key=lambda row: (row[0] is None, -row[1], row[0] or ""))
