from fastapi import APIRouter, Depends, Query

from app.dependencies import ProjectAccess, get_project_access, get_project_editor_access, get_task_suggestion_service
from app.schemas.task_suggestion import TaskSuggestionListResponse, TaskSuggestionRow, TaskSuggestionUpdateRequest

router = APIRouter(prefix="/api/projects/{project_id}/task-suggestions", tags=["task-suggestions"])


@router.get("", response_model=TaskSuggestionListResponse)
def approved(document_id: int | None = None, limit: int = Query(200, ge=1, le=500),
             access: ProjectAccess = Depends(get_project_access),
             service=Depends(get_task_suggestion_service)):
    return service.list(access.project.id, ("APPROVED", "EDITED"), limit, document_id)


@router.get("/pending", response_model=TaskSuggestionListResponse)
def pending(document_id: int | None = None, limit: int = Query(200, ge=1, le=500),
            access: ProjectAccess = Depends(get_project_access),
            service=Depends(get_task_suggestion_service)):
    return service.list(access.project.id, ("PENDING",), limit, document_id)


@router.get("/rejected", response_model=TaskSuggestionListResponse)
def rejected(document_id: int | None = None, limit: int = Query(200, ge=1, le=500),
             access: ProjectAccess = Depends(get_project_access),
             service=Depends(get_task_suggestion_service)):
    return service.list(access.project.id, ("REJECTED",), limit, document_id)


@router.post("/{item_id}/approve", response_model=TaskSuggestionRow)
def approve(item_id: int, body: TaskSuggestionUpdateRequest | None = None,
            access: ProjectAccess = Depends(get_project_editor_access),
            service=Depends(get_task_suggestion_service)):
    return service.approve(access.project.id, item_id, access.member.user_id,
                           body.model_dump(exclude_unset=True) if body else None)


@router.post("/{item_id}/reject", response_model=TaskSuggestionRow)
def reject(item_id: int, access: ProjectAccess = Depends(get_project_editor_access),
           service=Depends(get_task_suggestion_service)):
    return service.reject(access.project.id, item_id, access.member.user_id)


@router.post("/{item_id}/cancel", response_model=TaskSuggestionRow)
def cancel(item_id: int, access: ProjectAccess = Depends(get_project_editor_access),
           service=Depends(get_task_suggestion_service)):
    return service.cancel(access.project.id, item_id)
