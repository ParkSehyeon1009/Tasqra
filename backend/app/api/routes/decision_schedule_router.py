# =============================================================================
# 이 파일의 책임: 결정사항·일정 제안의 목록과 승인·수정·거절·취소 HTTP API다.
# 다른 파일과의 관계: dependencies.py가 review service와 프로젝트 권한을 주입하고,
#   decision_schedule.py DTO로 요청·응답 계약을 고정한다.
# Spring 비교: @RestController다. get_project_access는 조회 인터셉터,
#   get_project_editor_access는 변경 메서드의 @PreAuthorize 역할이다.
# =============================================================================

from fastapi import APIRouter, Depends, Query

from app.dependencies import (
    ProjectAccess,
    get_decision_schedule_review_service,
    get_project_access,
    get_project_editor_access,
)
from app.schemas.decision_schedule import (
    DecisionListResponse,
    DecisionRow,
    DecisionUpdateRequest,
    ScheduleItemListResponse,
    ScheduleItemRow,
    ScheduleItemUpdateRequest,
)
from app.services.decision_schedule_review_service import (
    APPROVED_DECISIONS,
    DecisionScheduleReviewService,
)

router = APIRouter(prefix="/api/projects/{project_id}", tags=["decision-schedule"])


@router.get("/decisions", response_model=DecisionListResponse)
def list_decisions(
    limit: int = Query(200, ge=1, le=500),
    access: ProjectAccess = Depends(get_project_access),
    service: DecisionScheduleReviewService = Depends(get_decision_schedule_review_service),
) -> DecisionListResponse:
    """승인 또는 수정 승인된 결정사항만 돌려준다."""
    return service.list_decisions(access.project.id, APPROVED_DECISIONS, limit)


@router.get("/decisions/pending", response_model=DecisionListResponse)
def list_pending_decisions(
    limit: int = Query(200, ge=1, le=500),
    access: ProjectAccess = Depends(get_project_access),
    service: DecisionScheduleReviewService = Depends(get_decision_schedule_review_service),
) -> DecisionListResponse:
    return service.list_decisions(access.project.id, ("PENDING",), limit)


@router.get("/decisions/rejected", response_model=DecisionListResponse)
def list_rejected_decisions(
    limit: int = Query(200, ge=1, le=500),
    access: ProjectAccess = Depends(get_project_access),
    service: DecisionScheduleReviewService = Depends(get_decision_schedule_review_service),
) -> DecisionListResponse:
    return service.list_decisions(access.project.id, ("REJECTED",), limit)


@router.patch("/decisions/{item_id}", response_model=DecisionRow)
def update_decision(
    item_id: int,
    body: DecisionUpdateRequest,
    access: ProjectAccess = Depends(get_project_editor_access),
    service: DecisionScheduleReviewService = Depends(get_decision_schedule_review_service),
) -> DecisionRow:
    return service.update_decision(
        access.project.id,
        item_id,
        access.member.user_id,
        body.model_dump(exclude_unset=True),
    )


@router.post("/decisions/{item_id}/approve", response_model=DecisionRow)
def approve_decision(
    item_id: int,
    access: ProjectAccess = Depends(get_project_editor_access),
    service: DecisionScheduleReviewService = Depends(get_decision_schedule_review_service),
) -> DecisionRow:
    return service.approve_decision(access.project.id, item_id, access.member.user_id)


@router.post("/decisions/{item_id}/reject", response_model=DecisionRow)
def reject_decision(
    item_id: int,
    access: ProjectAccess = Depends(get_project_editor_access),
    service: DecisionScheduleReviewService = Depends(get_decision_schedule_review_service),
) -> DecisionRow:
    return service.reject_decision(access.project.id, item_id, access.member.user_id)


@router.post("/decisions/{item_id}/cancel", response_model=DecisionRow)
def cancel_decision(
    item_id: int,
    access: ProjectAccess = Depends(get_project_editor_access),
    service: DecisionScheduleReviewService = Depends(get_decision_schedule_review_service),
) -> DecisionRow:
    return service.cancel_decision(access.project.id, item_id)


@router.get("/schedule-items", response_model=ScheduleItemListResponse)
def list_schedule_items(
    limit: int = Query(200, ge=1, le=500),
    access: ProjectAccess = Depends(get_project_access),
    service: DecisionScheduleReviewService = Depends(get_decision_schedule_review_service),
) -> ScheduleItemListResponse:
    """승인 또는 수정 승인된 일정·기한만 돌려준다."""
    return service.list_schedule_items(access.project.id, APPROVED_DECISIONS, limit)


@router.get("/schedule-items/pending", response_model=ScheduleItemListResponse)
def list_pending_schedule_items(
    limit: int = Query(200, ge=1, le=500),
    access: ProjectAccess = Depends(get_project_access),
    service: DecisionScheduleReviewService = Depends(get_decision_schedule_review_service),
) -> ScheduleItemListResponse:
    return service.list_schedule_items(access.project.id, ("PENDING",), limit)


@router.get("/schedule-items/rejected", response_model=ScheduleItemListResponse)
def list_rejected_schedule_items(
    limit: int = Query(200, ge=1, le=500),
    access: ProjectAccess = Depends(get_project_access),
    service: DecisionScheduleReviewService = Depends(get_decision_schedule_review_service),
) -> ScheduleItemListResponse:
    return service.list_schedule_items(access.project.id, ("REJECTED",), limit)


@router.patch("/schedule-items/{item_id}", response_model=ScheduleItemRow)
def update_schedule_item(
    item_id: int,
    body: ScheduleItemUpdateRequest,
    access: ProjectAccess = Depends(get_project_editor_access),
    service: DecisionScheduleReviewService = Depends(get_decision_schedule_review_service),
) -> ScheduleItemRow:
    return service.update_schedule_item(
        access.project.id,
        item_id,
        access.member.user_id,
        body.model_dump(exclude_unset=True),
    )


@router.post("/schedule-items/{item_id}/approve", response_model=ScheduleItemRow)
def approve_schedule_item(
    item_id: int,
    access: ProjectAccess = Depends(get_project_editor_access),
    service: DecisionScheduleReviewService = Depends(get_decision_schedule_review_service),
) -> ScheduleItemRow:
    return service.approve_schedule_item(access.project.id, item_id, access.member.user_id)


@router.post("/schedule-items/{item_id}/reject", response_model=ScheduleItemRow)
def reject_schedule_item(
    item_id: int,
    access: ProjectAccess = Depends(get_project_editor_access),
    service: DecisionScheduleReviewService = Depends(get_decision_schedule_review_service),
) -> ScheduleItemRow:
    return service.reject_schedule_item(access.project.id, item_id, access.member.user_id)


@router.post("/schedule-items/{item_id}/cancel", response_model=ScheduleItemRow)
def cancel_schedule_item(
    item_id: int,
    access: ProjectAccess = Depends(get_project_editor_access),
    service: DecisionScheduleReviewService = Depends(get_decision_schedule_review_service),
) -> ScheduleItemRow:
    return service.cancel_schedule_item(access.project.id, item_id)
