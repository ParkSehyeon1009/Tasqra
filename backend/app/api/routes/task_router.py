from fastapi import APIRouter, Depends, Response

from app.dependencies import ProjectAccess, get_project_access, get_project_editor_access, get_task_service
from app.schemas.task import TaskCreateRequest, TaskResponse, TaskUpdateRequest
from app.services.task_service import TaskService

router = APIRouter(prefix="/api/projects/{project_id}/tasks", tags=["tasks"])


@router.get("", response_model=list[TaskResponse])
def list_tasks(access: ProjectAccess = Depends(get_project_access), service: TaskService = Depends(get_task_service)):
    return service.list(access.project.id)


@router.get("/{task_id}", response_model=TaskResponse)
def get_task(task_id: int, access: ProjectAccess = Depends(get_project_access), service: TaskService = Depends(get_task_service)):
    return service.get(access.project.id, task_id)


@router.post("", response_model=TaskResponse, status_code=201)
def create_task(body: TaskCreateRequest, access: ProjectAccess = Depends(get_project_editor_access), service: TaskService = Depends(get_task_service)):
    return service.create(access.project.id, access.member.user_id, body.model_dump())


@router.patch("/{task_id}", response_model=TaskResponse)
def update_task(task_id: int, body: TaskUpdateRequest, access: ProjectAccess = Depends(get_project_editor_access), service: TaskService = Depends(get_task_service)):
    return service.update(access.project.id, task_id, body.model_dump(exclude_unset=True))


@router.delete("/{task_id}", status_code=204)
def delete_task(task_id: int, access: ProjectAccess = Depends(get_project_editor_access), service: TaskService = Depends(get_task_service)):
    service.delete(access.project.id, task_id)
    return Response(status_code=204)
